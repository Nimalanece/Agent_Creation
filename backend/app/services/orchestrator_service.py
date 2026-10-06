import logging
import re
from typing import Any, Dict, List, Set
from urllib.parse import urlparse

from app.services.url_analysis_service import analyze_url, URLAnalysisError
from app.services.scenarios_service import generate_scenarios
from app.services.testcases_service import generate_testcases
from app.core.groq_service import GroqServiceError, GroqService
from app.models.schemas import Agent1Contract, Agent1Feature, Agent1FeatureGroup, Agent1TestScenario, Agent1TestCase, Agent1TestStep, Agent2GenerationRequest, Agent2TestDataInput, Agent3SeleniumInput
from app.services.testdata_service import build_test_data_contract
from app.services.intent_classifier import extract_element_name as central_extract_element_name

LOGGER = logging.getLogger(__name__)


def _agent1_scenario_id(item: Any) -> str | None:
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


def _has_real_locator(mapping: Any) -> bool:
    if not isinstance(mapping, dict):
        return False
    placeholders = {"element", "input_field", "submit_button", "navigation_link", "primary_content", "form_input", "target_input"}
    for key in ("id", "name", "data-testid", "data_testid", "href", "selector", "css_selector", "xpath"):
        value = str(mapping.get(key) or "").strip()
        if value and value.lower() not in placeholders and not any(token in value.lower() for token in placeholders):
            return True
    return False


def _dom_locator(candidate: Dict[str, Any]) -> tuple[str, str]:
    """Return a locator only when it comes from analyzed DOM metadata."""
    if not isinstance(candidate, dict):
        return "", ""
    for key, locator_type in (
        ("id", "id"),
        ("name", "name"),
        ("data-testid", "data-testid"),
        ("data_testid", "data-testid"),
        ("selector", "css_selector"),
        ("css_selector", "css_selector"),
        ("xpath", "xpath"),
    ):
        value = str(candidate.get(key) or "").strip()
        visible_names = {
            str(candidate.get(name_key) or "").strip().casefold()
            for name_key in ("label", "text", "placeholder", "field_name", "element_name")
            if str(candidate.get(name_key) or "").strip()
        }
        if value.casefold() in visible_names:
            continue
        if value and value.casefold() not in {"element", "input_field", "submit_button", "navigation_link"}:
            return locator_type, value
    return "", ""


