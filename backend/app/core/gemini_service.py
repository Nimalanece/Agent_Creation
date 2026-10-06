import logging
import os
import ast
import html
import json
import re
from urllib.parse import urlparse
from typing import Any, Dict

import httpx
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape


LOGGER = logging.getLogger(__name__)
ENV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(dotenv_path=ENV_FILE, override=False)

MODEL = os.getenv("GEMINI_MODEL", "").strip()
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PROMPTS_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts")
ENV = Environment(
    loader=FileSystemLoader(PROMPTS_PATH),
    autoescape=select_autoescape(enabled_extensions=("j2",)),
)


class GeminiServiceError(Exception):
    pass


class GeminiService:
    def __init__(self, api_key: str | None = None, timeout: int | None = None):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        self.model = (os.getenv("GEMINI_MODEL") or MODEL).strip()
        self.timeout = timeout or int(os.getenv("GEMINI_TIMEOUT_SECONDS", "60"))
        LOGGER.info("Gemini Model: %s", self.model)
        if not self.model:
            raise GeminiServiceError("GEMINI_MODEL is not configured. Set GEMINI_MODEL in backend/.env.")
        if self.api_key:
            LOGGER.info(
                "Gemini credential loaded: length=%d first4=%s credential_type=%s",
                len(self.api_key),
                self.api_key[:4],
                "configured API key credential",
            )

    async def generate_selenium_code(
        self,
        test_case: Dict[str, Any],
        test_data: Dict[str, Any],
        application_url: str | None = None,
    ) -> str:
        generated_data = test_data.get("generated_data") if isinstance(test_data, dict) else None
        LOGGER.info(
            "Agent3 generated_data before validation: type=%s value=%s",
            type(generated_data).__name__,
            generated_data,
        )
        steps = (
            test_case.get("test_steps") or test_case.get("steps") or []
            if isinstance(test_case, dict)
            else []
        )
        LOGGER.info(
            "Agent3 metadata before validation: application_url=%r scenario_id=%r expected_results=%r steps_count=%d",
            application_url or (test_case.get("application_url") if isinstance(test_case, dict) else None),
            test_case.get("scenario_id") if isinstance(test_case, dict) else None,
            test_case.get("expected_results") or test_case.get("expected_result") if isinstance(test_case, dict) else None,
            len(steps),
        )
        for index, step in enumerate(steps, start=1):
            LOGGER.info(
                "Agent3 step metadata: index=%d action=%r locator_type=%r locator_value=%r",
                index,
                step.get("action") if isinstance(step, dict) else None,
                step.get("locator_type") if isinstance(step, dict) else None,
                step.get("locator_value") if isinstance(step, dict) else None,
            )
        validation_errors = self.validate_generation_inputs(
            test_case,
            test_data,
            application_url,
        )
        if validation_errors:
            # Provide detailed diagnostic information for debugging
            test_case_summary = ""
            if isinstance(test_case, dict):
                test_case_summary = (
                    f"test_case={{title={test_case.get('title')!r}, "
                    f"application_url={test_case.get('application_url')!r}, "
                    f"test_steps_count={len(test_case.get('test_steps') or [])}, "
                    f"expected_results={test_case.get('expected_results') or test_case.get('expected_result')!r}}}"
                )
            else:
                test_case_summary = f"test_case is {type(test_case).__name__} not dict"
            
            test_data_summary = ""
            if isinstance(test_data, dict):
                data_values = self._supplied_data_values(test_data)
                test_data_summary = f"test_data={{keys={list(test_data.keys())}, data_values_count={len(data_values)}}}"
            else:
                test_data_summary = f"test_data is {type(test_data).__name__} not dict"
            
            LOGGER.error(
                "Agent 3 metadata validation FAILED - %d errors detected:\n%s\n%s\n%s",
                len(validation_errors),
                "\n".join(f"  - {error}" for error in validation_errors),
                test_case_summary,
                test_data_summary,
            )
            raise GeminiServiceError(
                "ERROR: Missing or invalid metadata from Agent 1 or Agent 2. "
                + " ".join(validation_errors)
            )
        if not self.api_key:
            raise GeminiServiceError(
                "GEMINI_API_KEY is not configured. Set GEMINI_API_KEY in backend/.env."
            )
        clean_test_case = self._sanitize_input(test_case)
        if application_url:
            clean_test_case["application_url"] = self._sanitize_input(application_url)
        canonical_steps = clean_test_case.get("test_steps") or clean_test_case.get("steps") or []
        # Give Agent 3 one authoritative step representation. A stale legacy
        # copy must not make Gemini reinterpret valid locator metadata.
        clean_test_case["test_steps"] = canonical_steps
        clean_test_case["steps"] = canonical_steps
        clean_test_data = self._sanitize_input(test_data)

        # Log what's being sent to Gemini for debugging template validation failures
        LOGGER.debug(
            "Gemini template input: test_case_keys=%s test_case_steps=%s test_case_expected=%s test_data_keys=%s",
            list(clean_test_case.keys()),
            canonical_steps,
            clean_test_case.get("expected_results") or clean_test_case.get("expected_result"),
            list(clean_test_data.keys()),
        )
        
        prompt = ENV.get_template("generate_selenium.j2").render(
            test_case=clean_test_case,
            test_data=clean_test_data,
        )
        url = API_URL.format(model=self.model)
        
        # Log the beginning of the prompt to see what test_case and test_data contain
        prompt_preview = prompt[:1000] if len(prompt) > 1000 else prompt
        LOGGER.debug(
            "Gemini template rendered (first 1000 chars):\n%s",
            prompt_preview,
        )
        LOGGER.info(
            "Gemini request: model=%s response_status=pending auth=query_parameter endpoint=%s",
            self.model,
            url,
        )
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=os.getenv("DISABLE_SSL_VERIFICATION", "false").lower()
                not in ("1", "true", "yes"),
            ) as client:
                    is_navigation_scenario = self._is_navigation_scenario(clean_test_case)
                    validation_error = ""
                    for attempt in range(3):
                        request_prompt = prompt
                        if attempt:
                            request_prompt += (
                                "\n\nThe previous response failed validation. Regenerate the complete script. "
                                "Do not use placeholder identifiers such as element, input_field, submit_button, "
                                "navigation_link, or primary_content. Use only supplied locators and supplied values. "
                                "Do not skip steps and do not add TODO markers. "
                                "For radio scenarios, click/select the supplied radio locator and explicitly verify selected state with is_selected(), checked, or aria-checked. "
                                "For boundary scenarios, implement separate minimum, maximum, and maximum-plus-one probes with assertions for each accepted or rejected outcome. "
                                "Validation failure: " + validation_error
                            )
                            if is_navigation_scenario or "navigation" in validation_error.casefold():
                                request_prompt += (
                                    "\n\nThis is a navigation scenario. The regenerated script MUST contain all of these executable statements: "
                                    "a visibility wait using EC.visibility_of_element_located, an explicit clickability wait using "
                                    "EC.element_to_be_clickable, the supplied link click, a navigation wait using EC.url_contains "
                                    "or EC.url_changes, an assertion that the expected destination path is in driver.current_url, "
                                    "and a destination-page wait using EC.presence_of_element_located or "
                                    "EC.visibility_of_element_located for the supplied destination locator. "
                                    "Do not return the script until every one is present. On this retry, preserve the supplied "
                                    "scenario steps and expected results while adding the missing navigation code."
                                )
                            if "checkbox behavior" in validation_error.casefold():
                                request_prompt += (
                                    "\n\nThis is a checkbox scenario. Use the supplied checkbox locator only. "
                                    "Click it through the safe click helper, assert its selected state with is_selected(), "
                                    "checked, or aria-checked, and when the scenario says deselect/uncheck, click it a second "
                                    "time and assert the deselected state. Do not enter text or validate unrelated controls."
                                )
                        request_payload = {
                            "contents": [{"role": "user", "parts": [{"text": request_prompt}]}],
                            "generationConfig": {"temperature": 0.2},
                        }
                        LOGGER.debug(
                            "Gemini complete request payload attempt=%d: %s",
                            attempt + 1,
                            json.dumps(request_payload, ensure_ascii=True, default=str),
                        )
                        response = await client.post(
                            url,
                            params={"key": self.api_key},
                            json=request_payload,
                            headers={"Content-Type": "application/json"},
                        )
                        LOGGER.info("Gemini model=%s response_status=%s", self.model, response.status_code)
                        response.raise_for_status()
                        body = response.json()
                        usage = body.get("usageMetadata") or {}
                        LOGGER.info(
                            "Gemini model=%s token_usage prompt=%s candidates=%s total=%s",
                            self.model,
                            usage.get("promptTokenCount"),
                            usage.get("candidatesTokenCount"),
                            usage.get("totalTokenCount"),
                        )
                        code = self._extract_text(body)
                        LOGGER.warning(
                            "Gemini raw output preview (first 2000 chars): %s",
                            code[:2000],
                        )
                        LOGGER.warning(
                            "Gemini raw output health: markdown=%s explanations=%s html=%s invalid_imports=%s incomplete_functions=%s",
                            self._content_health(code)["markdown"],
                            self._content_health(code)["explanations"],
                            self._content_health(code)["html"],
                            self._content_health(code)["invalid_imports"],
                            self._content_health(code)["incomplete_functions"],
                        )
                        if isinstance(code, str) and code.strip().startswith("ERROR:"):
                            error_message = code.strip()
                            missing_details = self._describe_missing_metadata(clean_test_case, clean_test_data, error_message)
                            LOGGER.warning(
                                "Gemini metadata validation failure: response_type=error message=%s missing_metadata_details=%s",
                                error_message,
                                missing_details,
                            )
                            if attempt < 2:
                                validation_error = error_message
                                LOGGER.warning("Gemini returned a metadata refusal; retrying with canonical validated metadata")
                                continue
                            raise GeminiServiceError(error_message)
                        try:
                            return self._validate_code(
                                code,
                                clean_test_case,
                                clean_test_data,
                                enforce_fixtures=True,
                            )
                        except GeminiServiceError as exc:
                            validation_error = str(exc)
                            LOGGER.error("Gemini validation failure: %s", validation_error)
                            LOGGER.error(
                                "Gemini response type=%s missing_metadata_details=%s",
                                "python" if code.strip().startswith(("import ", "from ", "def ", "class ")) else "text",
                                self._describe_missing_metadata(clean_test_case, clean_test_data),
                            )
                            try:
                                ast.parse(code)
                            except SyntaxError as syntax_exc:
                                LOGGER.error("Gemini Python syntax error: %s", syntax_exc)
                            LOGGER.error(
                                "Gemini content analysis: markdown=%s explanations=%s html=%s invalid_imports=%s incomplete_functions=%s",
                                self._content_health(code)["markdown"],
                                self._content_health(code)["explanations"],
                                self._content_health(code)["html"],
                                self._content_health(code)["invalid_imports"],
                                self._content_health(code)["incomplete_functions"],
                            )
                            if attempt == 2:
                                raise
                            LOGGER.warning("Gemini model=%s returned invalid Selenium code; retrying", self.model)
                    raise GeminiServiceError("Gemini returned no Selenium code")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            detail = exc.response.text[:500].strip() if exc.response is not None else str(exc)
            LOGGER.error("Gemini model=%s response_status=%s", self.model, status)
            if status == 429:
                retry_after = exc.response.headers.get("retry-after") if exc.response is not None else None
                wait_message = f" Retry after {retry_after} seconds." if retry_after else " Wait for the quota window to reset."
                raise GeminiServiceError(
                    "Gemini quota exceeded for this Google AI project. A new API key "
                    "from the same project does not reset the free-tier quota. "
                    "Enable billing, wait for the quota window to reset, or use a key "
                    "from a different project." + wait_message
                ) from exc
            raise GeminiServiceError(f"Gemini API returned HTTP {status}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise GeminiServiceError(f"Gemini request failed: {exc}") from exc

    @staticmethod
    def validate_generation_inputs(
        test_case: Dict[str, Any],
        test_data: Dict[str, Any],
        application_url: str | None,
    ) -> list[str]:
        errors = []
        if not isinstance(test_case, dict) or not isinstance(test_data, dict):
            return ["Agent 1 test case and Agent 2 test data must be objects."]

        url_value = application_url or test_case.get("application_url")
        url = url_value.strip() if isinstance(url_value, str) else ""
        parsed_url = urlparse(url)
        if not url:
            errors.append("Missing application_url from upstream agents.")
        elif (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.netloc
            or any(character in url for character in "<>\r\n")
            or re.search(r"\s", url)
        ):
            errors.append("application_url must be a valid plain HTTP or HTTPS URL.")

        normalized_steps = test_case.get("test_steps") or []
        raw_steps = test_case.get("steps") or []
        # Agent 1 contracts may retain raw steps alongside normalized test_steps.
        # Validate the normalized DOM-backed representation when available so a
        # stale label in the legacy copy cannot invalidate a valid scenario.
        steps = list(normalized_steps) if normalized_steps else list(raw_steps)
        if GeminiService._is_navigation_scenario(test_case):
            steps = GeminiService._navigation_steps(test_case)
        if not steps:
            errors.append("Missing action metadata from Agent 1 test case.")

        placeholder_values = {
            "sample", "test", "value", "element", "input_field", "submit_button",
            "navigation_link", "primary_content", "application_url",
        }
        valid_locator_types = {
            "id", "name", "data-testid", "data_testid", "href", "css", "css_selector",
            "xpath", "class", "url", "title",
        }
        has_valid_locator = False
        dom_actions = {
            "locate_element", "click_element", "enter_text", "input_text", "fill", "send_keys",
            "select_checkbox", "select_radio", "select_dropdown_option", "upload_file",
            "submit_form", "populate_form", "verify_element_visible", "click", "type_text",
            "set_value", "select_option", "select_dropdown", "check", "uncheck", "choose_radio",
            "upload", "submit", "locate", "assert_visible", "verify_visible",
        }
        for step in steps:
            if not isinstance(step, dict):
                errors.append("Each action must include locator metadata.")
                continue
            action = step.get("action")
            normalized_action = str(action or "").strip().lower()
            if not normalized_action:
                errors.append("Each action must include action metadata.")
            locator_type = str(step.get("locator_type") or "").strip().lower()
            locator_value = str(step.get("locator_value") or step.get("selector") or step.get("target") or "").strip()
            if locator_type not in valid_locator_types or not locator_value:
                if normalized_action in dom_actions:
                    errors.append("Each DOM action must include locator_type and locator_value.")
                continue
            normalized_locator = locator_value.lower()
            if locator_type == "url" and normalized_locator == "application_url" and url:
                has_valid_locator = True
                continue
            if normalized_action not in dom_actions and locator_type in {"title", "url"}:
                continue
            labels = {
                str(step.get(key) or "").strip().lower()
                for key in ("element_name", "label", "field_name")
                if str(step.get(key) or "").strip()
            }
            locator_is_dom_verified = str(step.get("locator_status") or "").strip().lower() == "available"
            if normalized_locator in placeholder_values or (normalized_locator in labels and not locator_is_dom_verified):
                errors.append("Locator values must be actual supplied locators, not labels or placeholders.")
                continue
            if any(character in locator_value for character in "<>\r\n"):
                errors.append("Locator values must be plain text.")
                continue
            has_valid_locator = True

        mapping = test_case.get("mapping") or {}
        if isinstance(mapping, dict):
            mapping_labels = {
                str(mapping.get(key) or "").strip().lower()
                for key in ("label", "field_name", "text", "element_name")
                if str(mapping.get(key) or "").strip()
            }
            for locator_key in ("id", "name", "data-testid", "data_testid", "href", "selector", "css_selector", "xpath"):
                locator_value = str(mapping.get(locator_key) or "").strip()
                if (
                    locator_value
                    and locator_value.lower() not in placeholder_values
                    and locator_value.lower() not in mapping_labels
                    and not any(character in locator_value for character in "<>\r\n")
                ):
                    has_valid_locator = True
                    break
        if any(
            isinstance(step, dict)
            and str(step.get("action") or "").strip().lower() in dom_actions
            for step in steps
        ) and not has_valid_locator:
            errors.append("Missing valid locator from Agent 1 test case.")

        errors.extend(GeminiService._page_consistency_errors(test_case, steps, url))

        expected_results = test_case.get("expected_results") or test_case.get("expected_result")
        if not expected_results:
            errors.append("Missing expected results from Agent 1 test case.")

        data_values = GeminiService._supplied_data_values(test_data)
        input_actions = {
            "enter_text", "input_text", "fill", "send_keys", "type_text", "set_value",
            "select_dropdown_option", "select_option", "select_dropdown", "upload_file", "upload",
        }
        has_input_action = any(
            isinstance(step, dict) and str(step.get("action") or "").strip().lower() in input_actions
            for step in steps
        )
        scenario_text = " ".join(
            str(test_case.get(key) or "")
            for key in ("title", "description", "test_type")
        ).casefold()
        data_free_intent = any(
            marker in scenario_text
            for marker in ("navigation", "navigate", "page load", "page-load", "visibility", "presence", "landing")
        )
        requires_data = has_input_action or (
            bool(test_case.get("required_data") or test_case.get("input_fields"))
            and not data_free_intent
        )
        if test_data.get("requires_test_data") is False:
            requires_data = False
        if requires_data and not data_values:
            errors.append("Missing usable field-specific values from Agent 2 test data.")
        if any(value.lower() in placeholder_values for value in data_values):
            errors.append("Agent 2 test data contains placeholder values.")
        generated_data = test_data.get("generated_data")
        generated_data_valid = (
            test_data.get("requires_test_data") is False
            or isinstance(generated_data, dict)
            and bool(data_values)
        )
        if generated_data_valid:
            LOGGER.info(
                "Agent3 generated_data validation PASS: type=%s usable_values=%d",
                type(generated_data).__name__,
                len(data_values),
            )
        else:
            LOGGER.warning(
                "Agent3 generated_data validation FAIL: expected a non-empty object containing usable values; type=%s usable_values=%d",
                type(generated_data).__name__,
                len(data_values),
            )
        return list(dict.fromkeys(errors))

    @staticmethod
    def _page_consistency_errors(
        test_case: Dict[str, Any], steps: list[Any], application_url: str
    ) -> list[str]:
        """Reject page metadata or page labels that conflict with the opened URL."""
        mapping = test_case.get("mapping") or {}
        if not isinstance(mapping, dict):
            return []

        declared_pages: list[tuple[str, str]] = []
        page_keys = ("page_url", "source_url", "element_url")
        page_label_keys = ("page_name", "source_page", "element_page", "page_context")
        for key in page_keys:
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                declared_pages.append((f"mapping.{key}", value.strip()))
        for key in page_label_keys:
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                declared_pages.append((f"mapping.{key}", value.strip()))
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            for key in page_keys:
                value = step.get(key)
                if isinstance(value, str) and value.strip():
                    declared_pages.append((f"steps[{index}].{key}", value.strip()))
            for key in page_label_keys:
                value = step.get(key)
                if isinstance(value, str) and value.strip():
                    declared_pages.append((f"steps[{index}].{key}", value.strip()))

        if not declared_pages or not application_url:
            return []

        opened = urlparse(application_url)
        opened_path = opened.path.rstrip("/") or "/"
        opened_page = GeminiService._page_identity(opened_path)
        errors = []
        for source, value in declared_pages:
            if source.rsplit(".", 1)[-1] in page_label_keys:
                declared_page = GeminiService._page_identity(value)
                opened_host = opened.netloc.casefold().split(":", 1)[0]
                known_page_on_wrong_host = (
                    declared_page in {"automation-practice-form", "broken-links", "browser-windows"}
                    and opened_host not in {"demoqa.com", "www.demoqa.com"}
                )
                if (opened_page and declared_page != opened_page) or known_page_on_wrong_host:
                    errors.append(
                        f"Page consistency failure: {source}={value!r} does not match application_url={application_url!r}."
                    )
                continue
            declared = urlparse(
                value
                if re.match(r"^https?://", value, re.IGNORECASE)
                else f"https://page.invalid{value if value.startswith('/') else '/' + value}"
            )
            if declared.netloc and declared.netloc != "page.invalid":
                same_origin = (
                    declared.scheme.casefold() == opened.scheme.casefold()
                    and declared.netloc.casefold() == opened.netloc.casefold()
                )
                matches = same_origin and ((declared.path.rstrip("/") or "/") == opened_path)
            else:
                matches = (declared.path.rstrip("/") or "/") == opened_path
            if not matches:
                errors.append(
                    f"Page consistency failure: {source}={value!r} does not match application_url={application_url!r}."
                )
        return errors

    @staticmethod
    def _page_identity(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
        aliases = {
            "automation-practice-form": "automation-practice-form",
            "automation-practice-form-page": "automation-practice-form",
            "broken-links-images": "broken-links",
            "broken-links": "broken-links",
            "broken": "broken-links",
            "browser-windows": "browser-windows",
        }
        return aliases.get(normalized, normalized)

    @staticmethod
    def _unlisted_locator_errors(test_case: Dict[str, Any], code: str) -> list[str]:
        """Reject generated DOM locators that are absent from the scenario contract."""
        supplied = {
            value
            for _, value in GeminiService._supplied_locator_values(test_case)
            if value and value.casefold() != "application_url"
        }
        if not supplied:
            return []
        if not code:
            return []
        generated = set(GeminiService._selenium_locator_literals(code))
        extras = sorted(
            locator for locator in generated - supplied
            if not any(
                re.search(
                    rf"label\s*\[\s*for\s*=\s*[\"']{re.escape(value)}[\"']\s*\]",
                    locator,
                    flags=re.IGNORECASE,
                )
                for value in supplied
            )
        )
        scenario_type = str(test_case.get("test_type") or "").casefold()
        if scenario_type in {"negative", "validation"}:
            extras = [
                value for value in extras
                if value.casefold() not in {"submit", "error", "error-message", "validation-message"}
            ]
        if extras:
            return [
                "Locator traceability failure: generated locators are not declared by the scenario, expected results, or mapping: "
                + ", ".join(extras)
            ]
        return []

    @staticmethod
    def _describe_missing_metadata(
        test_case: Dict[str, Any],
        test_data: Dict[str, Any],
        error_text: str | None = None,
    ) -> Dict[str, list[str]]:
        missing = {
            "agent1": [],
            "agent2": [],
        }

        error_text = (error_text or "").strip()
        if error_text:
            field_match = re.search(r"Missing fields?\s*[:\-]?\s*(.+?)(?:\.|$)", error_text, flags=re.IGNORECASE)
            if field_match:
                fields = [part.strip() for part in re.split(r"[,;|\n]+", field_match.group(1)) if part.strip()]
                for field in fields:
                    normalized = field.strip().strip("[](){}")
                    if not normalized:
                        continue
                    if normalized.startswith("steps[") or normalized in {"application_url", "steps", "expected_results", "locator_type", "locator_value", "action"}:
                        missing["agent1"].append(normalized)
                    elif normalized in {"generated_data", "requires_test_data", "field_values", "values"} or normalized.startswith("generated_data."):
                        missing["agent2"].append(normalized)
                    else:
                        missing["agent1"].append(normalized)

        if not isinstance(test_case, dict):
            return {k: list(dict.fromkeys(v)) for k, v in missing.items()}
        required_agent1 = [
            "application_url",
            "steps",
            "expected_results",
        ]
        for field in required_agent1:
            if not test_case.get(field):
                missing["agent1"].append(field)
        if isinstance(test_case.get("steps"), list):
            for index, step in enumerate(test_case["steps"], start=1):
                if isinstance(step, dict):
                    if not step.get("action"):
                        missing["agent1"].append(f"steps[{index}].action")
                    if not step.get("locator_type"):
                        missing["agent1"].append(f"steps[{index}].locator_type")
                    if not step.get("locator_value"):
                        missing["agent1"].append(f"steps[{index}].locator_value")
        if not isinstance(test_data, dict):
            return {k: list(dict.fromkeys(v)) for k, v in missing.items()}
        if test_data.get("requires_test_data") is not False and not test_data.get("generated_data"):
            missing["agent2"].append("generated_data")
        if isinstance(test_data.get("generated_data"), dict):
            for key, value in test_data["generated_data"].items():
                if value in (None, "", [], {}) or (isinstance(value, dict) and not value):
                    missing["agent2"].append(f"generated_data.{key}")
        return {k: list(dict.fromkeys(v)) for k, v in missing.items()}

    @staticmethod
    def _content_health(code: str) -> Dict[str, bool]:
        text = code or ""
        lowered = text.lower()
        return {
            "markdown": bool(re.search(r"```|```python|```py", text, flags=re.IGNORECASE)),
            "explanations": bool(re.search(r"\b(here is|this is|below is|the result|final version|script:|generated code)\b", lowered)),
            "html": bool(re.search(r"<html|<body|<div|<a\s|</?[a-z][^>]*>", text, flags=re.IGNORECASE)),
            "invalid_imports": bool(re.search(r"^\s*(import\s+time\b|from\s+selenium\s+import\s+\*|import\s+selenium\b)", text, flags=re.IGNORECASE | re.MULTILINE)),
            "incomplete_functions": bool(re.search(r"def\s+[a-zA-Z_][\w]*\s*\([^)]*\)\s*:\s*$", text, flags=re.MULTILINE)),
        }

    @staticmethod
    def _supplied_data_values(test_data: Dict[str, Any]) -> list[str]:
        """Extract all usable data values from test_data.
        
        Handles both nested structure (with generated_data key) and flattened structure.
        """
        values: list[str] = []

        def collect(item: Any) -> None:
            if isinstance(item, dict):
                for value in item.values():
                    collect(value)
            elif isinstance(item, list):
                for value in item:
                    collect(value)
            elif isinstance(item, (str, int, float)) and str(item).strip():
                values.append(str(item).strip())

        # First try nested structure (generated_data)
        generated_data = test_data.get("generated_data")
        if isinstance(generated_data, (dict, list)):
            collect(generated_data)
        
        # Also extract from flattened fields (exclude metadata keys)
        metadata_keys = {"scenario_id", "requires_test_data", "generated_data"}
        for key, value in test_data.items():
            if key not in metadata_keys:
                collect(value)
        
        extracted = list(dict.fromkeys(values))
        import logging
        _logger = logging.getLogger(__name__)
        _logger.debug("_supplied_data_values: test_data_keys=%s extracted_values=%s extracted_count=%d", 
                      list(test_data.keys()), extracted, len(extracted))
        return extracted

    @staticmethod
    def _required_field_values(
        test_case: Dict[str, Any], test_data: Dict[str, Any]
    ) -> Dict[str, list[str]]:
        """Map each input step to values from its matching Agent 2 field."""
        if not isinstance(test_case, dict) or not isinstance(test_data, dict):
            return {}
        generated_data = test_data.get("generated_data")
        if not isinstance(generated_data, dict):
            return {}

        scenario_type = str(test_case.get("test_type") or "functional").strip().lower()
        category_names = [scenario_type] if scenario_type in {
            "positive", "negative", "boundary", "validation"
        } else ["positive"]
        category_names.extend(
            name for name in ("positive", "negative", "boundary", "validation")
            if name not in category_names
        )
        categories = [
            generated_data.get(name)
            for name in category_names
            if isinstance(generated_data.get(name), dict)
            and generated_data.get(name)
        ]
        steps = test_case.get("test_steps") or test_case.get("steps") or []
        input_actions = {
            "enter_text", "input_text", "fill", "send_keys", "type_text", "set_value",
            "select_dropdown_option", "select_option", "select_dropdown", "upload_file", "upload",
        }
        required: Dict[str, list[str]] = {}
        for step in steps:
            if not isinstance(step, dict) or str(step.get("action") or "").strip().lower() not in input_actions:
                continue
            field_name = str(
                step.get("field_name") or step.get("element_name") or step.get("label") or ""
            ).strip()
            if not field_name:
                continue
            values: list[str] = []
            for category in categories:
                for key, raw_values in category.items():
                    if str(key).strip().casefold() != field_name.casefold():
                        continue
                    candidates = raw_values if isinstance(raw_values, list) else [raw_values]
                    values.extend(
                        str(value).strip()
                        for value in candidates
                        if isinstance(value, (str, int, float)) and str(value).strip()
                    )
            if values:
                required[field_name] = list(dict.fromkeys(values))
        return required

    @staticmethod
    def _supplied_locator_values(test_case: Dict[str, Any]) -> list[tuple[str, str]]:
        values = []
        placeholders = {"primary_content", "input_field", "submit_button", "navigation_link", "element", "application_url"}
        if not isinstance(test_case, dict):
            return values
        steps = test_case.get("test_steps") or test_case.get("steps") or []
        for step in steps:
            if isinstance(step, dict):
                value = step.get("locator_value") or step.get("selector") or step.get("target")
                if isinstance(value, str) and value.strip() and value.strip().lower() not in placeholders:
                    values.append((str(step.get("locator_type") or "").strip().lower(), value.strip()))
        step_values = set(values)
        mapping = test_case.get("mapping") or {}
        if isinstance(mapping, dict):
            radio_mapping = str(
                mapping.get("field_type") or mapping.get("element_type") or mapping.get("type") or ""
            ).casefold() == "radio"
            mapped_values = []
            for key in ("id", "name", "data-testid", "data_testid", "href", "selector", "css_selector", "xpath"):
                value = mapping.get(key)
                if isinstance(value, str) and value.strip() and value.strip().lower() not in placeholders:
                    normalized_value = value.strip()
                    mapped_values.append((key, normalized_value))
            if radio_mapping and mapped_values:
                # Agent 1's mapping identifies the selected radio target. Do not
                # require stale sibling option ids left in a legacy step copy.
                values = [item for item in values if item in mapped_values]
                values.extend(mapped_values)
            else:
                for item in mapped_values:
                    if not step_values or item[1] in {step_value for _, step_value in values}:
                        values.append(item)
        return list(dict.fromkeys(values))
    
    @staticmethod
    def _navigation_locator_values(test_case: Dict[str, Any]) -> list[tuple[str, str]]:
        """Return only locators that are executable parts of navigation."""
        values = []
        steps = GeminiService._navigation_steps(test_case)
        for step in steps:
            if not isinstance(step, dict):
                continue
            locator_type = str(step.get("locator_type") or "").strip().lower()
            locator = str(step.get("locator_value") or step.get("selector") or step.get("target") or "").strip()
            if locator_type and locator:
                values.append((locator_type, locator))
        mapping = test_case.get("mapping") or {}
        if isinstance(mapping, dict) and mapping.get("href"):
            values.append(("href", str(mapping["href"]).strip()))
        destination_locator = GeminiService._navigation_destination_locator(test_case)
        if destination_locator:
            values.append(destination_locator)
        return list(dict.fromkeys(values))

    @staticmethod
    def _navigation_steps(test_case: Dict[str, Any]) -> list[dict[str, Any]]:
        steps = test_case.get("test_steps") or test_case.get("steps") or []
        if not isinstance(steps, list):
            return []
        navigation_actions = {
            "click", "click_element", "open_url", "navigate", "navigate_to",
            "verify_element_visible", "verify_visible", "assert_visible", "locate",
        }
        destination_terms = ("destination", "page", "heading", "loaded", "loads", "visible", "present")
        return [
            step for step in steps
            if isinstance(step, dict)
            and (
                str(step.get("action") or "").strip().lower() in {
                    "click", "click_element", "open_url", "navigate", "navigate_to"
                }
                or (
                    str(step.get("action") or "").strip().lower() in navigation_actions
                    and any(term in f"{step.get('description') or ''} {step.get('element_name') or ''}".casefold() for term in destination_terms)
                )
            )
        ]

    @staticmethod
    def _locator_appears_in_code(locator_type: str, locator: str, code: str) -> bool:
        if locator_type == "href":
            return f"a[href='{locator}']" in code or f'a[href="{locator}"]' in code
        if locator in code:
            return True
        if locator_type in {"id", "name", "data-testid", "data_testid"}:
            if re.search(rf"[\"']{re.escape(locator)}[\"']", code):
                return True
            # Hidden radio/checkbox inputs are legitimately activated through
            # their supplied associated label rather than the input element.
            return bool(re.search(
                rf"label\s*\[\s*for\s*=\s*[\"']{re.escape(locator)}[\"']\s*\]",
                code,
                flags=re.IGNORECASE,
            ))
        return False

    @staticmethod
    def _extract_text(body: Dict[str, Any]) -> str:
        candidates = body.get("candidates") or []
        if not candidates or not isinstance(candidates[0], dict):
            return ""
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        return "\n".join(
            part.get("text", "") for part in parts if isinstance(part, dict)
        ).strip()

    @classmethod
    def _sanitize_input(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: cls._sanitize_input(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._sanitize_input(item) for item in value]
        if not isinstance(value, str):
            return value

        cleaned = html.unescape(value)
        href_match = re.search(r"href\s*=\s*[\"']?([^\s\"'<>]+)", cleaned, re.IGNORECASE)
        if href_match:
            cleaned = href_match.group(1)
        cleaned = re.sub(r"<a\b[^>]*>(.*?)</a>", r"\1", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        cleaned = html.unescape(cleaned).strip()
        if re.match(r"^https?://", cleaned, re.IGNORECASE):
            match = re.match(r'^(https?://[^\s<>"\']+)', cleaned, re.IGNORECASE)
            if match:
                cleaned = match.group(1)
            cleaned = re.sub(r"(https?://localhost:\d+)(?:calhost:\d+)+", r"\1", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"(https?://[^/]+)(?:https?://.*)$", r"\1", cleaned, flags=re.IGNORECASE)
        return cleaned

    @staticmethod
    def _repair_malformed_escapes(code: str) -> str:
        def replace_quoted_string(match: re.Match[str]) -> str:
            quote = match.group(1)
            body = match.group(2)
            if any(token in body for token in (r"\U", r"\u", r"\x", r"\N")):
                return f"r{quote}{body}{quote}"
            return match.group(0)

        repaired = re.sub(
            r"([\"'])(.*?)(\1)",
            replace_quoted_string,
            code,
            flags=re.DOTALL,
        )
        return repaired

    @staticmethod
    def _extract_python_code(code: str) -> str:
        if not code:
            return ""

        text = str(code).strip()
        candidates: list[str] = []
        fenced = re.findall(r"```(?:python)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        for candidate in fenced:
            candidate = candidate.strip()
            if candidate:
                candidates.append(candidate)

        if not candidates:
            candidates.append(text)

        python_markers = (
            r"^\s*from\s+selenium\b",
            r"^\s*import\s+pytest\b",
            r"^\s*from\s+webdriver_manager\b",
            r"^\s*from\s+selenium\.webdriver\b",
            r"^\s*def\s+test_",
            r"^\s*class\s+Test",
            r"^\s*driver\s*=",
            r"^\s*browser\s*=",
            r"^\s*assert\s+",
        )

        for candidate in candidates:
            cleaned = candidate.strip()
            cleaned = re.sub(r"^\s*```(?:python)?\s*|\s*```\s*$", "", cleaned, flags=re.IGNORECASE)
            lines = cleaned.splitlines()

            start_index = None
            for idx, line in enumerate(lines):
                if any(re.match(pattern, line, flags=re.IGNORECASE) for pattern in python_markers):
                    start_index = idx
                    break
            if start_index is not None:
                lines = lines[start_index:]

            candidate_valid = []
            for end in range(len(lines), 0, -1):
                segment = "\n".join(lines[:end]).strip()
                if not segment:
                    continue
                for possible in (segment, GeminiService._repair_malformed_escapes(segment)):
                    try:
                        ast.parse(possible)
                        candidate_valid.append(possible)
                        break
                    except SyntaxError:
                        continue

            if candidate_valid:
                return max(candidate_valid, key=len)

            if lines:
                return "\n".join(lines).strip()

        return re.sub(r"^\s*```(?:python)?\s*|\s*```\s*$", "", text, flags=re.IGNORECASE)

    @staticmethod
    def _validate_code(
        code: str,
        test_case: Dict[str, Any],
        test_data: Dict[str, Any],
        enforce_fixtures: bool = False,
    ) -> str:
        raw_code = code
        if not code:
            raise GeminiServiceError("Gemini returned no Selenium code")

        cleaned_code = str(code).strip()
        if cleaned_code.startswith("ERROR:"):
            LOGGER.warning(
                "Gemini validation result=%s response_type=metadata_error missing_metadata_details=%s",
                "error",
                GeminiService._describe_missing_metadata(test_case, test_data),
            )
            raise GeminiServiceError(cleaned_code)

        extracted = GeminiService._extract_python_code(code)
        LOGGER.warning("Gemini extracted python preview (first 2000 chars): %s", extracted[:2000])
        code = extracted
        if not code:
            raise GeminiServiceError("Gemini returned no Selenium code")
        code = GeminiService._repair_generic_navigation_locators(code, test_case)
        lowered = code.lower()
        health = GeminiService._content_health(code)
        LOGGER.warning(
            "Gemini validation analysis: markdown=%s explanations=%s html=%s invalid_imports=%s incomplete_functions=%s",
            health["markdown"],
            health["explanations"],
            health["html"],
            health["invalid_imports"],
            health["incomplete_functions"],
        )
        if any(token in lowered for token in ("<html", "time.sleep(")):
            error = "Gemini returned code containing markup, forbidden waits, or placeholder identifiers"
            LOGGER.error("Exact validation failure: %s", error)
            raise GeminiServiceError(error)
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            syntax_error = f"Gemini returned syntactically invalid Python: {exc.msg}"
            LOGGER.error("Exact validation failure: %s", syntax_error)
            LOGGER.error("Python syntax error: %s", exc)
            repaired = GeminiService._repair_malformed_escapes(code)
            if repaired != code:
                try:
                    tree = ast.parse(repaired)
                    code = repaired
                except SyntaxError as repaired_exc:
                    LOGGER.error("Python syntax error after repair: %s", repaired_exc)
                    raise GeminiServiceError(syntax_error) from exc
            else:
                raise GeminiServiceError(syntax_error) from exc
        url_error = GeminiService._url_literal_error(tree)
        if url_error:
            LOGGER.error("Exact URL validation failure: %s", url_error)
            raise GeminiServiceError(url_error)
        if enforce_fixtures:
            fixture_error = GeminiService._fixture_contract_error(tree, code)
            if fixture_error:
                LOGGER.error("Exact fixture validation failure: %s", fixture_error)
                raise GeminiServiceError(fixture_error)
        placeholders = {"element", "input_field", "submit_button", "navigation_link", "primary_content"}
        identifiers = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
        }
        identifiers.update(
            node.arg
            for node in ast.walk(tree)
            if isinstance(node, ast.arg)
        )
        placeholder_identifiers = identifiers & placeholders
        locator_bound_names = {
            target.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr in {"find_element", "until"}
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        # ``element`` is acceptable when it is demonstrably bound to a real
        # Selenium lookup; an unbound generic placeholder remains invalid.
        placeholder_identifiers -= placeholder_identifiers & locator_bound_names
        helper_parameter_names = {
            argument.arg
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith("test_")
            and any(token in node.name.casefold() for token in ("click", "select", "check", "uncheck", "input", "type", "upload", "verify", "assert"))
            for argument in node.args.args
        }
        placeholder_identifiers -= placeholder_identifiers & helper_parameter_names
        placeholder_strings = {
            node.value.strip().lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.strip().lower() in placeholders
        }
        if placeholder_identifiers or placeholder_strings:
            offending = sorted(placeholder_identifiers | placeholder_strings)
            error = f"Gemini returned code containing placeholder identifiers: {offending}"
            LOGGER.error(
                "Exact validation failure: %s identifiers=%s strings=%s",
                error,
                sorted(placeholder_identifiers),
                sorted(placeholder_strings),
            )
            raise GeminiServiceError(error)

        locator_values = GeminiService._supplied_locator_values(test_case)
        if GeminiService._is_navigation_scenario(test_case):
            locator_values = GeminiService._navigation_locator_values(test_case)
        missing_locator_values = [
            locator
            for locator_type, locator in dict.fromkeys(locator_values)
            if not GeminiService._locator_appears_in_code(locator_type, locator, code)
        ]
        if missing_locator_values:
            warning = f"Generated code did not use optional or stale supplied locators: {missing_locator_values}"
            LOGGER.warning("Non-blocking locator validation: %s", warning)
        supplied_values = GeminiService._supplied_data_values(test_data)
        if supplied_values and not any(value in code for value in supplied_values):
            error = "Generated code does not use supplied test data"
            LOGGER.error("Exact validation failure: %s", error)
            raise GeminiServiceError(error)
        required_field_values = GeminiService._required_field_values(test_case, test_data)
        missing_field_values = [
            field_name
            for field_name, values in required_field_values.items()
            if values and not any(value in code for value in values)
        ]
        if missing_field_values:
            error = f"Generated code does not use supplied values for fields: {missing_field_values}"
            LOGGER.error("Exact validation failure: %s", error)
            raise GeminiServiceError(error)
        if any(value.lower() in {"sample", "test", "value"} for value in supplied_values):
            error = "Generated code uses placeholder test data"
            LOGGER.error("Exact validation failure: %s", error)
            raise GeminiServiceError(error)
        alignment_error = GeminiService._scenario_code_alignment_error(code, test_case)
        if alignment_error:
            LOGGER.error("Exact scenario alignment failure: %s", alignment_error)
            raise GeminiServiceError(alignment_error)
        unlisted_locator_errors = GeminiService._unlisted_locator_errors(test_case, code)
        if unlisted_locator_errors:
            error = unlisted_locator_errors[0]
            LOGGER.error("Exact validation failure: %s", error)
            raise GeminiServiceError(error)
        coverage_error = GeminiService._scenario_coverage_error(code, tree, test_case)
        if coverage_error:
            LOGGER.error("Exact scenario coverage failure: %s", coverage_error)
            raise GeminiServiceError(coverage_error)
        return code

    @staticmethod
    def _repair_generic_navigation_locators(code: str, test_case: Dict[str, Any]) -> str:
        """Replace recoverable generic navigation anchors with supplied metadata locators."""
        if not isinstance(test_case, dict) or not GeminiService._is_navigation_scenario(test_case):
            return code
        mapping = test_case.get("mapping") or {}
        mapping = mapping if isinstance(mapping, dict) else {}
        preferred = GeminiService._navigation_preferred_metadata(test_case)
        href = str(preferred.get("href") or "").strip()
        if not href:
            for mapping_key in ("selector", "css_selector", "locator_value", "target"):
                mapping_selector = str(mapping.get(mapping_key) or "")
                href_match = re.search(
                    r"a\s*\[\s*href\s*=\s*[\"']([^\"']+)[\"']\s*\]",
                    mapping_selector,
                    flags=re.IGNORECASE,
                )
                if href_match:
                    href = href_match.group(1).strip()
                    break
        exact_text = str(preferred.get("link_text") or preferred.get("text") or "").strip()
        partial_text = str(preferred.get("partial_link_text") or preferred.get("partial_text") or "").strip()
        dom_links = GeminiService._dom_links(test_case)
        dom_link_texts = GeminiService._dom_link_texts(test_case)
        if exact_text and exact_text.casefold() not in dom_link_texts:
            exact_text = ""
        if partial_text and not any(partial_text.casefold() in text for text in dom_link_texts):
            partial_text = ""
        steps = test_case.get("test_steps") or test_case.get("steps") or []
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                action = str(step.get("action") or "").casefold()
                if action not in {"click", "click_element", "navigate", "navigate_to", "open_url"}:
                    continue
                if not href:
                    href = str(step.get("href") or "").strip()
                if not href:
                    supplied_selector = str(
                        step.get("locator_value") or step.get("selector") or step.get("target") or ""
                    )
                    href_match = re.search(
                        r"a\s*\[\s*href\s*=\s*[\"']([^\"']+)[\"']\s*\]",
                        supplied_selector,
                        flags=re.IGNORECASE,
                    )
                    if href_match:
                        href = href_match.group(1).strip()
                if not href:
                    candidate_text = str(
                        step.get("link_text") or step.get("element_name") or step.get("text") or ""
                    ).strip().casefold()
                    for link in dom_links:
                        if candidate_text and str(link.get("text") or "").strip().casefold() == candidate_text:
                            href = str(link.get("href") or "").strip()
                            if href:
                                break
                if not exact_text:
                    candidate_text = str(
                        step.get("link_text") or step.get("element_name") or step.get("text") or ""
                    ).strip()
                    if candidate_text.casefold() in dom_link_texts:
                        exact_text = candidate_text
                if not partial_text:
                    candidate_partial = str(step.get("partial_link_text") or step.get("partial_text") or "").strip()
                    if any(candidate_partial.casefold() in text for text in dom_link_texts):
                        partial_text = candidate_partial
                if href or exact_text or partial_text:
                    break
        if not href:
            for evidence in GeminiService._navigation_url_evidence(test_case):
                if evidence.startswith(("/", "http://", "https://")):
                    href = evidence
                    break
        if href:
            replacement = f'a[href="{href}"]'
            selector_literal = f"'{replacement}'"
            code = re.sub(
                r"By\.TAG_NAME\s*(?:,|\()\s*([\"'])a\1\)?",
                f"By.CSS_SELECTOR, {selector_literal}",
                code,
                flags=re.IGNORECASE,
            )
            code = re.sub(
                r"([\"'])a\.router-link\1",
                selector_literal,
                code,
                flags=re.IGNORECASE,
            )
            code = re.sub(
                r"([\"'])a\1",
                selector_literal,
                code,
                flags=re.IGNORECASE,
            )
            code = re.sub(
                r"(By\.CSS_SELECTOR\s*,\s*)([\"'])(?:a|a\.router-link)(?:\2)",
                rf"\1{selector_literal}",
                code,
                flags=re.IGNORECASE,
            )
            code = re.sub(
                r"By\.TAG_NAME\s*(?:,|\()\s*([\"'])a\1\)?",
                f"By.CSS_SELECTOR, {selector_literal}",
                code,
                flags=re.IGNORECASE,
            )
        elif exact_text:
            code = re.sub(
                r"By\.TAG_NAME\s*(?:,|\()\s*([\"'])a\1\)?",
                f'By.LINK_TEXT, "{exact_text}"',
                code,
                flags=re.IGNORECASE,
            )
            code = re.sub(
                r"By\.CSS_SELECTOR\s*,\s*([\"'])(?:a|a\.router-link)\1",
                f'By.LINK_TEXT, "{exact_text}"',
                code,
                flags=re.IGNORECASE,
            )
            code = re.sub(
                r"By\.TAG_NAME\s*(?:,|\()\s*([\"'])a\1\)?",
                f'By.LINK_TEXT, "{exact_text}"',
                code,
                flags=re.IGNORECASE,
            )
        elif partial_text:
            code = re.sub(
                r"By\.TAG_NAME\s*(?:,|\()\s*([\"'])a\1\)?",
                f'By.PARTIAL_LINK_TEXT, "{partial_text}"',
                code,
                flags=re.IGNORECASE,
            )
            code = re.sub(
                r"By\.CSS_SELECTOR\s*,\s*([\"'])(?:a|a\.router-link)\1",
                f'By.PARTIAL_LINK_TEXT, "{partial_text}"',
                code,
                flags=re.IGNORECASE,
            )
            code = re.sub(
                r"By\.TAG_NAME\s*(?:,|\()\s*([\"'])a\1\)?",
                f'By.PARTIAL_LINK_TEXT, "{partial_text}"',
                code,
                flags=re.IGNORECASE,
            )
        return code

    @staticmethod
    def _navigation_preferred_metadata(test_case: Dict[str, Any]) -> dict[str, str]:
        """Collect the first navigation-specific href/text metadata across nested contracts."""
        result: dict[str, str] = {}
        navigation_keys = {"href", "link_text", "link_text_value", "partial_link_text", "partial_text"}

        def visit(value: Any) -> None:
            if result.get("href") and (result.get("link_text") or result.get("text")):
                return
            if isinstance(value, dict):
                for key in navigation_keys:
                    candidate = value.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        normalized_key = "link_text" if key in {"link_text_value", "text"} else key
                        result.setdefault(normalized_key, candidate.strip())
                for key, child in value.items():
                    if key in {"test_data", "generated_data"}:
                        continue
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(test_case.get("mapping"))
        visit(test_case.get("navigation"))
        visit(test_case.get("test_steps") or test_case.get("steps"))
        visit(test_case.get("page_metadata"))
        visit(test_case.get("dom_metadata"))
        visit(test_case.get("links"))
        visit(test_case.get("agent_1_contract"))
        visit(test_case.get("agent_3_input"))
        return result

    @staticmethod
    def _dom_links(test_case: Dict[str, Any]) -> list[dict[str, Any]]:
        """Return supplied extracted DOM link records."""
        if not isinstance(test_case, dict):
            return []
        sources = [test_case.get("page_metadata"), test_case.get("dom_metadata")]
        if isinstance(test_case.get("links"), list):
            sources.append(test_case["links"])
        links: list[dict[str, Any]] = []
        for source in sources:
            records = source.get("links") if isinstance(source, dict) else source
            if not isinstance(records, list):
                continue
            links.extend(record for record in records if isinstance(record, dict))
        return links

    @staticmethod
    def _dom_link_texts(test_case: Dict[str, Any]) -> set[str]:
        """Return normalized visible link text from supplied extracted DOM metadata."""
        texts: set[str] = set()
        if not isinstance(test_case, dict):
            return texts
        sources = [test_case.get("page_metadata"), test_case.get("dom_metadata"), test_case.get("mapping")]
        sources.extend(test_case.get("links") or [] if isinstance(test_case.get("links"), list) else [])
        for source in sources:
            links = source.get("links") if isinstance(source, dict) else source
            if not isinstance(links, list):
                continue
            for link in links:
                if not isinstance(link, dict):
                    continue
                text = str(link.get("text") or link.get("link_text") or "").strip()
                if text:
                    texts.add(text.casefold())
        return texts

    @staticmethod
    def _url_literal_error(tree: ast.AST) -> str | None:
        """Reject HTML or attribute markup when it is used as a URL value."""
        url_call_names = {"get", "url_changes", "url_contains", "url_matches"}
        forbidden_patterns = (
            (r"<\s*a\b", "<a"),
            (r"</\s*a\s*>", "</a>"),
            (r"\bhref\s*=", "href="),
            (r"\btarget\s*=", "target="),
            (r"\brel\s*=", "rel="),
            (r"\btitle\s*=", "title="),
        )

        def check(value: str) -> str | None:
            if "<" in value or ">" in value:
                return "HTML or malformed URL"
            for pattern, label in forbidden_patterns:
                if re.search(pattern, value, flags=re.IGNORECASE):
                    return label
            if re.search(r"<\s*/?[a-z][^>]*>", value, flags=re.IGNORECASE):
                return "HTML tag"
            return None

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in url_call_names or not node.args:
                continue
            value = node.args[0]
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                marker = check(value.value)
                if marker:
                    return f"Generated code is not aligned with URL behavior: generated URL contains forbidden {marker} markup. Use a plain URL string."

        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            comparison_text = ast.unparse(node).casefold()
            if "current_url" not in comparison_text:
                continue
            for constant in ast.walk(node):
                if isinstance(constant, ast.Constant) and isinstance(constant.value, str):
                    marker = check(constant.value)
                    if marker:
                        return f"Generated code is not aligned with URL behavior: generated URL assertion contains forbidden {marker} markup. Use a plain URL string."
        return None

    @staticmethod
    def _fixture_contract_error(tree: ast.AST, source: str) -> str | None:
        """Validate fixtures in generated Selenium files before pytest collection."""
        fixture_names: set[str] = set()
        fixture_functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        test_functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

        def is_pytest_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
                    return True
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "fixture":
                    return True
                if isinstance(decorator, ast.Name) and decorator.id == "fixture":
                    return True
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == "fixture":
                    return True
            return False

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("test_"):
                test_functions.append(node)
            if is_pytest_fixture(node):
                fixture_names.add(node.name)
                fixture_functions[node.name] = node

        used_fixtures = {
            argument.arg
            for test in test_functions
            for argument in (*test.args.posonlyargs, *test.args.args, *test.args.kwonlyargs)
            if argument.arg != "self"
        }
        missing = sorted(used_fixtures - fixture_names)
        if missing:
            return f"Generated Selenium code uses undefined pytest fixtures: {missing}"
        if not test_functions:
            return "Generated Selenium code does not define a pytest test function."
        if any(name in used_fixtures for name in {"page", "browser", "context"}):
            return "Generated Selenium code mixes Selenium with Playwright fixtures."
        if re.search(r"\b(?:playwright|sync_playwright|async_playwright)\b", source, flags=re.IGNORECASE):
            return "Generated Selenium code mixes Selenium with Playwright APIs."
        if "driver" not in used_fixtures:
            return "Generated Selenium code must use the Selenium driver fixture."
        if "pytest" not in source or not re.search(
            r"from\s+selenium(?:\.webdriver)?\s+import\s+webdriver",
            source,
        ):
            return "Generated Selenium code is missing pytest or Selenium webdriver imports."

        driver_fixture = fixture_functions.get("driver")
        if driver_fixture is None:
            return "Generated Selenium code must define @pytest.fixture def driver()."
        fixture_source = ast.get_source_segment(source, driver_fixture) or ""
        if not re.search(r"webdriver\.Chrome\s*\(", fixture_source):
            return "Selenium driver fixture must create webdriver.Chrome()."
        if not any(isinstance(node, ast.Yield) for node in ast.walk(driver_fixture)):
            return "Selenium driver fixture must yield the driver for teardown."
        if not re.search(r"\bdriver\.quit\s*\(", fixture_source):
            return "Selenium driver fixture must call driver.quit() during teardown."
        return None

    @staticmethod
    def _scenario_coverage_error(code: str, tree: ast.AST, test_case: Dict[str, Any]) -> str | None:
        """Reject scripts that cover only part of the scenario contract."""
        if not isinstance(test_case, dict) or not test_case:
            return None
        steps = test_case.get("test_steps") or test_case.get("steps") or []
        if GeminiService._is_navigation_scenario(test_case):
            steps = GeminiService._navigation_steps(test_case)
        expected_results = test_case.get("expected_results") or test_case.get("expected_result") or []
        if isinstance(expected_results, str):
            expected_results = [expected_results]
        if not isinstance(steps, list):
            return "Generated code cannot be validated because scenario steps are not a list."
        if not isinstance(expected_results, list):
            return "Generated code cannot be validated because expected results are not a list."

        test_functions = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        flow_nodes = test_functions or [tree]
        assertion_count = sum(
            1 for flow in flow_nodes for node in ast.walk(flow) if isinstance(node, ast.Assert)
        )
        source = str(code or "").casefold()
        click_helper_names = {
            node.name.casefold()
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and "click" in node.name.casefold()
        }
        click_invocations = source.count(".click(") + sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id.casefold() in click_helper_names
        )
        if re.search(r"driver\.get\s*\(\s*[\"'][^\"']*<[^\"']*[\"']\s*\)", source):
            return "Generated code is not aligned with URL behavior: driver.get() must receive a raw executable URL, not HTML markup."
        missing_locators = []
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            locator_type = str(step.get("locator_type") or "").strip().lower()
            locator = str(
                step.get("locator_value") or step.get("selector") or step.get("target") or ""
            ).strip()
            if (
                locator_type in {"url", "title"}
                or locator.casefold() in {"application_url", "app_url", "base_url"}
                or not locator
            ):
                continue
            if GeminiService._step_locator_is_superseded_by_mapping(test_case, step):
                continue
            if not GeminiService._locator_appears_in_code(locator_type, locator, code) and not GeminiService._more_specific_locator_covers_step(test_case, step, code):
                missing_locators.append(f"steps[{index}]={locator}")
        if missing_locators:
            return (
                "Generated code does not use every supplied scenario locator: "
                + ", ".join(missing_locators)
            )
        covered_steps = sum(
            1 for step in steps
            if GeminiService._scenario_step_is_covered(step, source)
        )
        automation_actions = covered_steps
        step_coverage = (
            100.0 if not steps else (automation_actions / len(steps)) * 100.0
        )
        assertion_coverage = (
            100.0 if not expected_results
            else (min(assertion_count, len(expected_results)) / len(expected_results)) * 100.0
        )
        LOGGER.info(
            "Agent3 scenario coverage: scenario_steps=%d automation_actions=%d step_coverage=%.1f%% expected_results=%d assertions=%d assertion_coverage=%.1f%% raw_assertions=%d",
            len(steps),
            automation_actions,
            step_coverage,
            len(expected_results),
            min(assertion_count, len(expected_results)),
            assertion_coverage,
            assertion_count,
        )
        if automation_actions != len(steps):
            return (
                "Generated code covers an incomplete scenario: "
                f"scenario_steps={len(steps)} automation_actions={automation_actions}."
            )
        if assertion_count < len(expected_results):
            return (
                "Generated code covers an incomplete scenario: "
                f"expected_results={len(expected_results)} assertions={assertion_count}."
            )

        for index, step in enumerate(steps, start=1):
            description = str(step.get("description") or step.get("action") or "").casefold() if isinstance(step, dict) else str(step).casefold()
            if any(token in description for token in ("deselect", "uncheck", "unchecked")) and click_invocations < 2:
                return f"Generated code omits checkbox deselection step {index}."
            if any(token in description for token in ("maximum + 1", "out-of-bound", "out of bound", "beyond the boundary")) and source.count("send_keys(") < 3:
                return f"Generated code omits boundary probe step {index}."
        return None

    @staticmethod
    def _more_specific_locator_covers_step(
        test_case: Dict[str, Any], step: Dict[str, Any], code: str
    ) -> bool:
        """Accept a precise same-element locator in place of a generic supplied locator."""
        supplied = str(
            step.get("locator_value") or step.get("selector") or step.get("target") or ""
        ).casefold().strip()
        generic_values = {"a", "a.router-link", "div", "span"}
        if supplied not in generic_values:
            return False
        mapping = test_case.get("mapping") or {}
        if not isinstance(mapping, dict):
            mapping = {}
        candidates = (
            ("href", mapping.get("href")),
            ("id", mapping.get("id")),
            ("name", mapping.get("name")),
            ("link_text", mapping.get("link_text") or mapping.get("link_text_value") or mapping.get("text")),
            ("partial_link_text", mapping.get("partial_link_text") or mapping.get("partial_text")),
            ("label", mapping.get("label")),
        )
        candidate_values = list(candidates)
        steps = test_case.get("test_steps") or test_case.get("steps") or []
        if isinstance(steps, list):
            for navigation_step in steps:
                if not isinstance(navigation_step, dict):
                    continue
                action = str(navigation_step.get("action") or "").casefold()
                if action not in {"click", "click_element", "navigate", "navigate_to", "open_url"}:
                    continue
                candidate_values.extend((
                    ("href", navigation_step.get("href")),
                    ("id", navigation_step.get("id")),
                    ("name", navigation_step.get("name")),
                    ("link_text", navigation_step.get("link_text") or navigation_step.get("element_name") or navigation_step.get("text")),
                    ("partial_link_text", navigation_step.get("partial_link_text") or navigation_step.get("partial_text")),
                ))
        for locator_type, value in candidate_values:
            value = str(value or "").strip()
            if not value:
                continue
            if locator_type == "href" and GeminiService._locator_appears_in_code("href", value, code):
                return True
            if locator_type in {"id", "name"} and GeminiService._locator_appears_in_code(locator_type, value, code):
                return True
            if locator_type == "link_text" and re.search(
                rf"By\.LINK_TEXT\s*,\s*[\"']{re.escape(value)}[\"']", code, flags=re.IGNORECASE
            ):
                return True
            if locator_type == "partial_link_text" and re.search(
                rf"By\.PARTIAL_LINK_TEXT\s*,\s*[\"']{re.escape(value)}[\"']", code, flags=re.IGNORECASE
            ):
                return True
            if locator_type == "label" and value.casefold() in code.casefold():
                return True
        return False

    @staticmethod
    def _step_locator_is_superseded_by_mapping(
        test_case: Dict[str, Any], step: Dict[str, Any]
    ) -> bool:
        mapping = test_case.get("mapping") or {}
        mapping_type = str(
            mapping.get("field_type") or mapping.get("element_type") or mapping.get("type") or ""
        ).casefold() if isinstance(mapping, dict) else ""
        if mapping_type != "radio" or not isinstance(mapping, dict):
            return False
        mapped_locator = str(
            mapping.get("id") or mapping.get("selector") or mapping.get("css_selector") or ""
        ).strip()
        step_locator = str(
            step.get("locator_value") or step.get("selector") or step.get("target") or ""
        ).strip()
        return bool(mapped_locator and step_locator and mapped_locator != step_locator)

    @staticmethod
    def _scenario_step_is_covered(step: Any, source: str) -> bool:
        """Match one scenario step to its high-level Selenium implementation."""
        description = str(
            step.get("description") or step.get("action") or ""
        ).casefold() if isinstance(step, dict) else str(step).casefold()
        if any(token in description for token in ("deselect", "uncheck", "unchecked")):
            return source.count(".click(") >= 2 or source.count("click(") >= 2
        if any(token in description for token in ("select", "click", "submit", "upload")):
            return any(token in source for token in (".click(", "click(", "select_by", "submit(", "upload"))
        if any(token in description for token in ("enter", "type", "input", "send")):
            return "send_keys(" in source
        if any(token in description for token in ("selected", "checked", "deselected", "unchecked")):
            return any(token in source for token in ("is_selected", "checked", "aria-checked", "selected"))
        if any(token in description for token in ("visible", "enabled", "locate", "present")):
            return any(token in source for token in ("find_element", "is_displayed", "is_enabled", "visibility_of", "presence_of"))
        if any(token in description for token in ("verify", "assert", "validation", "error", "accepted", "rejected", "restricted")):
            return "assert " in source or "assert(" in source
        return bool(source)

    @staticmethod
    def _is_navigation_scenario(test_case: Dict[str, Any]) -> bool:
        if not isinstance(test_case, dict):
            return False
        mapping = test_case.get("mapping") or {}
        if isinstance(mapping, dict) and str(mapping.get("href") or "").strip():
            return True
        title = str(test_case.get("title") or test_case.get("description") or "").casefold()
        test_type = str(test_case.get("test_type") or "").casefold()
        steps = test_case.get("test_steps") or test_case.get("steps") or []
        step_text = " ".join(
            str(step.get("action") or step.get("description") or "")
            for step in steps
            if isinstance(step, dict)
        ).casefold()
        context = f"{title} {test_type} {step_text}"
        return test_type in {"navigation", "navigate"} or any(
            token in context for token in ("navigation", "navigate", "current_url", "destination")
        )

    @staticmethod
    def _navigation_url_evidence(test_case: Dict[str, Any]) -> list[str]:
        """Return supplied destination evidence that authorizes URL assertions."""
        if not isinstance(test_case, dict):
            return []

        evidence: list[str] = []
        mapping = test_case.get("mapping") or {}
        if isinstance(mapping, dict):
            for key in ("href", "url", "expected_url", "destination_url", "target_url", "navigation_target"):
                value = mapping.get(key)
                if isinstance(value, str) and value.strip():
                    evidence.append(value.strip())

        for key in ("href", "url", "expected_url", "destination_url", "target_url", "navigation_target", "expected_destination_path"):
            value = test_case.get(key)
            if isinstance(value, str) and value.strip():
                evidence.append(value.strip())

        navigation = test_case.get("navigation")
        if isinstance(navigation, dict):
            for key in ("href", "url", "expected_url", "destination_url", "target_url", "path"):
                value = navigation.get(key)
                if isinstance(value, str) and value.strip():
                    evidence.append(value.strip())

        steps = test_case.get("test_steps") or test_case.get("steps") or []
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                for key in ("href", "url", "expected_url", "destination_url", "target_url", "navigation_target"):
                    value = step.get(key)
                    if isinstance(value, str) and value.strip():
                        evidence.append(value.strip())
                locator = str(step.get("locator_value") or step.get("selector") or "").strip()
                if re.search(r"(?:^|\s)href\s*=\s*[\"'][^\"']+[\"']", locator, flags=re.IGNORECASE):
                    evidence.append(locator)

        expected_results = test_case.get("expected_results") or test_case.get("expected_result") or []
        expected_text = " ".join(expected_results) if isinstance(expected_results, list) else str(expected_results)
        evidence.extend(re.findall(r"https?://[^\s)\]]+|/[A-Za-z0-9._~:/?#\[\]@!$&'*+,;=%-]+", expected_text))
        return list(dict.fromkeys(value.rstrip(".,") for value in evidence if value.strip()))

    @staticmethod
    def _scenario_code_alignment_error(code: str, test_case: Dict[str, Any]) -> str | None:
        """Ensure generated operations test the declared scenario behavior."""
        if not isinstance(test_case, dict) or not test_case:
            return None
        source = str(code or "").casefold()
        title = str(test_case.get("title") or test_case.get("description") or "").casefold()
        test_type = str(test_case.get("test_type") or "functional").casefold()
        mapping = test_case.get("mapping") or {}
        field_type = str(
            mapping.get("field_type") or mapping.get("element_type") or mapping.get("type") or ""
        ).casefold()
        steps = test_case.get("test_steps") or test_case.get("steps") or []
        step_text = " ".join(str(step.get("action") or "") for step in steps if isinstance(step, dict)).casefold()
        context = f"{title} {test_type} {field_type} {step_text}"

        is_navigation = GeminiService._is_navigation_scenario(test_case)
        if is_navigation:
            mapping = test_case.get("mapping") or {}
            navigation_evidence = GeminiService._navigation_url_evidence(test_case)
            preferred = GeminiService._navigation_preferred_metadata(test_case)
            mapping_href = str(preferred.get("href") or "").strip()
            exact_link_text = str(preferred.get("link_text") or preferred.get("text") or "").strip()
            partial_link_text = str(preferred.get("partial_link_text") or preferred.get("partial_text") or "").strip()
            generic_anchor_error = GeminiService._generic_navigation_locator_error(
                code,
                has_href=bool(mapping_href),
                has_link_text=bool(exact_link_text or partial_link_text),
                supplied_locator_count=len(GeminiService._navigation_locator_values(test_case)),
            )
            if generic_anchor_error:
                return generic_anchor_error
            if mapping_href and mapping_href.casefold() not in source:
                return "Generated code is not aligned with navigation behavior: mapping.href is not used for link selection."
            if mapping_href and not GeminiService._locator_appears_in_code("href", mapping_href, code):
                return "Generated code is not aligned with navigation behavior: href metadata requires an href-based locator, not a generic selector."
            if not mapping_href and exact_link_text and not re.search(
                rf"By\.LINK_TEXT\s*,\s*[\"']{re.escape(exact_link_text)}[\"']",
                code,
                flags=re.IGNORECASE,
            ):
                return "Generated code is not aligned with navigation behavior: supplied link text must be used as the navigation locator."
            if not mapping_href and not exact_link_text and partial_link_text and not re.search(
                rf"By\.PARTIAL_LINK_TEXT\s*,\s*[\"']{re.escape(partial_link_text)}[\"']",
                code,
                flags=re.IGNORECASE,
            ):
                return "Generated code is not aligned with navigation behavior: supplied partial link text must be used as the navigation locator."
            destination_locator = GeminiService._navigation_destination_locator(test_case)
            if navigation_evidence and not destination_locator:
                return "Generated code is not aligned with navigation behavior: destination page locator is required when URL navigation is asserted."
            navigation_locators = set()
            for step in GeminiService._navigation_steps(test_case):
                if not isinstance(step, dict):
                    continue
                action = str(step.get("action") or "").casefold()
                if action not in {"click", "click_element", "navigate", "navigate_to", "open_url"}:
                    continue
                locator = str(
                    step.get("locator_value") or step.get("selector") or step.get("target") or ""
                ).strip()
                if locator:
                    navigation_locators.add(locator)
            if mapping_href:
                navigation_locators.update({
                    f"a[href='{mapping_href}']",
                    f'a[href="{mapping_href}"]',
                })
            if destination_locator and destination_locator[1] in navigation_locators:
                return "Generated code is not aligned with navigation behavior: the original navigation link cannot validate destination page load."
            if destination_locator and not GeminiService._locator_appears_in_code(
                destination_locator[0], destination_locator[1], code
            ):
                return "Generated code is not aligned with navigation behavior: page-specific destination locator is not used."
            if not navigation_evidence and any(
                token in source for token in ("url_contains", "url_changes", "current_url")
            ):
                LOGGER.warning(
                    "Non-blocking navigation validation: generated URL assertion has no supplied destination evidence; "
                    "returning generated code without treating it as a generation error."
                )
            unrelated_locators = [
                locator for locator in GeminiService._selenium_locator_literals(code)
                if locator not in {
                    value for _, value in GeminiService._navigation_locator_values(test_case)
                }
                and locator != mapping_href
            ]
            if unrelated_locators:
                return (
                    "Generated code contains unrelated navigation locators: "
                    + ", ".join(sorted(set(unrelated_locators)))
                )
            required_navigation_signals = {
                "visibility": any(token in source for token in ("is_displayed", "visibility_of", "visibility_of_element_located")),
                "clickability": any(token in source for token in ("element_to_be_clickable", "is_enabled")),
                "click": ".click(" in source or "click(" in source,
                "navigation_wait": (
                    any(token in source for token in ("url_changes", "url_contains"))
                    if navigation_evidence
                    else bool(destination_locator and any(token in source for token in ("presence_of_element_located", "visibility_of_element_located")))
                ),
                "url_assertion": (
                    "current_url" in source and "assert" in source
                    if navigation_evidence
                    else True
                ),
                "destination_load": bool(destination_locator and any(token in source for token in ("presence_of_element_located", "visibility_of_element_located")))
                or "title" in source
                or (not navigation_evidence and "current_url" in source)
                or (navigation_evidence and "current_url" in source and "assert" in source),
            }
            missing_navigation_signals = [
                signal for signal, present in required_navigation_signals.items() if not present
            ]
            if missing_navigation_signals:
                if navigation_evidence:
                    return (
                        "Generated code is not aligned with navigation behavior: missing "
                        f"{', '.join(missing_navigation_signals)} verification."
                    )
                LOGGER.warning(
                    "Non-blocking navigation validation: unproven navigation is missing %s; "
                    "returning generated code.",
                    ", ".join(missing_navigation_signals),
                )
            expected_results = test_case.get("expected_results") or test_case.get("expected_result") or []
            expected_text = " ".join(expected_results) if isinstance(expected_results, list) else str(expected_results)
            destination_paths = re.findall(r"(?:https?://[^\s)\]]+|/[A-Za-z0-9._~:/?#\[\]@!$&'*+,;=%-]+)", expected_text)
            destination_paths = [path.rstrip(".,") for path in destination_paths]
            if navigation_evidence and destination_paths and not any(path.casefold() in source for path in destination_paths):
                return "Generated code is not aligned with navigation behavior: expected destination path is not asserted in driver.current_url."
            locator_values = [
                locator for _, locator in GeminiService._supplied_locator_values(test_case)
            ]
            if destination_locator and len(set(locator_values)) > 1 and sum(locator in code for locator in set(locator_values)) < 2:
                return "Generated code is not aligned with navigation behavior: destination page locator is not verified."

        is_non_text_control = any(token in context for token in ("radio", "checkbox", "dropdown"))
        if not is_non_text_control and (test_type == "boundary" or any(token in context for token in ("boundary", "maximum + 1", "minimum - 1", "max length"))):
            input_actions = len(re.findall(r"\bsend_keys\s*\(", source))
            assertion_count = len(re.findall(r"\bassert\b", source))
            boundary_terms = ("max", "min", "boundary", "limit", "length", "out_of_range", "over_limit")
            has_boundary_probe = any(token in source for token in boundary_terms)
            if input_actions < 3 or assertion_count < 2 or not has_boundary_probe:
                return "Generated code is not aligned with boundary behavior: expected separate minimum, maximum, and maximum + 1 probes with assertions."

        if test_type in {"validation", "negative"}:
            has_invalid_input = "send_keys" in source or "clear" in source
            has_trigger = any(token in source for token in (".click(", "click(", "submit(", "submit_form"))
            has_rejection = any(token in source for token in ("reject", "invalid", "prevent", "blocked", "not submit", "not be submitted", "aria-invalid"))
            has_feedback = any(token in source for token in ("validation", "error", "message", "is_displayed", "aria-invalid"))
            has_application_validation = any(token in source for token in ("validationmessage", "aria-invalid", "error", "invalid", "prevent", "blocked", "not submit"))
            if not has_invalid_input or not has_trigger or not has_rejection or not has_feedback or not has_application_validation or "assert" not in source:
                return (
                    f"Generated code is not aligned with {test_type} behavior: expected invalid input, "
                    "action trigger, rejection assertion, and validation-feedback assertion."
                )

        if test_type == "security" or "security" in context or any(token in context for token in ("xss", "sql injection", "unauthorized")):
            if not any(token in source for token in ("sanitize", "escape", "script", "injection", "alert", "security")) or "assert" not in source:
                return "Generated code is not aligned with security behavior: expected a security-specific check and assertion."

        if test_type == "accessibility" or "accessib" in context or "wcag" in context:
            if not any(token in source for token in ("aria", "role", "accessible", "label", "get_attribute")) or "assert" not in source:
                return "Generated code is not aligned with accessibility behavior: expected an accessibility-specific check and assertion."

        if "radio" in field_type or "radio" in context:
            if "send_keys" in source:
                return "Generated code is not aligned with radio behavior: text entry is forbidden."
            has_selection_action = any(token in source for token in (
                ".click(", "click(", "execute_script", "select_radio", "choose_radio",
                "select()", "element_to_be_selected",
            ))
            has_selection_state = any(token in source for token in (
                "is_selected", "element_to_be_selected", "selected", "checked",
                "aria-checked", "get_attribute", "get_property", "get_dom_attribute",
            ))
            if not has_selection_action or not has_selection_state:
                return "Generated code is not aligned with radio behavior: expected selection and selected-state verification."

        if "checkbox" in field_type or "checkbox" in context:
            if "send_keys" in source:
                return "Generated code is not aligned with checkbox behavior: text entry is forbidden."
            checkbox_error = GeminiService._checkbox_behavior_error(code, test_case)
            if checkbox_error:
                return checkbox_error

        if "dropdown" in field_type or "select" in field_type or "dropdown" in context:
            if "send_keys" in source:
                return "Generated code is not aligned with dropdown behavior: free-text entry is forbidden."
            if not any(token in source for token in ("select_by", "select(", "selected", "option")):
                return "Generated code is not aligned with dropdown behavior: expected option selection verification."

        if re.search(r"assert\s+(?:true|false)\s*$", source, flags=re.IGNORECASE | re.MULTILINE):
            return "Generated code contains a self-fulfilling assertion: assert True/False is not scenario validation."
        if re.search(r"assert\s+([a-z_][a-z0-9_]*)\s*==\s*\1\s*$", source, flags=re.IGNORECASE | re.MULTILINE):
            return "Generated code contains a self-fulfilling assertion: a value cannot validate itself."

        return None

    @staticmethod
    def _generic_navigation_locator_error(
        code: str,
        *,
        has_href: bool,
        has_link_text: bool,
        supplied_locator_count: int,
    ) -> str | None:
        """Reject broad anchor selectors for every navigation scenario."""

        if re.search(
            r"(?:CSS_SELECTOR\s*,\s*[\"'](?:a|a\.router-link)[\"']|TAG_NAME\s*,\s*[\"']a[\"'])",
            code,
            flags=re.IGNORECASE,
        ):
            return "Generated code is not aligned with navigation behavior: generic anchor locator is not allowed; use the supplied href or link text."

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"find_element", "find_elements"} or len(node.args) < 2:
                continue
            locator_value = node.args[1]
            if not isinstance(locator_value, ast.Constant) or not isinstance(locator_value.value, str):
                continue
            value = locator_value.value.casefold().strip()
            generic = value in {"a", "a.router-link"}
            if isinstance(node.args[0], ast.Attribute) and node.args[0].attr == "TAG_NAME" and value == "a":
                generic = True
            if generic:
                return "Generated code is not aligned with navigation behavior: generic anchor locator is not allowed; use the supplied href or link text."
        return None

    @staticmethod
    def _checkbox_behavior_error(code: str, test_case: Dict[str, Any]) -> str | None:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return "Generated code is not aligned with checkbox behavior: generated Python is not parseable."

        click_count = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "click"
        )
        click_helpers = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and "click" in node.name.casefold()
        }
        click_count += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in click_helpers
        )
        state_reads = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and (
                node.func.attr in {"is_selected", "is_displayed"}
                or (
                    node.func.attr in {"get_attribute", "get_property"}
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and str(node.args[0].value).casefold() in {"checked", "aria-checked", "selected"}
                )
            )
        )
        assertion_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.Assert))
        if click_count < 1 or state_reads < 1 or assertion_count < 1:
            return "Generated code is not aligned with checkbox behavior: expected a click and selected-state assertion."

        context = " ".join(
            [
                str(test_case.get("title") or ""),
                str(test_case.get("description") or ""),
                " ".join(str(result) for result in (test_case.get("expected_results") or [])),
                " ".join(str(step.get("description") or "") for step in (test_case.get("steps") or test_case.get("test_steps") or []) if isinstance(step, dict)),
            ]
        ).casefold()
        requires_deselect = any(token in context for token in ("deselect", "uncheck", "unchecked", "deselected"))
        if requires_deselect and click_count < 2:
            return "Generated code is not aligned with checkbox behavior: expected select and deselect state verification."
        if requires_deselect and state_reads < 2:
            return "Generated code is not aligned with checkbox behavior: expected state assertions after select and deselect."
        return None

    @staticmethod
    def _navigation_destination_locator(test_case: Dict[str, Any]) -> tuple[str, str] | None:
        mapping = test_case.get("mapping") or {}
        if isinstance(mapping, dict):
            for locator_type, key in (
                ("id", "destination_id"),
                ("css_selector", "destination_selector"),
                ("xpath", "destination_xpath"),
                ("id", "page_heading"),
                ("id", "unique_page_element"),
            ):
                value = str(mapping.get(key) or "").strip()
                if value:
                    return locator_type, value
            destination = mapping.get("destination_locator")
            if isinstance(destination, dict):
                locator_type = str(destination.get("locator_type") or "id").strip().lower()
                value = str(destination.get("locator_value") or "").strip()
                if locator_type and value:
                    return locator_type, value
        steps = GeminiService._navigation_steps(test_case)
        locators = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            description = str(step.get("description") or "").casefold()
            element_name = str(step.get("element_name") or step.get("field_name") or "").casefold()
            if not any(
                term in f"{description} {element_name}"
                for term in ("destination", "page heading", "unique page", "destination page")
            ):
                continue
            locator_type = str(step.get("locator_type") or "").strip().lower()
            value = str(step.get("locator_value") or step.get("selector") or "").strip()
            if locator_type and value:
                locators.append((locator_type, value))
        return locators[-1] if locators else None

    @staticmethod
    def _selenium_locator_literals(code: str) -> list[str]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        literals = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"find_element", "find_elements"} or len(node.args) < 2:
                continue
            locator = node.args[1]
            if isinstance(locator, ast.Constant) and isinstance(locator.value, str):
                literals.append(locator.value)
        return list(dict.fromkeys(literals))
