from typing import Any, Dict, List, Optional, Union

from ..models.schemas import (
    Agent2DataSet,
    Agent2GeneratedDataValue,
    Agent2GenerationRequest,
    Agent2GenerationResponse,
)
from .rules_engine import TestDataRulesEngine


class TestDataAgentService:
    """Clean architecture service for Agent 2 test-data synthesis.

    Responsibilities are intentionally separated into a small orchestration layer:
    1. Receive Agent 1 response.
    2. Inspect the Agent 1 mapping payload.
    3. Detect field types from the mapping contract.
    4. Generate data through the strategy rules engine.
    5. Assemble a machine-readable JSON response.
    6. Validate the response contract before returning it.
    """

    def __init__(self, rules_engine: Optional[TestDataRulesEngine] = None):
        self.rules_engine = rules_engine or TestDataRulesEngine()
        self.supported_data_types = {
            "email",
            "username",
            "password",
            "phone_number",
            "phone",
            "text",
            "textarea",
            "address",
            "multiline",
            "gender",
            "number",
            "date",
            "search",
            "dropdown",
            "select",
            "checkbox",
            "radio",
            "file",
            "url",
        }

    def receive_agent_1_response(self, payload: Any) -> Agent2GenerationRequest:
        """Normalize the Agent 1 payload or request object into the Agent 2 request contract."""
        if isinstance(payload, Agent2GenerationRequest):
            return payload
        if isinstance(payload, dict):
            return Agent2GenerationRequest.model_validate(payload)
        if hasattr(payload, "model_dump"):
            try:
                return Agent2GenerationRequest.model_validate(payload.model_dump(mode="json"))
            except Exception:
                pass
        raise TypeError("Unsupported Agent 1 payload type for Agent 2 service")

    @staticmethod
    def _scenario_id_from_agent1(item: Dict[str, Any]) -> Optional[str]:
        if not isinstance(item, dict):
            return None
        mapping = item.get("mapping") or {}
        candidates = [
            item.get("scenario_id"),
            item.get("test_scenario_id"),
            item.get("scenario"),
            mapping.get("scenario_id") if isinstance(mapping, dict) else None,
            mapping.get("test_scenario_id") if isinstance(mapping, dict) else None,
            mapping.get("scenarioId") if isinstance(mapping, dict) else None,
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    def inspect_mapping(self, payload: Agent2GenerationRequest) -> List[Dict[str, Any]]:
        """Pull test cases out of Agent 1's nested contract shape."""
        agent_1_contract = payload.agent_1_contract or {}
        # Prefer explicit scenarios array when provided by Agent 1; fall back to test_cases
        scenarios = payload.scenarios or agent_1_contract.get("scenarios") or agent_1_contract.get("test_scenarios") or None
        test_cases = payload.test_cases or agent_1_contract.get("test_cases") or agent_1_contract.get("testcases") or None

        candidate = scenarios if isinstance(scenarios, list) and scenarios else test_cases
        if isinstance(candidate, dict):
            candidate = candidate.get("scenarios") or candidate.get("test_cases") or candidate.get("testcases") or []
        if not isinstance(candidate, list):
            return []
        test_cases = candidate

        normalized_cases: List[Dict[str, Any]] = []
        for item in test_cases:
            if hasattr(item, "model_dump"):
                try:
                    item = item.model_dump(mode="json")
                except Exception:
                    item = dict(item)
            if isinstance(item, dict):
                normalized_cases.append(item)
        return normalized_cases

    def detect_field_type(self, field: Dict[str, Any]) -> str:
        """Resolve a field's machine-readable type from the Agent 1 mapping contract.

        Accept many common key names: field_type, type, tag, nodeName, input_type, and map textarea/address to text.
        """
        if not isinstance(field, dict):
            return "text"
        # Check multiple possible keys for field type
        field_type = (
            field.get("field_type")
            or field.get("type")
            or field.get("tag")
            or field.get("nodeName")
            or field.get("input_type")
            or field.get("controlType")
            or "text"
        )
        normalized = str(field_type or "").strip().lower()
        # Preserve specialized controls so their strategies can produce
        # multiline and address-shaped values.
        if normalized == "street":
            normalized = "address"
        elif normalized == "textarea-input":
            normalized = "textarea"
        if normalized == "phone_number":
            normalized = "phone"
        if normalized == "textbox":
            normalized = "text"
        if normalized in ("tel", "telephone", "mobile"):
            normalized = "phone"
        if normalized in ("select", "combobox"):
            normalized = "select"
        return normalized if normalized in self.supported_data_types else "text"

    def _infer_field_type_from_alias(self, alias: str) -> str:
        normalized = str(alias or "").strip().lower()
        if not normalized:
            return "text"

        alias_map = {
            "username": "username",
            "user": "username",
            "email": "email",
            "e-mail": "email",
            "password": "password",
            "passcode": "password",
            "phone": "phone",
            "phone_number": "phone",
            "telephone": "phone",
            "mobile": "phone",
            "gender": "gender",
            "sex": "gender",
            "search": "search",
            "query": "search",
            "find": "search",
            "dropdown": "dropdown",
            "select": "dropdown",
            "checkbox": "checkbox",
            "radio": "radio",
            "file": "file",
            "url": "url",
            "website": "url",
            "link": "url",
            "date": "date",
            "dob": "date",
            "birthday": "date",
            "state": "dropdown",
            "city": "dropdown",
            "country": "dropdown",
            "address": "address",
            "street": "address",
            "textarea": "textarea",
            "number": "number",
            "amount": "number",
            "quantity": "number",
        }

        for token, mapped in alias_map.items():
            if token in normalized:
                return mapped
        return "text"

    def _collect_field_specs(self, test_case: Dict[str, Any]) -> List[Dict[str, Any]]:
        specs_by_name: Dict[str, Dict[str, Any]] = {}
        input_fields = test_case.get("input_fields") or []
        required_data = test_case.get("required_data") or []

        def add_spec(field_name: str, field_type: str) -> None:
            if not field_name:
                return
            if field_name in specs_by_name:
                existing = specs_by_name[field_name]
                if existing.get("field_type") == "text" and field_type != "text":
                    existing["field_type"] = field_type
                    existing["type"] = field_type
                return
            specs_by_name[field_name] = {
                "field_name": field_name,
                "field_type": field_type,
                "name": field_name,
                "type": field_type,
            }

        for field in input_fields:
            if isinstance(field, dict):
                field_name = str(field.get("name") or field.get("field_name") or field.get("id") or field.get("label") or "").strip()
                field_type = self.detect_field_type(field)
                if field_type == "text":
                    field_type = self._infer_field_type_from_alias(field_name)
            elif isinstance(field, str):
                field_name = field.strip()
                field_type = self._infer_field_type_from_alias(field_name)
            else:
                continue
            add_spec(field_name, field_type)

        for field in required_data:
            if isinstance(field, dict):
                field_name = str(field.get("field_name") or field.get("name") or field.get("id") or field.get("label") or "").strip()
                field_type = self.detect_field_type(field)
                if field_type == "text":
                    field_type = self._infer_field_type_from_alias(field_name)
            elif isinstance(field, str):
                field_name = field.strip()
                field_type = self._infer_field_type_from_alias(field_name)
            else:
                continue
            add_spec(field_name, field_type)

        # If mapping contains explicit field definitions, prefer those (per-scenario mapping)
        mapping = test_case.get("mapping") or {}
        if isinstance(mapping, dict):
            # Common key patterns: 'fields', 'inputs', 'required_data'
            for key in ("fields", "inputs", "required_data", "mapping_fields"):
                entries = mapping.get(key) or []
                if isinstance(entries, list) and entries:
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        field_name = str(entry.get("field_name") or entry.get("name") or entry.get("label") or entry.get("id") or "").strip()
                        if not field_name:
                            continue
                        field_type = self.detect_field_type(entry)
                        add_spec(field_name, field_type)
            # If mapping itself describes a single field
            single_name = mapping.get("field_name") or mapping.get("name") or mapping.get("label")
            if single_name and isinstance(single_name, str):
                field_name = single_name.strip()
                field_type = self.detect_field_type(mapping)
                add_spec(field_name, field_type)

        return list(specs_by_name.values())

    def _requires_test_data(self, test_case: Dict[str, Any]) -> bool:
        """Decide whether the scenario is input-driven versus a page-load/visibility/navigation class."""
        normalized_title = str(test_case.get("title") or test_case.get("description") or "").strip().lower()
        normalized_type = str(test_case.get("test_type") or test_case.get("type") or "").strip().lower()
        scenario_text = " ".join([
            normalized_title,
            str(test_case.get("scenario_id") or ""),
            str(test_case.get("mapping") or ""),
            str(test_case.get("steps") or ""),
        ]).lower()

        skipped_keywords = (
            "page load",
            "page-load",
            "visibility check",
            "visibility",
            "presence check",
            "presence",
            "navigation",
            "navigate",
            "landing",
            "render",
            # Note: 'click' removed as a skip keyword because many input-driven scenarios include clicks
        )

        if normalized_type in {"page_load", "navigation", "visibility", "presence"}:
            return False
        if any(keyword in normalized_title or keyword in scenario_text for keyword in skipped_keywords):
            return False

        field_specs = self._collect_field_specs(test_case)
        if not field_specs:
            return False
        return True

    def generate_data(self, scenario_id: str, field_specs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Call the strategy engine and return the dataset bundle shape that Agent 2 requires."""
        return self.rules_engine.generate_many(scenario_id, field_specs)

    def build_json_response(self, payload: Agent2GenerationRequest) -> Agent2GenerationResponse:
        """Assemble Agent 2's serialized response from Agent 1 inputs."""
        normalized = self.receive_agent_1_response(payload)
        test_cases = self.inspect_mapping(normalized)
        application_name = normalized.application_name or (normalized.agent_1_contract or {}).get("application_name") or "Unknown Application"
        url = normalized.url or (normalized.agent_1_contract or {}).get("url") or ""

        # Debug logging: show how many test cases Agent2 received and their scenario_ids
        try:
            tc_ids = [self._scenario_id_from_agent1(tc) for tc in (test_cases or []) if isinstance(tc, dict)]
        except Exception:
            tc_ids = []
        LOGGER = __import__('logging').getLogger(__name__)
        LOGGER.info("Agent2: build_json_response received %s test_cases. scenario_id/test_case samples: %s", len(test_cases or []), tc_ids[:20])

        positive_data: List[Agent2DataSet] = []
        negative_data: List[Agent2DataSet] = []
        boundary_data: List[Agent2DataSet] = []
        validation_data: List[Agent2DataSet] = []
        scenario_outputs: List["Agent2ScenarioOutput"] = []

        import logging
        LOGGER = logging.getLogger(__name__)

        for index, test_case in enumerate(test_cases):
            if not isinstance(test_case, dict):
                continue

            # Use scenario_id only as provided by Agent 1. Do NOT generate new scenario IDs.
            scenario_id = self._scenario_id_from_agent1(test_case)

            if not scenario_id:
                LOGGER.warning("Agent2: Missing scenario_id for test case; marking as requires_test_data=False. test_case keys=%s", list(test_case.keys()))
                # An unidentifiable record cannot satisfy the one-to-one contract.
                # Skip it rather than fabricate an ID.
                continue

            title = str(test_case.get("title") or test_case.get("description") or f"Dataset for {scenario_id}").strip()
            field_specs = self._collect_field_specs(test_case)

            requires = self._requires_test_data(test_case)

            # Log scenario-level inputs and the requires flag before generating data
            LOGGER.info("Agent2: Preparing scenario: scenario_id=%s title=%s requires_test_data=%s field_specs=%s", scenario_id, title, requires, [f.get('field_name') for f in field_specs])
            for spec in field_specs:
                LOGGER.info(
                    "Agent2 input: scenario_id=%s field_name=%s field_type=%s",
                    scenario_id,
                    spec.get("field_name"),
                    spec.get("field_type"),
                )

            # Build per-scenario output bundle for one-to-one mapping
            scenario_output = {
                "scenario_id": scenario_id,
                "generated_data": {
                    "positive": {},
                    "negative": {},
                    "boundary": {},
                    "validation": {},
                },
            }

            # If this scenario does not require data, append a passive output
            if not requires:
                from ..models.schemas import Agent2ScenarioOutput
                scenario_outputs.append(Agent2ScenarioOutput(scenario_id=scenario_id, requires_test_data=False, generated_data=scenario_output.get("generated_data")))
                continue

            if not field_specs:
                # No field specs discovered; still emit requires_test_data=false
                from ..models.schemas import Agent2ScenarioOutput
                scenario_outputs.append(Agent2ScenarioOutput(scenario_id=scenario_id, requires_test_data=False, generated_data=scenario_output.get("generated_data")))
                continue

            # Enrich field specs with scenario context so generation is not based on scenario_id alone
            enhanced_field_specs = []
            for spec in field_specs:
                enriched = dict(spec)
                enriched["scenario_description"] = test_case.get("description") or test_case.get("title")
                enriched["scenario_test_type"] = test_case.get("test_type")
                enriched["mapping"] = test_case.get("mapping") or {}
                enhanced_field_specs.append(enriched)

            generated_bundle = self.generate_data(scenario_id, enhanced_field_specs)
            generated_data = generated_bundle.get("generated_data") or {}

            # Log generated bundle for debugging and verification
            LOGGER.info("Agent2: Generated bundle for scenario_id=%s -> %s", scenario_id, generated_bundle)
            LOGGER.info(
                "Agent2 output: scenario_id=%s generated_data=%s",
                scenario_id,
                generated_data,
            )

            for dataset_type, dataset_map in generated_data.items():
                for field_name, dataset_row in dataset_map.items():
                    if not isinstance(dataset_row, list):
                        continue
                    field_type = "text"
                    for spec in field_specs:
                        if spec.get("field_name") == field_name:
                            field_type = str(spec.get("field_type") or spec.get("type") or "text")
                            break

                    # Populate scenario-level generated_data
                    scenario_output["generated_data"][dataset_type][field_name] = list(dataset_row)

                    dataset = Agent2DataSet(
                        dataset_type=str(dataset_type),
                        scenario_id=scenario_id,
                        title=title,
                        field_name=str(field_name),
                        field_type=field_type,
                        description=f"Generated {dataset_type} data for {field_name}.",
                        generated_data={
                            "positive": list(dataset_row) if dataset_type == "positive" else [],
                            "negative": list(dataset_row) if dataset_type == "negative" else [],
                            "boundary": list(dataset_row) if dataset_type == "boundary" else [],
                            "validation": list(dataset_row) if dataset_type == "validation" else [],
                        },
                        values=[Agent2GeneratedDataValue(value=item) for item in dataset_row],
                        expected_format=_field_format_for(field_type),
                        validation_rules=_validation_rules_for(field_type),
                    )

                    if dataset_type == "positive":
                        positive_data.append(dataset)
                    elif dataset_type == "negative":
                        negative_data.append(dataset)
                    elif dataset_type == "boundary":
                        boundary_data.append(dataset)
                    else:
                        validation_data.append(dataset)

            # append per-scenario output
            from ..models.schemas import Agent2ScenarioOutput
            scenario_outputs.append(Agent2ScenarioOutput(scenario_id=scenario_id, requires_test_data=True, generated_data=scenario_output.get("generated_data")))

        # Debug logging: show how many scenario_outputs Agent2 is returning and their IDs
        try:
            out_ids = [o.scenario_id for o in scenario_outputs]
        except Exception:
            out_ids = []
        LOGGER.info("Agent2: Returning %s scenario_outputs. ids sample: %s", len(scenario_outputs), out_ids[:20])

        response = Agent2GenerationResponse(
            application_name=application_name,
            url=url,
            requires_test_data=bool(positive_data or negative_data or boundary_data or validation_data),
            positive_data=positive_data,
            negative_data=negative_data,
            boundary_data=boundary_data,
            validation_data=validation_data,
            scenario_outputs=scenario_outputs,
        )
        return self.validate_response(response)

    def validate_response(self, response: Agent2GenerationResponse) -> Agent2GenerationResponse:
        """Validate and normalize the assembled response before it leaves the service."""
        return Agent2GenerationResponse.model_validate(response.model_dump())


class Agent2TestDataService(TestDataAgentService):
    """Backward-compatible subclass alias used by existing imports and tests."""

    def build(self, payload: Agent2GenerationRequest) -> Agent2GenerationResponse:
        return self.build_json_response(payload)


def _field_format_for(field_type: str) -> str:
    mapping = {
        "email": "user@example.com",
        "username": "alpha_user",
        "password": "StrongPassword123!",
        "phone_number": "+1 555 123 4567",
        "text": "plain text input",
        "number": "123",
        "date": "YYYY-MM-DD",
        "search": "search query",
        "dropdown": "select one approved value",
        "checkbox": "true/false",
        "url": "https://example.com",
    }
    return mapping.get(field_type, "string")


def _validation_rules_for(field_type: str) -> List[str]:
    if field_type == "email":
        return ["must conform to RFC-style email syntax"]
    if field_type == "password":
        return ["must satisfy complexity policy", "must not expose a plaintext password"]
    if field_type == "phone_number":
        return ["must match allowed region format"]
    if field_type == "number":
        return ["must be numeric"]
    if field_type == "date":
        return ["must be ISO date format"]
    if field_type == "url":
        return ["must be an absolute URL"]
    return ["must be accepted by the UI contract"]


def build_test_data_contract(payload: Agent2GenerationRequest) -> Agent2GenerationResponse:
    service = TestDataAgentService()
    return service.build_json_response(payload)