def _discovered_mapping_for_step(step: Dict[str, Any], test_case: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    existing = test_case.get("mapping") or {}
    if isinstance(existing, dict):
        locator_type, locator_value = _dom_locator(existing)
        if locator_type:
            return {**existing, "locator_type": locator_type, "locator_value": locator_value}

    action = str(step.get("action") or "").lower()
    requested = " ".join(
        str(value or "")
        for value in (
            step.get("element_name"), step.get("target"), step.get("selector"),
            test_case.get("title"), test_case.get("description"),
            " ".join(str(value) for value in (test_case.get("input_fields") or [])),
        )
    ).lower()
    sources = []
    if any(token in action for token in ("click", "button", "link")):
        sources.extend(analysis.get("buttons") or [])
        sources.extend(analysis.get("links") or [])
    sources.extend(analysis.get("inputs") or [])
    sources.extend(analysis.get("selects") or [])
    sources.extend(
        field
        for form in (analysis.get("forms") or [])
        if isinstance(form, dict)
        for field in (form.get("inputs") or [])
    )

    best = None
    best_score = 0
    for candidate in sources:
        if not isinstance(candidate, dict):
            continue
        candidate_text = " ".join(str(candidate.get(key) or "") for key in ("name", "id", "label", "placeholder", "text", "type")).lower()
        score = sum(1 for token in re.findall(r"[a-z0-9]+", requested) if len(token) > 2 and token in candidate_text)
        if score > best_score or (best is None and candidate.get("id")):
            best = candidate
            best_score = score
    if best is None:
        return existing
    discovered = dict(existing)
    for key in ("id", "name", "data-testid", "data_testid", "selector", "xpath", "label", "text", "type"):
        if best.get(key) is not None:
            discovered[key] = best.get(key)
    locator_type, locator_value = _dom_locator(best)
    if locator_type:
        discovered["locator_type"] = locator_type
        discovered["locator_value"] = locator_value
    return discovered


def _build_agent1_step(step: Dict[str, Any], index: int, test_case: Dict[str, Any], analysis: Dict[str, Any]) -> Agent1TestStep:
    enriched = dict(step)
    mapping = _discovered_mapping_for_step(enriched, test_case, analysis)
    visible_names = {
        str(enriched.get(key) or "").strip().casefold()
        for key in ("label", "text", "element_name", "title")
        if str(enriched.get(key) or "").strip()
    }
    if isinstance(mapping, dict):
        visible_names.update(
            str(mapping.get(key) or "").strip().casefold()
            for key in ("label", "text")
            if str(mapping.get(key) or "").strip()
        )
    if str(enriched.get("locator_value") or "").strip().casefold() in visible_names:
        enriched["locator_type"] = None
        enriched["locator_value"] = None
    locator_type, locator_value = _dom_locator(enriched)
    if not locator_type:
        locator_type, locator_value = _dom_locator(mapping)
    enriched["locator_type"] = locator_type
    enriched["locator_value"] = locator_value
    if not enriched.get("element_name"):
        enriched["element_name"] = mapping.get("label") or mapping.get("text") or mapping.get("name") or mapping.get("id") or "Element"
    locator_status = "available" if locator_type and locator_value else "locator unavailable"
    LOGGER.debug(
        "Agent1 locator: scenario_id=%s element_name=%s locator_type=%s locator_value=%s status=%s",
        test_case.get("scenario_id"), enriched.get("element_name"), locator_type, locator_value, locator_status,
    )
    return Agent1TestStep(
        step_number=index,
        action=str(enriched.get("action") or "perform action"),
        selector=enriched.get("selector") if isinstance(enriched.get("selector"), str) else None,
        target=enriched.get("target") if isinstance(enriched.get("target"), str) else None,
        element_name=enriched.get("element_name") if isinstance(enriched.get("element_name"), str) else None,
        locator_type=locator_type,
        locator_value=locator_value,
        locator_status=locator_status,
        value=enriched.get("value") if "value" in enriched else None,
        expected_value=enriched.get("expected_value") if "expected_value" in enriched else None,
        data_type=enriched.get("data_type") if isinstance(enriched.get("data_type"), str) else None,
    )


def _agent1_source_steps(test_case: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    steps = test_case.get("steps") or test_case.get("test_steps") or []
    if isinstance(steps, list) and steps:
        return [step for step in steps if isinstance(step, dict)]

    # Recover an action only from a real analyzed control. Never create a
    # placeholder locator when the page analysis has no usable element.
    candidates = []
    candidates.extend(analysis.get("inputs") or [])
    candidates.extend(analysis.get("selects") or [])
    candidates.extend(analysis.get("buttons") or [])
    candidates.extend(analysis.get("links") or [])
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        mapping = {key: candidate.get(key) for key in ("id", "name", "data-testid", "data_testid", "href", "selector", "xpath", "label", "text", "type") if candidate.get(key) is not None}
        if _has_real_locator(mapping):
            action = "click_element" if str(candidate.get("tag") or "").lower() in {"button", "a"} else "enter_text"
            return [{"action": action, "element_name": candidate.get("label") or candidate.get("name") or candidate.get("id"), "mapping": mapping}]
    return []


def _app_name_from_analysis(analysis: Dict[str, Any], url: str) -> str:
    title = str(analysis.get("title") or "").strip()
    if title:
        return title
    parsed = urlparse(url or analysis.get("url") or "")
    host = parsed.netloc or parsed.path or "Application"
    return host.split(".")[0].replace("-", " ").title() or "Application"


def _extract_input_fields(analysis: Dict[str, Any]) -> List[str]:
    """Detect ALL page-level input fields and return field names with their types.
    
    Extracts from:
    - input fields (text, email, password, phone, search, number, date, checkbox, radio, file, etc.)
    - textarea fields
    - select/dropdown fields
    
    Returns a flat list of field names that Agent 1 can use to generate scenarios.
    Agent 2 will receive these fields and generate appropriate test data based on field type.
    """
    field_list: List[str] = []
    field_set: Set[str] = set()

    def add_field(candidate: Any) -> None:
        if not isinstance(candidate, str):
            return
        field_name = candidate.strip()
        if not field_name or re.fullmatch(r"react-select-\d+-input", field_name, re.IGNORECASE):
            return
        if field_name not in field_set:
            field_list.append(field_name)
            field_set.add(field_name)
    
    # Extract from page-level inputs (includes input types + textarea)
    inputs = analysis.get("inputs") or []
    if isinstance(inputs, list):
        for item in inputs:
            if not isinstance(item, dict):
                continue
            
            # Get field name from multiple possible keys
            field_name = (
                item.get("name") or 
                item.get("id") or 
                item.get("label") or 
                item.get("placeholder") or
                ""
            )
            add_field(field_name)
    
    # Extract from select/dropdown fields
    selects = analysis.get("selects") or []
    if isinstance(selects, list):
        for item in selects:
            if not isinstance(item, dict):
                continue
            
            field_name = (
                item.get("name") or 
                item.get("id") or 
                item.get("label") or
                ""
            )
            add_field(field_name)
    
    # Extract from form inputs (includes input types within forms + textarea + select within forms)
    forms = analysis.get("forms") or []
    if isinstance(forms, list):
        for form in forms:
            if not isinstance(form, dict):
                continue
            
            # Extract fields from the form
            form_inputs = form.get("inputs") or []
            if isinstance(form_inputs, list):
                for item in form_inputs:
                    if not isinstance(item, dict):
                        continue
                    
                    field_name = (
                        item.get("name") or 
                        item.get("id") or 
                        item.get("label") or 
                        item.get("placeholder") or
                        ""
                    )
                    add_field(field_name)
    
    return field_list


def _detect_field_type_from_analysis(field_name: str, analysis: Dict[str, Any]) -> str:
    """Detect the field type from the analysis object.
    
    Searches through inputs, selects, and form fields to find the matching field
    and determine its type (text, email, password, textarea, checkbox, radio, select/dropdown, etc.)
    """
    if not isinstance(analysis, dict) or not field_name:
        return "text"
    
    field_name_lower = field_name.lower()

    # Some sites expose semantic fields as generic text inputs or as
    # React-Select comboboxes. Prefer the business name when it is explicit.
    semantic_types = {
        "email": "email",
        "e-mail": "email",
        "mobile": "phone",
        "phone": "phone",
        "telephone": "phone",
        "gender": "radio",
        "state": "dropdown",
        "city": "dropdown",
        "country": "dropdown",
        "select": "dropdown",
        "search": "search",
        "password": "password",
        "date": "date",
        "address": "address",
    }
    for token, field_type in semantic_types.items():
        if re.search(rf"(?:^|[ _-]){re.escape(token)}(?:$|[ _-])", field_name_lower):
            return field_type
    
    # Check page-level inputs
    inputs = analysis.get("inputs") or []
    if isinstance(inputs, list):
        for item in inputs:
            if not isinstance(item, dict):
                continue
            
            item_name = str(item.get("name") or item.get("id") or item.get("label") or item.get("placeholder") or "").lower()
            if item_name == field_name_lower or field_name_lower in item_name:
                input_type = str(item.get("type") or "text").lower()
                
                # Map HTML input types to field type vocabulary
                if input_type == "textarea":
                    return "textarea"
                elif input_type == "checkbox":
                    return "checkbox"
                elif input_type == "radio":
                    return "radio"
                elif input_type == "email":
                    return "email"
                elif input_type == "password":
                    return "password"
                elif input_type == "number":
                    return "number"
                elif input_type == "date":
                    return "date"
                elif input_type == "file":
                    return "file"
                elif input_type == "search":
                    return "search"
                elif input_type == "tel" or input_type == "phone":
                    return "phone"
                elif input_type == "url":
                    return "url"
                elif input_type == "text":
                    return "text"
                else:
                    return input_type if input_type else "text"
    
    # Check page-level selects
    selects = analysis.get("selects") or []
    if isinstance(selects, list):
        for item in selects:
            if not isinstance(item, dict):
                continue
            
            item_name = str(item.get("name") or item.get("id") or item.get("label") or "").lower()
            if item_name == field_name_lower or field_name_lower in item_name:
                return "dropdown"
    
    # Check form inputs and selects
    forms = analysis.get("forms") or []
    if isinstance(forms, list):
        for form in forms:
            if not isinstance(form, dict):
                continue
            
            form_inputs = form.get("inputs") or []
            if isinstance(form_inputs, list):
                for item in form_inputs:
                    if not isinstance(item, dict):
                        continue
                    
                    item_name = str(item.get("name") or item.get("id") or item.get("label") or item.get("placeholder") or "").lower()
                    if item_name == field_name_lower or field_name_lower in item_name:
                        # Check for kind field (form extraction uses "kind" for select, input, textarea)
                        kind = str(item.get("kind") or "").lower()
                        if kind == "select":
                            return "dropdown"
                        elif kind == "textarea":
                            return "textarea"
                        
                        # Check type field for input types
                        input_type = str(item.get("type") or "text").lower()
                        if input_type == "checkbox":
                            return "checkbox"
                        elif input_type == "radio":
                            return "radio"
                        elif input_type == "email":
                            return "email"
                        elif input_type == "password":
                            return "password"
                        elif input_type == "number":
                            return "number"
                        elif input_type == "date":
                            return "date"
                        elif input_type == "file":
                            return "file"
                        elif input_type == "search":
                            return "search"
                        elif input_type == "tel" or input_type == "phone":
                            return "phone"
                        elif input_type == "url":
                            return "url"
                        elif input_type == "text":
                            return "text"
                        else:
                            return input_type if input_type else "text"
    
    return "text"


def _build_page_metadata(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize the analysis object into a Selenium/QA page_metadata section."""
    page_inputs = analysis.get("inputs") or []
    page_forms = analysis.get("forms") or []
    page_buttons = analysis.get("buttons") or []
    page_selects = analysis.get("selects") or []
    page_links = analysis.get("links") or []

    checkbox_candidates = []
    for field in page_inputs if isinstance(page_inputs, list) else []:
        if isinstance(field, dict) and str(field.get("type") or "").lower() == "checkbox":
            checkbox_candidates.append(field)

    return {
        "forms": page_forms if isinstance(page_forms, list) else [],
        "buttons": page_buttons if isinstance(page_buttons, list) else [],
        "fields": page_inputs if isinstance(page_inputs, list) else [],
        "dropdowns": page_selects if isinstance(page_selects, list) else [],
        "checkboxes": checkbox_candidates,
        "links": page_links if isinstance(page_links, list) else [],
    }


def _extract_name_from_item(item: Dict[str, Any]) -> str:
    if not isinstance(item, dict):
        return None
    mapping = item.get("mapping") or {}
    for key in ("label", "field_name", "text", "name", "id"):
        val = mapping.get(key) if isinstance(mapping, dict) else None
        if isinstance(val, str) and val.strip():
            return val.strip()
    # Try title/description fields
    title = str(item.get("title") or item.get("description") or "").strip()
    if title:
        m = re.search(r"['\"]([^'\"]+)['\"]", title)
        if m:
            return m.group(1).strip()
    return None


def _with_name(s: str, name: str) -> str:
    if not s:
        return s
    if name:
        return s.replace("Element", name).replace("Target Field", name).replace("Target Link", name).replace("Input Field", name)
    return s


def _expected_result_text(item: Dict[str, Any]) -> str:
    raw = item.get("expected_result") or item.get("expected_results") or item.get("expected") or "Element is visible"
    name = _extract_name_from_item(item)
    if isinstance(raw, str):
        phrase = raw.strip()
        if not phrase:
            return _with_name("Element is visible", name)
        lowered = phrase.lower()
        if any(blocked in lowered for blocked in ("outcome is verified", "validation successful", "test passed", "verification successful")):
            return _with_name("Validation message is displayed", name)
        return _with_name(phrase, name)
    if isinstance(raw, dict):
        # Preserve Selenium-oriented assertions for exact DOM-visible outcomes
        if "message" in raw:
            return _with_name(str(raw.get("message") or "Validation message is displayed"), name)
        if "status" in raw:
            return _with_name(str(raw.get("status") or "Success message is displayed"), name)
        return _with_name("Element is visible", name)
    if isinstance(raw, list):
        candidates = [str(value) for value in raw if value]
        if candidates:
            return _with_name(candidates[0], name)
        return _with_name("Element is visible", name)
    return _with_name(str(raw) or "Element is visible", name)


def _required_data_contract_for_fields(fields: List[str], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Map page input fields into the Agent 2 contract required_data payload.

    For each discovered field name, detects its type from the analysis object,
    then generates appropriate metadata for test data generation.
    
    Supports: text, email, password, username, phone, textarea, address,
    multiline, date, select/dropdown, radio, checkbox, file, url, search, number.
    """
    # Field type to metadata mapping
    field_type_metadata = {
        "email": {
            "business_purpose": "User Authentication",
            "expected_format": "valid email address",
            "validation_rules": ["cannot be empty", "must contain @", "must be a syntactically valid email"],
        },
        "username": {
            "business_purpose": "User Identification",
            "expected_format": "username or account identifier",
            "validation_rules": ["cannot be empty", "must satisfy username policy"],
        },
        "password": {
            "business_purpose": "User Authentication",
            "expected_format": "minimum 8 characters",
            "validation_rules": ["cannot be empty", "minimum length 8", "must be masked in UI"],
        },
        "phone": {
            "business_purpose": "Contact Information",
            "expected_format": "valid phone number",
            "validation_rules": ["cannot be empty", "must contain digits and optional separators"],
        },
        "text": {
            "business_purpose": "Free-form user entry",
            "expected_format": "plain text value",
            "validation_rules": ["cannot be empty when required"],
        },
        "textarea": {
            "business_purpose": "Multi-line text entry",
            "expected_format": "multi-line text value",
            "validation_rules": ["cannot be empty when required", "accepts multi-line input"],
        },
        "address": {
            "business_purpose": "Address information",
            "expected_format": "complete address with street, city, state, zip",
            "validation_rules": ["cannot be empty when required", "must be a valid address format"],
        },
        "multiline": {
            "business_purpose": "Multi-line text entry",
            "expected_format": "multi-line text value",
            "validation_rules": ["cannot be empty when required", "accepts multi-line input"],
        },
        "number": {
            "business_purpose": "Numeric data capture",
            "expected_format": "numeric value",
            "validation_rules": ["cannot be empty when required", "must be numeric"],
        },
        "date": {
            "business_purpose": "Date-based workflow",
            "expected_format": "YYYY-MM-DD",
            "validation_rules": ["cannot be empty when required", "must be a valid date"],
        },
        "search": {
            "business_purpose": "Search and filtering",
            "expected_format": "search query text",
            "validation_rules": ["cannot be empty when required"],
        },
        "dropdown": {
            "business_purpose": "Controlled selection",
            "expected_format": "one of the allowed values",
            "validation_rules": ["must select an available option"],
        },
        "select": {
            "business_purpose": "Controlled selection",
            "expected_format": "one of the allowed values",
            "validation_rules": ["must select an available option"],
        },
        "checkbox": {
            "business_purpose": "Preference or consent confirmation",
            "expected_format": "true or false",
            "validation_rules": ["boolean value is accepted"],
        },
        "radio": {
            "business_purpose": "Single option selection",
            "expected_format": "one of the available options",
            "validation_rules": ["must select one available option"],
        },
        "file": {
            "business_purpose": "File upload",
            "expected_format": "valid file path or file object",
            "validation_rules": ["must be a valid file", "must satisfy file type restrictions"],
        },
        "url": {
            "business_purpose": "URL entry",
            "expected_format": "absolute URL",
            "validation_rules": ["must be a valid web URL"],
        },
    }

    required_data = []
    seen_fields = set()
    
    for field_name in (fields or []):
        if not isinstance(field_name, str):
            continue
        
        field_name = field_name.strip()
        if not field_name or field_name in seen_fields:
            continue
        seen_fields.add(field_name)
        
        # Detect the actual field type from the analysis
        detected_type = _detect_field_type_from_analysis(field_name, analysis)
        
        # Normalize field type names for consistency
        normalized_type = detected_type.lower()
        if normalized_type in ("textarea", "multiline", "address"):
            normalized_type = detected_type.lower()  # Keep as-is for distinction but map appropriately
        elif normalized_type == "select":
            normalized_type = "dropdown"
        elif normalized_type in ("tel", "telephone"):
            normalized_type = "phone"
        
        # Get metadata for this field type
        meta = field_type_metadata.get(normalized_type, field_type_metadata.get("text"))
        
        required_data.append({
            "field_name": field_name,
            "field_type": normalized_type,
            "business_purpose": meta["business_purpose"],
            "expected_format": meta["expected_format"],
            "validation_rules": meta["validation_rules"],
        })

    return required_data


def _feature_names_from_analysis(analysis: Dict[str, Any], scenarios: Any) -> List[Agent1Feature]:
    features: List[Agent1Feature] = []
    forms = analysis.get("forms") or []
    inputs = analysis.get("inputs") or []
    buttons = analysis.get("buttons") or []
    links = analysis.get("links") or []

    feature_specs = []
    if forms:
        feature_specs.append(("FEAT001", "Forms", "Form-driven user interaction"))
    if inputs:
        feature_specs.append(("FEAT002", "Input Fields", "Text, email, password, select and numeric input handling"))
    if buttons:
        feature_specs.append(("FEAT003", "Actions & Buttons", "Primary action and button verification"))
    if links:
        feature_specs.append(("FEAT004", "Navigation Links", "Link and navigation coverage"))

    if not feature_specs and isinstance(scenarios, list):
        for idx, item in enumerate(scenarios[:3], start=1):
            if isinstance(item, dict):
                title = str(item.get("title") or "").strip()
                if title:
                    feature_specs.append((f"FEAT{idx:03d}", title, item.get("description") or title))

    for idx, (feature_id, name, description) in enumerate(feature_specs, start=1):
        if not name:
            continue
        normalized_feature_id = feature_id if feature_id else f"FEAT{idx:03d}"
        features.append(Agent1Feature(feature_id=normalized_feature_id, name=name, description=description))

    return features


def _extract_discovered_locators(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Return the exact DOM-derived selectors that were used to build the generated tests."""
    def normalize_item(item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        selector = item.get("selector") or item.get("css") or item.get("id") or item.get("name")
        return {
            "tag": item.get("tag") or item.get("kind") or item.get("type") or "",
            "id": item.get("id") or "",
            "name": item.get("name") or "",
            "type": item.get("type") or "",
            "text": item.get("text") or "",
            "placeholder": item.get("placeholder") or "",
            "href": item.get("href") or "",
            "selector": selector or "",
        }

    inputs = [normalize_item(item) for item in (analysis.get("inputs") or [])]
    buttons = [normalize_item(item) for item in (analysis.get("buttons") or [])]
    links = [normalize_item(item) for item in (analysis.get("links") or [])]
    forms = []
    for form in analysis.get("forms") or []:
        if not isinstance(form, dict):
            continue
        fields = [normalize_item(field) for field in (form.get("inputs") or [])]
        forms.append({
            "id": form.get("id") or "",
            "name": form.get("name") or "",
            "selector": form.get("selector") or form.get("id") or form.get("name") or "form",
            "fields": fields,
        })
    headings = []
    for heading in analysis.get("headings") or []:
        if isinstance(heading, dict):
            headings.append(normalize_item(heading))
    return {
        "forms": forms,
        "inputs": inputs,
        "buttons": buttons,
        "links": links,
        "headings": headings,
    }


async def run_full_pipeline(url: str, render_js: bool = False) -> Dict[str, Any]:
    """Run the analysis pipeline.

    Steps:
      1. Analyze URL -> analysis JSON
      2. Generate scenarios from analysis -> scenarios list
      3. Generate testcases from scenarios -> testcases list

    Returns a dict matching the required response shape.
    """
    # 1. Analyze
    try:
        analysis = await analyze_url(url, render_js=render_js)
    except URLAnalysisError as e:
        LOGGER.exception("URL analysis failed: %s", e)
        raise

    # 2. Scenarios
    try:
        scenarios_resp = await generate_scenarios(analysis)
        scenarios = scenarios_resp.get("scenarios") if isinstance(scenarios_resp, dict) else scenarios_resp
    except GroqServiceError as e:
        LOGGER.exception("Scenario generation failed: %s", e)
        raise

    # 3. Testcases
    try:
        testcases_resp = await generate_testcases(scenarios)
        testcases = testcases_resp.get("testcases") if isinstance(testcases_resp, dict) else testcases_resp
    except GroqServiceError as e:
        LOGGER.exception("Testcase generation failed: %s", e)
        raise

    feature_groups: List[Agent1FeatureGroup] = []
    feature_names = _feature_names_from_analysis(analysis, scenarios)
    if not feature_names:
        feature_names = [
            Agent1Feature(
                feature_id="FEAT001",
                name="Page Elements",
                description="Discovered page elements",
            )
        ]
    input_fields = _extract_input_fields(analysis)
    scenario_counter = 1
    test_case_counter = 1

    if feature_names:
        for feature in feature_names:
            feature_name = feature.name
            feature_id = feature.feature_id
            matching_scenarios = []
            matching_testcases = []

            for idx, s in enumerate(scenarios if isinstance(scenarios, list) else [], start=1):
                if isinstance(s, dict) and feature_name.lower() in str(s.get("title") or "").lower():
                    # Preserve pre-existing scenario_id if Agent 1 provided one; do NOT generate new IDs here
                    scenario_id = _agent1_scenario_id(s)

                    inferred_test_type = str(s.get("test_type") or "positive").strip().lower() or "positive"
                    if inferred_test_type not in {"positive", "negative", "validation", "boundary"}:
                        inferred_test_type = "positive"
                    matching_scenarios.append(
                        Agent1TestScenario(
                            scenario_id=scenario_id,
                            feature_id=feature_id,
                            id=str(s.get("id") or f"s{idx}"),
                            title=str(s.get("title") or s.get("description") or f"Scenario {idx}"),
                            description=s.get("description") if isinstance(s.get("description"), str) else None,
                            priority=str(s.get("priority") or "medium"),
                            test_type=inferred_test_type,
                            preconditions=["The application is available", "The user is on the target page"],
                            test_steps=[
                                Agent1TestStep(action="Observe target page", selector=s.get("mapping", {}).get("page") if isinstance(s.get("mapping"), dict) else None, value=s.get("mapping") or {})
                            ],
                            expected_results=["The scenario condition is observable and the page responds as designed"],
                        )
                    )

            for idx, item in enumerate(testcases if isinstance(testcases, list) else [], start=1):
                if isinstance(item, dict) and (
                    feature_name.lower() in str(item.get("title") or "").lower()
                    or feature_name.lower() in str(item.get("description") or "").lower()
                ):
                    # Resolve scenario_id for this test case. Prefer explicit mappings, then matching_scenarios, then try to find a matching scenario by title/description, then mapping fallback.
                    scenario_id = None
                    # 1) explicit on the test case
                    if isinstance(item, dict):
                        scenario_id = _agent1_scenario_id(item)
                    # 2) use the first matching_scenario's id if present
                    if not scenario_id and matching_scenarios:
                        scenario_id = matching_scenarios[0].scenario_id
                    # 3) try to find in the original scenarios list by exact title/description match
                    if not scenario_id:
                        try:
                            title = str(item.get('title') or '').strip()
                            desc = str(item.get('description') or '').strip()
                            for s in (scenarios or []):
                                if not isinstance(s, dict):
                                    continue
                                sid_candidate = _agent1_scenario_id(s)
                                if title and title and str(s.get('title') or '').strip() == title and sid_candidate:
                                    scenario_id = sid_candidate.strip() if isinstance(sid_candidate, str) else sid_candidate
                                    break
                                if desc and str(s.get('description') or '').strip() == desc and sid_candidate:
                                    scenario_id = sid_candidate.strip() if isinstance(sid_candidate, str) else sid_candidate
                                    break
                        except Exception:
                            scenario_id = scenario_id
                    # 4) fallback to mapping-contained scenario identifiers (mapping.scenario_id or mapping.scenario)
                    if not scenario_id:
                        mapping_candidate = (item.get('mapping') or {}) if isinstance(item, dict) else {}
                        if isinstance(mapping_candidate, dict):
                            scenario_id = _agent1_scenario_id(item)

                    test_case_id = f"TC{test_case_counter:03d}"
                    test_case_counter += 1
                    required_data = _required_data_contract_for_fields(input_fields, analysis)
                    # Log mapping/title and detected element name prior to expected result generation
                    try:
                        detected_name = central_extract_element_name(item.get('mapping') or {}, item.get('title') or item.get('description'))
                    except Exception:
                        detected_name = None
                    LOGGER.info("orchestrator - preparing Agent1TestCase: title=%s mapping=%s detected_name=%s resolved_scenario_id=%s", item.get('title'), item.get('mapping'), detected_name, scenario_id)

                    matching_testcases.append(
                        Agent1TestCase(
                            test_case_id=test_case_id,
                            feature_id=feature_id,
                            scenario_id=scenario_id,
                            id=str(item.get("id") or f"t{idx}"),
                            title=str(item.get("title") or f"Test Case {idx}"),
                            priority=str(item.get("priority") or "medium"),
                            application_url=url or analysis.get("url") or "",
                            preconditions=item.get("preconditions") or ["The application is available"],
                            test_steps=[
                                _build_agent1_step(step, step_index, item, analysis)
                                for step_index, step in enumerate(_agent1_source_steps(item, analysis), start=1)
                                if isinstance(step, dict)
                            ],
                            # Prefer per-item input_fields/mapping when available so Agent2 can generate field-specific data
                            input_fields=item.get("input_fields") or input_fields,
                            required_data=item.get("required_data") or required_data,
                            mapping=item.get("mapping") or {},
                            expected_result=_expected_result_text(item),
                        )
                    )

            if matching_scenarios or matching_testcases:
                feature_groups.append(
                    Agent1FeatureGroup(
                        feature_id=feature_id,
                        feature=feature_name,
                        description=feature.description,
                        test_scenarios=matching_scenarios,
                        test_cases=matching_testcases,
                    )
                )

    if not feature_groups:
        fallback_scenarios = []
        for idx, s in enumerate(scenarios if isinstance(scenarios, list) else [], start=1):
            inferred_test_type = str(s.get("test_type") or "positive").strip().lower() or "positive"
            if inferred_test_type not in {"positive", "negative", "validation", "boundary"}:
                inferred_test_type = "positive"
            # Preserve any provided scenario_id from the source scenario; do NOT fabricate new IDs
            sid_to_use = _agent1_scenario_id(s)

            fallback_scenarios.append(
                Agent1TestScenario(
                    scenario_id=sid_to_use,
                    feature_id=feature_names[0].feature_id,
                    id=str(s.get("id") or f"s{idx}"),
                    title=str(s.get("title") or s.get("description") or f"Scenario {idx}"),
                    description=s.get("description") if isinstance(s.get("description"), str) else None,
                    priority=str(s.get("priority") or "medium"),
                    test_type=inferred_test_type,
                    preconditions=["The application is available", "The user is on the target page"],
                    test_steps=[
                        Agent1TestStep(action="Observe target page", selector=s.get("mapping", {}).get("page") if isinstance(s.get("mapping"), dict) else None, value=s.get("mapping") or {})
                    ],
                    expected_results=["The scenario condition is observable and the page responds as designed"],
                )
            )

        # Build fallback feature group with explicit logging for expected result name extraction
        test_cases_list = []
        for idx, item in enumerate(testcases if isinstance(testcases, list) else [], start=1):
            try:
                detected_name = central_extract_element_name(item.get('mapping') or {}, item.get('title') or item.get('description'))
            except Exception:
                detected_name = None
            LOGGER.info("orchestrator - fallback TestCase prepare: idx=%s title=%s mapping=%s detected_name=%s", idx, item.get('title'), item.get('mapping'), detected_name)
            # For fallback test cases, preserve any incoming scenario_id if provided by the source item
            sid_to_use = _agent1_scenario_id(item)

            test_case = Agent1TestCase(
                test_case_id=f"TC{test_case_counter:03d}",
                feature_id=feature_names[0].feature_id,
                scenario_id=sid_to_use,
                id=str(item.get("id") or f"t{idx}"),
                title=str(item.get("title") or f"Test Case {idx}"),
                priority=str(item.get("priority") or "medium"),
                application_url=url or analysis.get("url") or "",
                preconditions=item.get("preconditions") or ["The application is available"],
                test_steps=[
                    _build_agent1_step(step, step_index, item, analysis)
                    for step_index, step in enumerate(_agent1_source_steps(item, analysis), start=1)
                    if isinstance(step, dict)
                ],
                input_fields=item.get('input_fields') or input_fields,
                required_data=item.get('required_data') or _required_data_contract_for_fields(input_fields, analysis),
                mapping=item.get('mapping') or {},
                expected_result=_expected_result_text(item),
            )
            test_cases_list.append(test_case)
        feature_groups = [
            Agent1FeatureGroup(
                feature_id=feature_names[0].feature_id,
                feature=feature_names[0].name,
                description=feature_names[0].description,
                test_scenarios=fallback_scenarios,
                test_cases=test_cases_list,
            )
        ]

    flat_testcases = [test_case for group in feature_groups for test_case in group.test_cases]

    for test_case in flat_testcases:
        for step in test_case.test_steps:
            LOGGER.debug(
                "Agent1 locator contract: scenario_id=%s element_name=%s locator_type=%s locator_value=%s status=%s",
                test_case.scenario_id,
                step.element_name,
                step.locator_type,
                step.locator_value,
                step.locator_status,
            )

    page_metadata = _build_page_metadata(analysis)

    contract = Agent1Contract(
        application_name=_app_name_from_analysis(analysis, url),
        url=url or analysis.get("url") or "",
        application_url=url or analysis.get("url") or "",
        page_title=str(analysis.get("title") or "").strip() or None,
        features=feature_names,
        feature_groups=feature_groups,
        page_metadata=page_metadata,
        agent_2_input=Agent2TestDataInput(
            application_name=_app_name_from_analysis(analysis, url),
            url=url or analysis.get("url") or "",
            test_cases=flat_testcases,
        ),
        agent_3_input=Agent3SeleniumInput(
            application_name=_app_name_from_analysis(analysis, url),
            url=url or analysis.get("url") or "",
            features=feature_names,
            test_scenarios=[scenario for group in feature_groups for scenario in group.test_scenarios],
            test_cases=flat_testcases,
        ),
    )

    # Log test case count and identifiers being passed to Agent 2 for easier triage
    try:
        tc_summary = [
            {
                "test_case_id": getattr(case, "test_case_id", None) or (case.get("test_case_id") if isinstance(case, dict) else None),
                "scenario_id": getattr(case, "scenario_id", None) or (case.get("scenario_id") if isinstance(case, dict) else None),
                "title": getattr(case, "title", None) or (case.get("title") if isinstance(case, dict) else None),
            }
            for case in flat_testcases
        ]
    except Exception:
        tc_summary = []

    LOGGER.info("orchestrator: Passing %s test_cases to Agent2. Samples: %s", len(flat_testcases), tc_summary[:10])

    # Build Agent2 test_cases array. Prefer the explicit test cases created above, but also
    # include any original Agent 1 scenarios (one-to-one) to ensure Agent2 receives every scenario
    # even when test_cases were not created for some scenarios.
    agent2_test_cases = [case.model_dump(mode="json") for case in flat_testcases if hasattr(case, "model_dump")]

    # Add any scenario entries that are missing from agent2_test_cases (preserve scenario_id)
    existing_ids = set()
    for tc in agent2_test_cases:
        try:
            if isinstance(tc, dict):
                existing_ids.add(str(tc.get("scenario_id") or tc.get("id") or tc.get("test_case_id") or "").strip())
        except Exception:
            continue

    for s in (scenarios or []):
        if not isinstance(s, dict):
            continue
        sid_str = _agent1_scenario_id(s)
        if not sid_str:
            # Skip adding minimal entry when the source scenario lacks a stable scenario_id
            continue
        if sid_str in existing_ids:
            continue
        # Construct a minimal test case representation for Agent2
        minimal = {
            "scenario_id": sid_str,
            "title": s.get("title") or s.get("description") or "",
            "description": s.get("description") or "",
            "mapping": s.get("mapping") or {},
            "input_fields": s.get("input_fields") or input_fields,
            "required_data": s.get("required_data") or _required_data_contract_for_fields(input_fields, analysis),
        }
        agent2_test_cases.append(minimal)

    LOGGER.info("orchestrator: Passing %s test_cases to Agent2. Samples: %s", len(agent2_test_cases), agent2_test_cases[:10])

    agent_2_request = Agent2GenerationRequest(
        application_name=_app_name_from_analysis(analysis, url),
        url=url or analysis.get("url") or "",
        test_cases=agent2_test_cases,
        agent_1_contract=contract.model_dump(mode="json"),
    )
    agent_2_contract = build_test_data_contract(agent_2_request)

    agent_2_contract_dict = agent_2_contract.model_dump(mode="json")
    # Preserve the complete scenario-level bundle. The old implementation
    # selected the first category record, which could belong to another
    # scenario and contained only one field/category.
    scenario_outputs = agent_2_contract_dict.get("scenario_outputs") or []
    first_scenario_output = next(
        (output for output in scenario_outputs if isinstance(output, dict)),
        None,
    )
    agent3_test_data: Dict[str, Any] = {}
    if first_scenario_output and isinstance(first_scenario_output.get("generated_data"), dict):
        agent3_test_data = {
            "scenario_id": first_scenario_output.get("scenario_id"),
            "requires_test_data": first_scenario_output.get(
                "requires_test_data", agent_2_contract_dict.get("requires_test_data", True)
            ),
            "generated_data": first_scenario_output["generated_data"],
            "scenario_outputs": scenario_outputs,
        }
        LOGGER.info(
            "orchestrator: Prepared complete Agent3 test_data bundle for scenario_id=%s",
            first_scenario_output.get("scenario_id"),
        )
    else:
        LOGGER.warning("orchestrator: No scenario-level test data could be extracted for Agent3")

    result: Dict[str, Any] = {
        "analysis": analysis,
        "application_url": url or analysis.get("url") or "",
        "page_title": str(analysis.get("title") or "").strip() or None,
        "scenarios": scenarios,
        "testcases": testcases,
        "page_metadata": page_metadata,
        "discovered_locators": _extract_discovered_locators(analysis),
        "agent_1_contract": contract.model_dump(mode="json"),
        "agent_2_contract": agent_2_contract_dict,
        "agent_3_test_data": agent3_test_data,
    }

    # Demo Mode: for known demo domains like saucedemo.com, generate additional insights
    try:
        if "saucedemo.com" in (url or ""):
            groq = GroqService()
            artifacts = {"analysis": analysis, "scenarios": scenarios, "testcases": testcases}
            demo_insights = await groq.generate_demo_insights(artifacts)
            # Expect keys: defect_possibilities, risk_areas, automation_coverage_percent, recommended_smoke_tests
            if isinstance(demo_insights, dict):
                result.update(demo_insights)
                result["demo_insights"] = demo_insights
    except GroqServiceError as e:
        # Log and continue without failing the whole pipeline
        LOGGER.exception("Demo insights generation failed: %s", e)

    return result
