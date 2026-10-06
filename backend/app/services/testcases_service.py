import re
import logging
from typing import Any, Dict, List

from app.core.groq_service import GroqService, GroqServiceError
from app.services.element_detection import (
    detect_element_type,
    get_element_specific_expected_results,
    get_element_specific_automation_hints,
    ElementType,
)
from app.services.intent_classifier import extract_element_name as central_extract_element_name

LOGGER = logging.getLogger(__name__)


def _source_scenario_id(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    mapping = item.get("mapping") or {}
    for value in (
        item.get("scenario_id"),
        item.get("test_scenario_id"),
        item.get("scenario"),
        mapping.get("scenario_id") if isinstance(mapping, dict) else None,
        mapping.get("test_scenario_id") if isinstance(mapping, dict) else None,
        mapping.get("scenarioId") if isinstance(mapping, dict) else None,
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


_BLOCKED_EXPECTED_RESULT_PHRASES = (
    "outcome is verified",
    "verification successful",
    "validations successful",
    "validation successful",
    "test passed",
)


def _extract_element_name(mapping: Dict[str, Any] = None, title: str = None, raw_text: str = None) -> str:
    """Attempt to derive a human-friendly element name from mapping, title, or raw text.

    Returns None if no suitable name is found.
    """
    mapping = mapping or {}
    visible_names = {
        str(mapping.get(key) or "").strip().casefold()
        for key in ("label", "text", "element_name", "title")
        if str(mapping.get(key) or "").strip()
    }
    # Priority: mapping.label, mapping.field_name, mapping.text, mapping.name
    for key in ("label", "field_name", "text", "name", "id"):
        val = mapping.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    # Try to extract quoted name from title/description: e.g., Verify link 'Login' navigates
    if isinstance(title, str) and title:
        m = re.search(r"['\"]([^'\"]+)['\"]", title)
        if m:
            return m.group(1).strip()
        # fallback: look for patterns like Verify link Login
        m2 = re.search(r"verify\s+(?:link|button|field|input)\s+([A-Za-z0-9 _-]+)", title.lower())
        if m2:
            return m2.group(1).strip().title()

    # Try raw_text
    if isinstance(raw_text, str) and raw_text:
        m = re.search(r"['\"]([^'\"]+)['\"]", raw_text)
        if m:
            return m.group(1).strip()

    return None


def _expected_result_to_text(value: Any, mapping: Dict[str, Any] = None, title: str = None) -> str:
    """Normalize an expected result payload into an automation-friendly assertion phrase.

    Replaces generic placeholders like 'Element' with actual element names when available.
    """
    name = _extract_element_name(mapping or {}, title, value if isinstance(value, str) else None)

    def _with_name(s: str) -> str:
        if not s:
            return s
        if name:
            return s.replace("Element", name).replace("Target Field", name).replace("Target Link", name).replace("Input Field", name)
        return s

    if isinstance(value, str):
        phrase = value.strip()
        if not phrase:
            return _with_name("Element is visible")
        lowered = phrase.lower()
        if any(blocked in lowered for blocked in _BLOCKED_EXPECTED_RESULT_PHRASES):
            return _with_name("Browser title equals expected title")
        return _with_name(phrase)
    if isinstance(value, dict):
        if value.get("message"):
            return _with_name(str(value.get("message")).strip())
        if value.get("title_present") is True:
            return _with_name("Browser title equals expected title")
        if value.get("status"):
            return _with_name(str(value.get("status")).strip())
        return _with_name("Element is visible")
    if isinstance(value, list):
        text = " ".join(str(item) for item in value if item)
        return _with_name(text.strip() or "Element is visible")
    if value is None:
        return _with_name("Element is visible")
    return _with_name(str(value))


def _expected_results_to_assertions(raw: Any, mapping: Dict[str, Any] = None, title: str = None) -> List[str]:
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = [item for item in raw if item is not None]
    elif isinstance(raw, dict):
        values = [raw]
    else:
        values = []

    # Attempt central extraction once for logging/diagnostics
    try:
        detected_name = central_extract_element_name(mapping or {}, title)
    except Exception:
        detected_name = None
    LOGGER.info("_expected_results_to_assertions - detected_name=%s title=%s mapping=%s raw_count=%s", detected_name, title, mapping, len(values))

    assertions = []
    for item in values:
        if isinstance(item, str):
            text = str(item).strip()
            serialized = _expected_result_to_text(text, mapping=mapping, title=title)
        elif isinstance(item, dict):
            text = str(item.get("message") or item.get("status") or item.get("assertion") or "Element is visible").strip()
            serialized = _expected_result_to_text(text, mapping=mapping, title=title)
        else:
            text = str(item).strip()
            serialized = _expected_result_to_text(text, mapping=mapping, title=title)

        if any(blocked in serialized.lower() for blocked in _BLOCKED_EXPECTED_RESULT_PHRASES):
            LOGGER.debug("_expected_results_to_assertions - blocked generic phrase found for title=%s mapping=%s raw=%s", title, mapping, item)
            # Normalize to a clearer validation assertion
            serialized = "Validation message is displayed"
        assertions.append(serialized)

    if not assertions:
        default = _expected_result_to_text("Element is visible", mapping=mapping, title=title)
        assertions = [default]
    return assertions


def _generate_expected_results_for_test_type(
    test_type: str = "functional",
    title: str = "",
    description: str = "",
    mapping: Dict[str, Any] = None,
    input_fields: List[str] = None,
) -> List[str]:
    """Generate scenario-specific expected results based on element type, test type, and context.

    Uses element type detection to generate appropriate assertions. For example:
    - Links generate navigation-specific results (clickable, URL changes)
    - Buttons generate action-specific results (clickable, action triggered)
    - Forms generate submission-specific results (success message, no errors)
    - Text inputs generate input-specific results (visible, accepts input, value displayed)

    Args:
        test_type: The classification of the test (e.g., functional, positive, negative, navigation, security, validation, boundary).
        title: The test title or scenario name.
        description: The test description.
        mapping: Optional mapping context with field details, element type, selector, etc.
        input_fields: Optional list of input field names involved in the test.

    Returns:
        List of specific, executable expected result assertions.
    """
    if mapping is None:
        mapping = {}
    if input_fields is None:
        input_fields = []

    test_type = str(test_type or "functional").strip().lower()
    title = str(title or "").strip()
    description = str(description or "").strip()
    
    # Detect element type from multiple data sources
    element_type = detect_element_type(
        mapping=mapping,
        description=description,
        title=title,
        selector=str(mapping.get("selector") or "").strip(),
    )
    
    # Use element-specific expected results generation
    expected = get_element_specific_expected_results(
        element_type=element_type,
        test_type=test_type,
        mapping=mapping,
        description=description,
    )
    
    return expected if expected else ["Test condition is observable", "System responds as designed"]


def _automation_hints_from_item(item: Any) -> Dict[str, Any]:
    raw = item.get("automation_hints") if isinstance(item, dict) else None
    if isinstance(raw, dict):
        page_name = str(raw.get("page_name") or "Page").strip() or "Page"
        actions = raw.get("actions") or []
        assertions = raw.get("assertions") or []
        return {
            "page_name": page_name,
            "actions": [str(action) for action in actions if str(action).strip()] if isinstance(actions, list) else [],
            "assertions": [str(assertion) for assertion in assertions if str(assertion).strip()] if isinstance(assertions, list) else [],
        }
    return {
        "page_name": "Page",
        "actions": ["open_url", "verify_page_title", "verify_element_visible"],
        "assertions": ["Browser title equals expected title", "Element is visible"],
    }


def _select_best_locator_type_and_value(mapping: Dict[str, Any], selector: str = "", visible_names: set = None) -> tuple[str, str]:
    """Select the best locator type based on priority.
    
    Priority: id > name > data-testid > href > css_selector > xpath
    
    Returns:
        Tuple of (locator_type, locator_value)
    """
    mapping = mapping or {}
    visible_names = visible_names or set()
    
    # Priority 1: id attribute
    element_id = str(mapping.get("id") or "").strip()
    if element_id:
        return ("id", element_id)
    
    # Priority 2: name attribute
    name = str(mapping.get("name") or "").strip()
    if name and name.casefold() not in visible_names:
        return ("name", name)
    
    # Priority 3: data-testid attribute
    data_testid = str(mapping.get("data-testid") or mapping.get("data_testid") or "").strip()
    if data_testid and data_testid.casefold() not in visible_names:
        return ("data-testid", data_testid)
    
    # Priority 4: href attribute (for links)
    href = str(mapping.get("href") or "").strip()
    if href:
        # Use CSS selector for href-based locators
        css_selector = f"a[href='{href}']"
        return ("css_selector", css_selector)
    
    # Priority 5: selector field (typically CSS selector)
    selector = str(selector or mapping.get("selector") or "").strip()
    if selector and _looks_like_selector(selector) and selector.casefold() not in visible_names:
        return ("css_selector", selector)
    
    # Priority 6: xpath
    xpath = str(mapping.get("xpath") or "").strip()
    if xpath and xpath.casefold() not in visible_names:
        return ("xpath", xpath)
    
    return ("", "")


def _looks_like_selector(value: str) -> bool:
    return bool(
        value
        and (value.startswith(("#", ".", "[", "/")) or any(token in value for token in (">", "[", "]", "#", ":")))
    )


_PLACEHOLDER_LOCATORS = {
    "primary_content", "element", "input_field", "submit_button",
    "navigation_link", "primary_button", "target_input", "form_input",
    "feedback_message", "application_url", "expected_title", "expected_url",
    "username_field", "password_field", "login_button",
}


def _is_valid_locator(locator_type: Any, locator_value: Any) -> bool:
    valid_types = {"id", "name", "data-testid", "css_selector", "xpath"}
    locator_type = str(locator_type or "").strip().lower()
    locator_value = str(locator_value or "").strip()
    return bool(
        locator_type in valid_types
        and locator_value
        and locator_value.lower() not in _PLACEHOLDER_LOCATORS
        and not any(token in locator_value.lower() for token in _PLACEHOLDER_LOCATORS)
        and "<" not in locator_value
        and ">" not in locator_value
    )


def _sanitize_generated_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sanitized = []
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        locator_type = str(step.get("locator_type") or "").strip().lower()
        locator_value = str(step.get("locator_value") or "").strip()
        visible_names = {
            str(step.get(key) or "").strip().casefold()
            for key in ("label", "text", "element_name", "title")
            if str(step.get(key) or "").strip()
        }
        if locator_value.casefold() in visible_names:
            locator_type = ""
            locator_value = ""
        element_name = str(step.get("element_name") or "").strip()
        sanitized.append({
            **step,
            "element_name": element_name,
            "locator_type": locator_type if _is_valid_locator(locator_type, locator_value) else "",
            "locator_value": locator_value if _is_valid_locator(locator_type, locator_value) else "",
            "locator_status": "available" if _is_valid_locator(locator_type, locator_value) else "locator unavailable",
        })
    return sanitized


def _normalize_step(item: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Promote a vague test step into a Selenium-compatible control/action instruction.
    
    Preserves locator metadata from LLM if provided, or enhances steps with locator detection.
    Ensures all steps are Selenium-ready with full metadata.
    """
    raw_action = str(item.get("action") or item.get("verb") or item.get("name") or "perform_action").strip().lower()
    
    # Extract locator information (may be provided by LLM or populated via mapping)
    locator_type = str(item.get("locator_type") or "").strip() or None
    locator_value = str(item.get("locator_value") or "").strip() or None
    element_name = str(item.get("element_name") or "").strip() or None
    selector = str(item.get("selector") or item.get("target") or "").strip() or None
    mapping = item.get("mapping") or {}

    visible_names = {
        str(item.get(key) or "").strip().casefold()
        for key in ("label", "text", "element_name", "title")
        if str(item.get(key) or "").strip()
    }
    if isinstance(mapping, dict):
        visible_names.update(
            str(mapping.get(key) or "").strip().casefold()
            for key in ("label", "text")
            if str(mapping.get(key) or "").strip()
        )
    if locator_value and locator_value.casefold() in visible_names:
        locator_type = None
        locator_value = None
    if locator_type in {"css", "css_selector"} and locator_value and not _looks_like_selector(locator_value):
        locator_type = None
        locator_value = None
    
    # If locator metadata is missing, try to detect it
    if not locator_type or not locator_value:
        locator_type, locator_value = _select_best_locator_type_and_value(mapping, selector, visible_names)
    
    # If element_name is still missing, try to get it from mapping
    if not element_name:
        element_name = str(mapping.get("label") or mapping.get("field_name") or mapping.get("name") or mapping.get("text") or "").strip() or None

    # Action vocabulary normalization
    if raw_action in {"open", "open_url", "navigate", "launch"} or "page load" in raw_action:
        action = "open_url"
        payload = {
            "step_number": index, 
            "action": action, 
            "target": selector or item.get("url") or "application_url",
            "element_name": "Application",
            "locator_type": "url",
            "locator_value": selector or item.get("url") or "",
        }
    elif "verify title" in raw_action or "title" in raw_action or raw_action in {"check title", "browser title"}:
        action = "verify_page_title"
        expected = str(item.get("expected_value") or item.get("value") or "").strip()
        payload = {
            "step_number": index, 
            "action": action,
            "element_name": "Page Title",
            "locator_type": "title",
            "locator_value": expected,
            "expected_value": expected
        }
    elif "verify" in raw_action and "url" in raw_action:
        action = "verify_url"
        expected = str(item.get("expected_value") or item.get("value") or "").strip()
        payload = {
            "step_number": index,
            "action": action,
            "locator_type": "url",
            "locator_value": expected,
            "expected_value": expected
        }
    elif "visible" in raw_action or "content" in raw_action or "verify" in raw_action or raw_action in {"observe", "inspect", "check"}:
        action = "verify_element_visible"
        payload = {
            "step_number": index, 
            "action": action, 
            "target": selector,
            "element_name": element_name,
            "selector": selector,
            "locator_type": locator_type,
            "locator_value": locator_value,
        }
    elif "click" in raw_action or raw_action in {"click_element", "click_submit"}:
        action = "click_element"
        payload = {
            "step_number": index, 
            "action": action, 
            "target": selector,
            "element_name": element_name,
            "selector": selector,
            "locator_type": locator_type,
            "locator_value": locator_value,
        }
    elif raw_action in {"select_checkbox"}:
        action = "select_checkbox"
        payload = {
            "step_number": index,
            "action": action,
            "target": selector,
            "element_name": element_name,
            "selector": selector,
            "locator_type": locator_type,
            "locator_value": locator_value,
        }
    elif raw_action in {"select_radio"}:
        action = "select_radio"
        payload = {
            "step_number": index,
            "action": action,
            "target": selector,
            "element_name": element_name,
            "selector": selector,
            "locator_type": locator_type,
            "locator_value": locator_value,
        }
    elif raw_action in {"select_dropdown_option", "select_dropdown"}:
        action = "select_dropdown_option"
        payload = {
            "step_number": index,
            "action": action,
            "target": selector,
            "element_name": element_name,
            "selector": selector,
            "locator_type": locator_type,
            "locator_value": locator_value,
            "value": item.get("value"),
        }
    elif raw_action in {"upload_file"}:
        action = "upload_file"
        payload = {
            "step_number": index,
            "action": action,
            "target": selector,
            "element_name": element_name,
            "selector": selector,
            "locator_type": locator_type,
            "locator_value": locator_value,
            "input_value": item.get("input_value") or item.get("value"),
        }
    elif "enter" in raw_action or "fill" in raw_action or "text" in raw_action or raw_action in {"enter_text"}:
        action = "enter_text"
        payload = {
            "step_number": index, 
            "action": action, 
            "target": selector,
            "element_name": element_name,
            "selector": selector,
            "locator_type": locator_type,
            "locator_value": locator_value,
            "value": item.get("value") or item.get("input_value"),
        }
    elif "error" in raw_action or "message" in raw_action:
        action = "assert_validation_message"
        payload = {
            "step_number": index, 
            "action": action, 
            "target": selector,
            "element_name": "Validation Message",
            "selector": selector,
            "locator_type": locator_type,
            "locator_value": locator_value,
        }
    else:
        # Generic action - preserve all provided fields
        action = raw_action if raw_action and raw_action != "perform_action" else "perform_action"
        payload = {"step_number": index, "action": action}
        
        # Add optional fields if present
        if selector:
            payload["target"] = selector
            payload["selector"] = selector
            payload["locator_type"] = locator_type
            payload["locator_value"] = locator_value
        if element_name:
            payload["element_name"] = element_name
        if item.get("value") is not None:
            payload["value"] = item.get("value")
        if item.get("input_value") is not None:
            payload["input_value"] = item.get("input_value")
        if item.get("expected_value") is not None:
            payload["expected_value"] = item.get("expected_value")

    payload.setdefault("element_name", element_name or "")
    payload.setdefault("locator_type", locator_type or "")
    payload.setdefault("locator_value", locator_value or "")
    if not _is_valid_locator(payload.get("locator_type"), payload.get("locator_value")):
        payload["locator_type"] = ""
        payload["locator_value"] = ""
        payload["locator_status"] = "locator unavailable"
    else:
        payload["locator_status"] = "available"
    return payload


def _extract_scenario_list(scenarios: Any) -> List[Dict[str, Any]]:
    if isinstance(scenarios, dict):
        candidate = scenarios.get("scenarios")
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    if isinstance(scenarios, list):
        return [item for item in scenarios if isinstance(item, dict)]
    return []


def _build_fallback_testcases(scenarios: Any) -> List[Dict[str, Any]]:
    scenario_items = _extract_scenario_list(scenarios)
    if not scenario_items:
        test_type = "functional"
        expected_results = _generate_expected_results_for_test_type(
            test_type=test_type, title="Verify page renders", description="Ensure the target page renders without errors."
        )
        return [
            {
                "id": "fallback-t1",
                "title": "Verify page renders",
                "description": "Ensure the target page renders without errors.",
                "test_type": test_type,
                "preconditions": [],
                "steps": [
                    {
                        "step_number": 1, 
                        "action": "open_url", 
                        "target": "application_url",
                        "element_name": "Application",
                        "locator_type": "url",
                        "locator_value": "application_url"
                    }
                ],
                "expected_result": expected_results[0] if expected_results else "Element is visible",
                "expected_results": expected_results,
            }
        ]

    fallback_cases = []
    for index, scenario in enumerate(scenario_items, start=1):
        title = str(scenario.get("title") or f"Scenario {index}").strip()
        description = str(scenario.get("description") or f"Validate {title}").strip()
        case_id = f"t{index}"
        test_type = str(scenario.get("test_type") or "functional").strip().lower()
        mapping = scenario.get("mapping") or {}
        steps = [
            {
                "step_number": 1, 
                "action": "open_url", 
                "target": "application_url",
                "element_name": "Application",
                "locator_type": "url",
                "locator_value": "application_url"
            }
        ]
        lowered = title.lower()

        # Determine test_type based on title if not explicitly provided
        if test_type == "functional" or not test_type:
            if "form" in lowered or "submit" in lowered:
                test_type = "positive" if "invalid" not in lowered else "negative"
            elif "navigation" in lowered or "redirect" in lowered:
                test_type = "navigation"
            elif "button" in lowered or "click" in lowered:
                test_type = "functional"
            elif "link" in lowered:
                test_type = "functional"
            elif "input" in lowered or "field" in lowered:
                test_type = "functional"
            else:
                test_type = "functional"

        # Generate scenario-specific steps with Selenium-ready locators
        if "form" in lowered:
            locator_type, locator_value = _select_best_locator_type_and_value(mapping, "form_input")
            steps.append({
                "step_number": 2, 
                "action": "enter_text", 
                "target": "form_input",
                "element_name": str(mapping.get("label") or mapping.get("name") or "Form Input").strip() or "Form Input",
                "locator_type": locator_type,
                "locator_value": locator_value,
                "value": "valid-value"
            })
            submit_locator_type, submit_locator_value = _select_best_locator_type_and_value(mapping, "submit_button")
            steps.append({
                "step_number": 3, 
                "action": "click_element", 
                "target": "submit_button",
                "element_name": "Submit",
                "locator_type": submit_locator_type,
                "locator_value": submit_locator_value
            })
        elif "login" in lowered:
            username_locator_type, username_locator_value = _select_best_locator_type_and_value({"name": "username", "id": "username_field"}, "username_field")
            steps.append({
                "step_number": 2, 
                "action": "enter_text", 
                "target": "username_field",
                "element_name": "Username",
                "locator_type": username_locator_type,
                "locator_value": username_locator_value,
                "value": "valid-user"
            })
            password_locator_type, password_locator_value = _select_best_locator_type_and_value({"name": "password", "id": "password_field"}, "password_field")
            steps.append({
                "step_number": 3, 
                "action": "enter_text", 
                "target": "password_field",
                "element_name": "Password",
                "locator_type": password_locator_type,
                "locator_value": password_locator_value,
                "value": "valid-password"
            })
            login_locator_type, login_locator_value = _select_best_locator_type_and_value({"id": "login_button"}, "login_button")
            steps.append({
                "step_number": 4, 
                "action": "click_element", 
                "target": "login_button",
                "element_name": "Login",
                "locator_type": login_locator_type,
                "locator_value": login_locator_value
            })
        elif "button" in lowered or "click" in lowered or "action" in lowered:
            button_locator_type, button_locator_value = _select_best_locator_type_and_value(mapping, "primary_button")
            steps.append({
                "step_number": 2, 
                "action": "click_element", 
                "target": "primary_button",
                "element_name": str(mapping.get("text") or mapping.get("label") or "Button").strip() or "Button",
                "locator_type": button_locator_type,
                "locator_value": button_locator_value
            })
        elif "link" in lowered:
            link_locator_type, link_locator_value = _select_best_locator_type_and_value(mapping, "navigation_link")
            steps.append({
                "step_number": 2, 
                "action": "click_element", 
                "target": "navigation_link",
                "element_name": str(mapping.get("text") or mapping.get("label") or "Link").strip() or "Link",
                "locator_type": link_locator_type,
                "locator_value": link_locator_value
            })
        elif "input" in lowered or "field" in lowered:
            input_locator_type, input_locator_value = _select_best_locator_type_and_value(mapping, "target_input")
            steps.append({
                "step_number": 2, 
                "action": "enter_text", 
                "target": "target_input",
                "element_name": str(mapping.get("label") or mapping.get("name") or "Input").strip() or "Input",
                "locator_type": input_locator_type,
                "locator_value": input_locator_value,
                "value": "sample"
            })
        else:
            steps.append({
                "step_number": 2, 
                "action": "verify_page_title",
                "element_name": "Page Title",
                "locator_type": "title",
                "locator_value": "demosite",
                "expected_value": "demosite"
            })
            steps.append({
                "step_number": 3, 
                "action": "verify_element_visible", 
                "target": "primary_content",
                "element_name": "Primary Content",
                "locator_type": "css_selector",
                "locator_value": "primary_content"
            })

        # Generate dynamic expected results based on test_type and context
        expected_results = _generate_expected_results_for_test_type(
            test_type=test_type, title=title, description=description, mapping=mapping
        )

        fallback_cases.append(
            {
                "id": case_id,
                "scenario_id": _source_scenario_id(scenario),
                "title": title,
                "description": description,
                "test_type": test_type,
                "preconditions": ["The application is available", "The user has access to the target page"],
                "steps": _sanitize_generated_steps(steps),
                "expected_results": expected_results,
                "expected_result": expected_results[0] if expected_results else "Element is visible",
            }
        )

    return fallback_cases


def _normalize_required_data(item: Any) -> List[Dict[str, Any]]:
    raw = item.get("required_data") if isinstance(item, dict) else None
    if isinstance(raw, list):
        normalized = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            field_name = str(entry.get("field_name") or "").strip()
            if not field_name:
                continue
            normalized.append({
                "field_name": field_name,
                "field_type": str(entry.get("field_type") or "text").strip() or "text",
                "business_purpose": str(entry.get("business_purpose") or "User interaction value").strip() or "User interaction value",
                "expected_format": str(entry.get("expected_format") or "value").strip() or "value",
                "validation_rules": [str(rule) for rule in (entry.get("validation_rules") or []) if str(rule).strip()] or ["cannot be empty when required"],
            })
        return normalized
    return []


def _normalize_testcases(parsed: Any, scenarios: Any) -> List[Dict[str, Any]]:
    if isinstance(parsed, dict):
        if isinstance(parsed.get("test_cases"), list):
            candidates = parsed["test_cases"]
        elif isinstance(parsed.get("testcases"), list):
            candidates = parsed["testcases"]
        else:
            candidates = []
    elif isinstance(parsed, list):
        candidates = parsed
    else:
        candidates = []

    normalized = []
    seen_titles = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        if title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        input_fields = [str(alias) for alias in (item.get("input_fields") or []) if str(alias).strip()] or []
        required_data = _normalize_required_data(item)
        if not required_data and input_fields:
            required_data = [{
                "field_name": field,
                "field_type": "text",
                "business_purpose": "User interaction value",
                "expected_format": "value",
                "validation_rules": ["cannot be empty when required"],
            } for field in input_fields]

        steps = item.get("steps") or item.get("test_steps") or [{"action": "verify_element_visible", "target": "primary_content"}]
        item_mapping = item.get("mapping") or {}
        if isinstance(steps, list) and steps:
            normalized_steps = []
            for index, step in enumerate(steps, start=1):
                if isinstance(step, dict):
                    normalized_steps.append(
                        _normalize_step(
                            {"mapping": item_mapping, **step},
                            index,
                        )
                    )
                else:
                    normalized_steps.append({
                        "step_number": index,
                        "action": "verify_element_visible",
                        "target": "primary_content",
                        "value": step,
                    })
            steps = _sanitize_generated_steps(normalized_steps)
        else:
            steps = []

        test_type = str(item.get("test_type") or "functional").strip().lower()
        mapping = item.get("mapping") or {}
        expected_results = item.get("expected_results") or item.get("expected_result") or []
        try:
            detected_name = central_extract_element_name(mapping or {}, title)
        except Exception:
            detected_name = None
        LOGGER.info("testcases_service - preparing expected_results: title=%s mapping=%s detected_name=%s raw_expected=%s", title, mapping, detected_name, expected_results)
        for step in steps:
            LOGGER.info(
                "Agent1 locator: element_name=%s locator_type=%s locator_value=%s",
                step.get("element_name"),
                step.get("locator_type"),
                step.get("locator_value"),
            )
        expected_results = _expected_results_to_assertions(expected_results, mapping=mapping, title=title)

        # If no expected results were provided or only generic fallback, generate dynamic results based on test intent
        if not expected_results or expected_results == ["Element is visible"]:
            expected_results = _generate_expected_results_for_test_type(
                test_type=test_type, title=title, description=item.get("description") or f"Validate {title}", mapping=mapping, input_fields=input_fields
            )

        if not expected_results:
            expected_results = ["Element is visible"]

        normalized.append(
            {
                "id": item.get("id") or f"t{len(normalized) + 1}",
                "scenario_id": item.get("scenario_id") or item.get("test_scenario_id") or f"TS_{len(normalized)+1:02d}",
                "title": title,
                "description": item.get("description") or f"Validate {title}",
                "test_type": test_type,
                "priority": item.get("priority") or "medium",
                "preconditions": item.get("preconditions") or [],
                "steps": steps,
                "expected_results": expected_results,
                "input_fields": input_fields,
                "required_data": required_data,
                "automation_hints": _automation_hints_from_item(item),
                "mapping": mapping,
                "expected_result": expected_results[0] if expected_results else "Element is visible",
            }
        )

    target_count = max(8, len(_extract_scenario_list(scenarios)))
    if len(normalized) < target_count:
        fallback_cases = _build_fallback_testcases(scenarios)
        for case in fallback_cases:
            case_title = str(case.get("title") or "").lower()
            if any(existing.get("title", "").lower() == case_title for existing in normalized):
                continue
            normalized.append(case)
            if len(normalized) >= target_count:
                break

    if len(normalized) < target_count:
        return _build_fallback_testcases(scenarios)

    return normalized


async def generate_testcases(scenarios: Any) -> Dict[str, Any]:
    """Generate detailed test cases from scenarios using GroqService.

    Args:
        scenarios: The scenarios data (list or dict) produced by the scenarios generator.

    Returns:
        Dict with key "testcases": [ ... ]

    Raises:
        GroqServiceError if the LLM fails or returns unexpected output.
    """
    # Annotate scenarios with a scenario_category to provide explicit intent guidance
    try:
        from app.services.intent_classifier import classify_scenario
    except Exception:
        classify_scenario = None

    annotated = scenarios
    try:
        if classify_scenario and isinstance(scenarios, dict) and isinstance(scenarios.get("scenarios"), list):
            annotated = {**scenarios}
            annotated_list = []
            for s in scenarios.get("scenarios", []):
                if isinstance(s, dict):
                    try:
                        cat = classify_scenario(s.get("description") or s.get("title"), s.get("test_type"), s.get("mapping"))
                    except Exception:
                        cat = None
                    s = {**s, "scenario_category": cat} if cat else s
                annotated_list.append(s)
            annotated["scenarios"] = annotated_list
    except Exception:
        annotated = scenarios

    groq = GroqService()
    try:
        parsed = await groq.generate_testcases(annotated)
    except GroqServiceError:
        return {"testcases": _build_fallback_testcases(scenarios)}

    normalized = _normalize_testcases(parsed, scenarios)
    return {"testcases": normalized}
