import os
import logging
import re
from typing import Dict, Any, List, Tuple

from app.core.groq_service import GroqService, GroqServiceError
from app.services.element_detection import (
    detect_element_type,
    get_element_specific_steps,
    get_element_specific_expected_results,
    get_element_specific_automation_hints,
    ElementType,
)
from app.services.intent_classifier import extract_element_name

LOGGER = logging.getLogger(__name__)

USE_AI_SCENARIOS = os.getenv("USE_AI_SCENARIOS", "false").lower() in ("1", "true", "yes")


def _infer_test_type(text: str, mapping: Dict[str, Any] = None) -> str:
    """Infer a strict Agent 1 test_type vocabulary from description + mapping + intent."""
    raw = str(text or "").lower()
    mapping_payload = mapping or {}
    if isinstance(mapping_payload, dict):
        for key, value in mapping_payload.items():
            raw += " " + str(key or "").lower() + " " + str(value or "").lower()

    # Strong direct mapping override as requested by the platform contract.
    mode = None
    if isinstance(mapping_payload, dict):
        mode = str(mapping_payload.get("mode") or "").strip().lower()
    if mode == "submit-valid":
        return "positive"
    if mode == "submit-invalid":
        return "negative"

    # Detect semantic intent using the requested vocabulary.
    security_tokens = ("xss", "sql injection", "unauthorized access", "authentication", "authorization", "security")
    navigation_tokens = ("redirect", "navigation", "routing", "route", "navigate")
    validation_tokens = ("required field", "required", "validation", "error message", "error", "empty", "blank", "missing")
    boundary_tokens = ("max length", "min length", "boundary", "limit", "threshold", "maxlength", "minlength")
    functional_tokens = ("page load", "page title", "page loads", "page load", "form exists", "form is present", "field exists", "element visible", "visible", "present")
    negative_tokens = ("invalid", "failure", "reject", "negative")
    positive_tokens = ("submit", "success", "valid", "happy path", "submit-valid")

    if any(token in raw for token in security_tokens):
        return "security"
    if any(token in raw for token in navigation_tokens):
        return "navigation"
    if any(token in raw for token in validation_tokens):
        return "validation"
    if any(token in raw for token in boundary_tokens):
        return "boundary"
    if any(token in raw for token in functional_tokens):
        return "functional"
    if any(token in raw for token in negative_tokens):
        return "negative"
    if any(token in raw for token in positive_tokens):
        return "positive"

    return "functional"


def _select_scenario_template(description: str, test_type: str, mapping: Dict[str, Any]) -> str:
    """
    Select scenario template based on business intent priority:
    1. Scenario Description (keywords in description)
    2. Test Type (functional, positive, negative, validation, etc.)
    3. Mapping Metadata (mode field)
    4. Element Type (fallback only)
    
    Returns template name: PAGE_LOAD, FORM_POSITIVE, FORM_NEGATIVE, INPUT_FIELD, NAVIGATION, BUTTON_VALIDATION
    """
    description_lower = description.lower()
    mapping_payload = mapping or {}
    mode = str(mapping_payload.get("mode") or "").strip().lower()
    
    # Priority 1: Check scenario description for explicit intent
    if "page load" in description_lower or "page is visible" in description_lower or "homepage" in description_lower:
        return "PAGE_LOAD"
    
    if "form" in description_lower and "submission" in description_lower:
        if "invalid" in description_lower or "negative" in description_lower or "error" in description_lower or "validation feedback" in description_lower:
            return "FORM_NEGATIVE"
        else:
            return "FORM_POSITIVE"
    
    if "validation" in description_lower or "error message" in description_lower or "required field" in description_lower:
        return "FORM_NEGATIVE"
    
    if "navigate" in description_lower or "redirect" in description_lower or "link" in description_lower:
        return "NAVIGATION"
    
    if "button" in description_lower or "cta" in description_lower:
        return "BUTTON_VALIDATION"
    
    if "field" in description_lower or "input" in description_lower or "enter" in description_lower:
        if "invalid" in description_lower or "negative" in description_lower:
            return "FORM_NEGATIVE"
        else:
            return "INPUT_FIELD"
    
    # Priority 2: Check test_type
    if test_type == "validation":
        return "FORM_NEGATIVE"
    elif test_type == "negative":
        return "FORM_NEGATIVE"
    elif test_type == "positive":
        # Could be form or input, but check description for form indicators
        if "form" in description_lower or "submit" in description_lower:
            return "FORM_POSITIVE"
        else:
            return "INPUT_FIELD"
    elif test_type == "navigation":
        return "NAVIGATION"
    elif test_type == "functional":
        if "page load" in description_lower or "page" in description_lower:
            return "PAGE_LOAD"
        else:
            return "INPUT_FIELD"
    
    # Priority 3: Check mapping.mode
    if mode == "submit-invalid":
        return "FORM_NEGATIVE"
    elif mode == "submit-valid":
        return "FORM_POSITIVE"
    
    # Fallback
    return "INPUT_FIELD"


def _generate_page_load_steps() -> List[Dict[str, Any]]:
    """PAGE LOAD template steps."""
    return [
        {"step_number": 1, "description": "Open the application"},
        {"step_number": 2, "description": "Verify the page loads successfully"},
        {"step_number": 3, "description": "Verify the page title is displayed correctly"},
        {"step_number": 4, "description": "Verify main content is visible"},
    ]


def _generate_page_load_expected_results() -> List[str]:
    """PAGE LOAD template expected results."""
    return [
        "Page loads successfully",
        "Page title is displayed correctly",
        "Main content is visible",
        "No errors are shown",
    ]


def _generate_form_positive_steps(form_name: str = "form") -> List[Dict[str, Any]]:
    """FORM SUBMISSION POSITIVE template steps."""
    return [
        {"step_number": 1, "description": "Open the application"},
        {"step_number": 2, "description": f"Locate the {form_name}"},
        {"step_number": 3, "description": "Enter valid data into all required fields"},
        {"step_number": 4, "description": f"Submit the {form_name}"},
        {"step_number": 5, "description": "Verify successful submission"},
    ]


def _generate_form_positive_expected_results(form_name: str = "form") -> List[str]:
    """FORM SUBMISSION POSITIVE template expected results."""
    return [
        f"{form_name} submits successfully",
        "Success message is displayed",
        "No validation errors are shown",
        "User is redirected or confirmation is visible",
    ]


def _generate_form_negative_steps(form_name: str = "form") -> List[Dict[str, Any]]:
    """FORM SUBMISSION NEGATIVE template steps."""
    return [
        {"step_number": 1, "description": "Open the application"},
        {"step_number": 2, "description": f"Locate the {form_name}"},
        {"step_number": 3, "description": "Leave required fields blank or enter invalid data"},
        {"step_number": 4, "description": f"Attempt to submit the {form_name}"},
        {"step_number": 5, "description": "Verify validation feedback is displayed"},
    ]


def _generate_form_negative_expected_results(form_name: str = "form") -> List[str]:
    """FORM SUBMISSION NEGATIVE template expected results."""
    return [
        "Form submission is prevented",
        "Validation message is displayed",
        "Required fields are highlighted or indicated",
        "User is informed of the validation errors",
    ]


def _generate_input_field_steps(field_name: str = "field") -> List[Dict[str, Any]]:
    """INPUT FIELD VERIFICATION template steps."""
    return [
        {"step_number": 1, "description": "Open the application"},
        {"step_number": 2, "description": f"Locate the {field_name}"},
        {"step_number": 3, "description": f"Verify {field_name} is visible and accessible"},
        {"step_number": 4, "description": f"Enter data into the {field_name}"},
        {"step_number": 5, "description": f"Verify the entered value is displayed in the {field_name}"},
    ]


def _generate_input_field_expected_results(field_name: str = "field") -> List[str]:
    """INPUT FIELD VERIFICATION template expected results."""
    return [
        f"{field_name} is visible",
        f"{field_name} is accessible",
        f"{field_name} accepts user input",
        "Entered value is displayed correctly",
    ]


def _generate_navigation_steps(link_name: str = "link", destination: str = "target page") -> List[Dict[str, Any]]:
    """NAVIGATION template steps."""
    return [
        {"step_number": 1, "description": "Open the application"},
        {"step_number": 2, "description": f"Locate the {link_name}"},
        {"step_number": 3, "description": f"Click the {link_name}"},
        {"step_number": 4, "description": f"Verify navigation to the {destination}"},
    ]


def _generate_navigation_expected_results(link_name: str = "link", destination: str = "target page") -> List[str]:
    """NAVIGATION template expected results."""
    return [
        f"{link_name} is visible and clickable",
        "Navigation succeeds",
        f"URL changes to destination ({destination})",
        f"{destination} loads successfully",
    ]


def _generate_button_validation_steps(button_name: str = "button") -> List[Dict[str, Any]]:
    """BUTTON VALIDATION template steps."""
    return [
        {"step_number": 1, "description": "Open the application"},
        {"step_number": 2, "description": f"Locate the {button_name}"},
        {"step_number": 3, "description": f"Click the {button_name}"},
        {"step_number": 4, "description": "Verify the expected action is triggered"},
    ]


def _generate_button_validation_expected_results(button_name: str = "button") -> List[str]:
    """BUTTON VALIDATION template expected results."""
    return [
        f"{button_name} is visible and clickable",
        f"{button_name} is enabled",
        "Expected action is triggered",
    ]


def _scenario_steps_for_mapping(mapping: Dict[str, Any], description: str = "", test_type: str = "functional") -> List[Dict[str, Any]]:
    """
    Generate business-level QA steps using template-based approach.
    
    Steps are selected based on business intent (test_type, description) not element type.
    Priority: Description > Test Type > Mapping > Element Type
    """
    if not isinstance(mapping, dict):
        mapping = {}

    field_type = _field_type_for_mapping(mapping)
    field_name = extract_element_name(mapping, description) or str(
        mapping.get("label") or mapping.get("field_name") or mapping.get("name") or "field"
    ).strip()
    if field_type == "radio":
        return [
            {"step_number": 1, "description": f"Verify '{field_name}' radio button is visible and enabled."},
            {"step_number": 2, "description": f"Select the '{field_name}' radio button."},
            {"step_number": 3, "description": f"Verify '{field_name}' radio button is selected."},
        ]
    if field_type == "checkbox":
        return [
            {"step_number": 1, "description": f"Verify '{field_name}' checkbox is visible and enabled."},
            {"step_number": 2, "description": f"Select and deselect the '{field_name}' checkbox."},
            {"step_number": 3, "description": f"Verify '{field_name}' checkbox state changes correctly."},
        ]
    if field_type == "dropdown":
        return [
            {"step_number": 1, "description": f"Verify '{field_name}' dropdown is visible."},
            {"step_number": 2, "description": f"Select an option from the '{field_name}' dropdown."},
            {"step_number": 3, "description": f"Verify the selected option is displayed in '{field_name}'."},
        ]
    if field_type == "file":
        return [
            {"step_number": 1, "description": f"Verify '{field_name}' upload control is visible."},
            {"step_number": 2, "description": f"Upload a valid file using '{field_name}'."},
            {"step_number": 3, "description": f"Verify the uploaded filename is displayed for '{field_name}'."},
        ]
    
    # Select template based on business intent
    template = _select_scenario_template(description, test_type, mapping)
    
    # Derive element names using intent classifier utility
    derived_name = extract_element_name(mapping, description)
    field_name = derived_name or str(mapping.get("label") or mapping.get("field_name") or mapping.get("name") or "field").strip()
    form_name = derived_name or str(mapping.get("form_name") or "form").strip()
    link_name = derived_name or str(mapping.get("text") or mapping.get("label") or "link").strip()
    destination = str(mapping.get("href") or "target page").strip()
    button_name = derived_name or str(mapping.get("text") or mapping.get("label") or "button").strip()

    LOGGER.debug("_scenario_steps_for_mapping - description=%s mapping=%s derived_name=%s", description, mapping, derived_name)

    # Generate steps based on selected template
    if template == "PAGE_LOAD":
        return _generate_page_load_steps()
    elif template == "FORM_POSITIVE":
        return _generate_form_positive_steps(form_name)
    elif template == "FORM_NEGATIVE":
        return _generate_form_negative_steps(form_name)
    elif template == "INPUT_FIELD":
        return _generate_input_field_steps(field_name)
    elif template == "NAVIGATION":
        return _generate_navigation_steps(link_name, destination)
    elif template == "BUTTON_VALIDATION":
        return _generate_button_validation_steps(button_name)
    else:
        return _generate_input_field_steps(field_name)


def _scenario_expected_results_for_mapping(mapping: Dict[str, Any], description: str = "", test_type: str = "functional") -> List[str]:
    """
    Generate business-level expected results using template-based approach.
    
    Results are selected based on business intent (test_type, description) not element type.
    Priority: Description > Test Type > Mapping > Element Type
    """
    if not isinstance(mapping, dict):
        mapping = {}

    field_type = _field_type_for_mapping(mapping)
    if field_type in {"radio", "checkbox", "dropdown", "file"}:
        detected = detect_element_type(mapping, description=description)
        return get_element_specific_expected_results(detected, test_type, mapping, description)
    
    # Select template based on business intent
    template = _select_scenario_template(description, test_type, mapping)
    
    # Derive element names using intent classifier utility
    derived_name = extract_element_name(mapping, description)
    field_name = derived_name or str(mapping.get("label") or mapping.get("field_name") or mapping.get("name") or "field").strip()
    form_name = derived_name or str(mapping.get("form_name") or "form").strip()
    link_name = derived_name or str(mapping.get("text") or mapping.get("label") or "link").strip()
    destination = str(mapping.get("href") or "target page").strip()
    button_name = derived_name or str(mapping.get("text") or mapping.get("label") or "button").strip()

    # Log decision
    LOGGER.debug("_scenario_expected_results_for_mapping - description=%s mapping=%s derived_name=%s", description, mapping, derived_name)

    # Generate expected results based on selected template
    if template == "PAGE_LOAD":
        return _generate_page_load_expected_results()
    elif template == "FORM_POSITIVE":
        return _generate_form_positive_expected_results(form_name)
    elif template == "FORM_NEGATIVE":
        return _generate_form_negative_expected_results(form_name)
    elif template == "INPUT_FIELD":
        return _generate_input_field_expected_results(field_name)
    elif template == "NAVIGATION":
        return _generate_navigation_expected_results(link_name, destination)
    elif template == "BUTTON_VALIDATION":
        return _generate_button_validation_expected_results(button_name)
    else:
        return _generate_input_field_expected_results(field_name)


def _field_type_for_mapping(mapping: Dict[str, Any]) -> str:
    """Return a stable semantic field type for scenario compatibility checks."""
    mapping = mapping or {}
    raw = str(
        mapping.get("field_type")
        or mapping.get("type")
        or mapping.get("input_type")
        or mapping.get("element_type")
        or mapping.get("tag_name")
        or mapping.get("tag")
        or "text"
    ).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "text_input": "text", "textinput": "text", "input": "text",
        "email_input": "email", "phone_input": "phone", "phone_number": "phone",
        "number_input": "number", "date_input": "date", "textarea": "textarea",
        "radio_button": "radio", "radio_input": "radio", "select": "dropdown",
        "select_input": "dropdown", "file_upload": "file", "upload": "file",
        "checkbox_input": "checkbox", "button": "button", "link": "link",
    }
    return aliases.get(raw, raw)


_FIELD_SCENARIO_RULES = {
    "text": [
        ("positive", "Verify '{name}' accepts valid text input."),
        ("negative", "Verify '{name}' rejects invalid text input."),
        ("boundary", "Verify '{name}' enforces its text length boundary."),
        ("validation", "Verify required text field '{name}' shows validation when empty."),
    ],
    "email": [
        ("positive", "Verify '{name}' accepts a valid email format."),
        ("negative", "Verify '{name}' rejects an invalid email format."),
        ("validation", "Verify required email field '{name}' shows validation when empty."),
    ],
    "textarea": [
        ("positive", "Verify '{name}' accepts multiline text."),
        ("boundary", "Verify '{name}' enforces its maximum text length."),
        ("validation", "Verify required textarea '{name}' shows validation when empty."),
    ],
    "phone": [
        ("positive", "Verify '{name}' accepts a valid phone number."),
        ("negative", "Verify '{name}' rejects an invalid phone number."),
        ("boundary", "Verify '{name}' enforces the phone number length."),
    ],
    "radio": [
        ("functional", "Verify '{name}' radio button is visible and enabled."),
        ("positive", "Verify '{name}' radio button can be selected."),
        ("boundary", "Verify only one option in the '{name}' radio group can be selected."),
        ("validation", "Verify the mandatory '{name}' radio group requires one selection."),
    ],
    "checkbox": [
        ("positive", "Verify '{name}' checkbox can be selected and deselected."),
        ("boundary", "Verify '{name}' checkbox group supports the allowed multiple selections."),
        ("validation", "Verify mandatory checkbox selection is enforced for '{name}'."),
    ],
    "dropdown": [
        ("positive", "Verify an option can be selected from '{name}' dropdown."),
        ("negative", "Verify '{name}' dropdown handles an invalid option."),
        ("validation", "Verify '{name}' dropdown default value is validated."),
    ],
    "date": [
        ("positive", "Verify '{name}' accepts a valid date."),
        ("negative", "Verify '{name}' rejects an invalid date."),
        ("boundary", "Verify '{name}' enforces its boundary date."),
    ],
    "file": [
        ("positive", "Verify '{name}' accepts a valid file upload."),
        ("negative", "Verify '{name}' rejects an invalid file type."),
        ("boundary", "Verify '{name}' enforces the file size limit."),
    ],
}


def _scenario_compatible(description: str, mapping: Dict[str, Any]) -> bool:
    """Reject scenarios whose actions contradict the mapped control semantics."""
    field_type = _field_type_for_mapping(mapping)
    if field_type not in _FIELD_SCENARIO_RULES:
        return True
    text = str(description or "").casefold()
    forbidden = {
        "radio": ("enter", "typed value", "text input", "leave", "blank", "entered value"),
        "checkbox": ("enter text", "typed value", "entered value"),
        "dropdown": ("enter free text", "enter text", "typed value"),
    }
    if any(token in text for token in forbidden.get(field_type, ())):
        return False
    if field_type not in {"text", "email", "textarea", "phone", "number", "date", "file"}:
        if "accepts input" in text or "accepts user input" in text:
            return False
    return True


def _compatible_field_scenarios(mapping: Dict[str, Any]) -> List[Tuple[str, str]]:
    field_type = _field_type_for_mapping(mapping)
    name = _scenario_name(mapping, field_type)
    scenarios = [(test_type, description.format(name=name)) for test_type, description in _FIELD_SCENARIO_RULES.get(field_type, [])]
    if field_type == "radio" and len(_radio_options(mapping)) < 2:
        scenarios = [item for item in scenarios if "only one option" not in item[1].lower()]
    return scenarios


def _radio_options(mapping: Dict[str, Any]) -> List[str]:
    raw_options = (
        mapping.get("options")
        or mapping.get("radio_options")
        or mapping.get("group_options")
        or mapping.get("choices")
        or []
    ) if isinstance(mapping, dict) else []
    if not isinstance(raw_options, list):
        return []
    options = []
    for option in raw_options:
        if isinstance(option, dict):
            value = option.get("label") or option.get("text") or option.get("value") or option.get("name")
        else:
            value = option
        if str(value or "").strip():
            options.append(str(value).strip())
    return list(dict.fromkeys(options))


def _scenario_name(mapping: Dict[str, Any], field_type: str | None = None) -> str:
    mapping = mapping or {}
    field_type = field_type or _field_type_for_mapping(mapping)
    if field_type == "radio":
        group_name = (
            mapping.get("group_name")
            or mapping.get("group_label")
            or mapping.get("radio_group_name")
            or mapping.get("group")
        )
        if isinstance(group_name, str) and group_name.strip():
            return group_name.strip()
    return extract_element_name(mapping, "") or str(
        mapping.get("label") or mapping.get("field_name") or mapping.get("name") or "field"
    ).strip()


def _scenario_behavior(description: str) -> str:
    text = str(description or "").casefold()
    if "only one" in text or "single selection" in text or "one option" in text:
        return "radio_single_selection"
    if "mandatory" in text or "required" in text or "when empty" in text or "left blank" in text:
        return "required_validation"
    if "deselect" in text or "multiple selection" in text:
        return "checkbox_selection"
    if "selectable" in text or "can be selected" in text or "selected" in text:
        return "selection"
    if "invalid" in text or "reject" in text:
        return "invalid_input"
    if "boundary" in text or "length" in text or "limit" in text:
        return "boundary"
    if "default" in text:
        return "default_value"
    if "visible" in text or "enabled" in text or "present" in text:
        return "visibility"
    if "upload" in text:
        return "upload"
    if "valid" in text or "accept" in text:
        return "valid_input"
    return "unknown"


def _scenario_contract(mapping: Dict[str, Any], title: str, test_type: str) -> Tuple[str, List[Dict[str, Any]], List[str]] | None:
    field_type = _field_type_for_mapping(mapping)
    name = _scenario_name(mapping, field_type)
    behavior = _scenario_behavior(title)
    if behavior == "boundary" and field_type in {"text", "email", "textarea", "phone", "date", "file"}:
        subject = "file size" if field_type == "file" else "date" if field_type == "date" else "text length"
        return (
            f"Verify '{name}' enforces its {subject} boundary.",
            [
                {"step_number": 1, "description": f"Enter the minimum or maximum allowed {subject} value in '{name}'."},
                {"step_number": 2, "description": f"Verify the boundary value is accepted for '{name}'."},
                {"step_number": 3, "description": f"Enter a value beyond the boundary, such as maximum + 1, in '{name}'."},
                {"step_number": 4, "description": f"Verify the out-of-bound value is rejected or restricted for '{name}'."},
            ],
            [f"'{name}' accepts the allowed {subject} boundary.", f"Values beyond the {subject} boundary are rejected or restricted for '{name}'."],
        )
    if field_type == "radio":
        if behavior == "radio_single_selection":
            options = _radio_options(mapping)
            if len(options) < 2:
                return None
            first, second = options[:2]
            return (
                f"Verify only one option in the '{name}' radio group can be selected.",
                [
                    {"step_number": 1, "description": f"Select the '{first}' radio option."},
                    {"step_number": 2, "description": f"Verify '{first}' is selected."},
                    {"step_number": 3, "description": f"Select the '{second}' radio option."},
                    {"step_number": 4, "description": f"Verify '{first}' is deselected."},
                    {"step_number": 5, "description": f"Verify '{second}' is selected."},
                ],
                [f"Only one option remains selected in the '{name}' radio group."],
            )
        if behavior == "required_validation":
            return (
                f"Verify the mandatory '{name}' radio group requires one selection.",
                [{"step_number": 1, "description": f"Submit the form without selecting a '{name}' radio option."}, {"step_number": 2, "description": f"Verify validation feedback is displayed for '{name}'."}],
                [f"Validation feedback indicates that '{name}' requires one selection."],
            )
        if behavior in {"selection", "visibility", "unknown"}:
            return (
                f"Verify '{name}' radio button can be selected.",
                [{"step_number": 1, "description": f"Locate the '{name}' radio button."}, {"step_number": 2, "description": f"Select the '{name}' radio button."}, {"step_number": 3, "description": f"Verify '{name}' radio button is selected."}],
                [f"'{name}' radio button is visible and enabled.", f"'{name}' radio button can be selected.", f"'{name}' selected state is retained."],
            )
    if field_type == "checkbox" and behavior in {"selection", "checkbox_selection", "unknown"}:
        return (
            f"Verify '{name}' checkbox can be selected and deselected.",
            [{"step_number": 1, "description": f"Select the '{name}' checkbox."}, {"step_number": 2, "description": f"Verify '{name}' checkbox is selected."}, {"step_number": 3, "description": f"Deselect the '{name}' checkbox."}, {"step_number": 4, "description": f"Verify '{name}' checkbox is deselected."}],
            [f"'{name}' checkbox can be selected.", f"'{name}' checkbox can be deselected."],
        )
    return None


def _automation_intent(mapping: Dict[str, Any], title: str, test_type: str) -> Dict[str, Any]:
    field_type = _field_type_for_mapping(mapping)
    behavior = _scenario_behavior(title)
    actions = {
        "radio_single_selection": ["select_option_a", "verify_option_a_selected", "select_option_b", "verify_option_a_deselected", "verify_option_b_selected"],
        "selection": ["locate_control", "select_control", "verify_selected"],
        "checkbox_selection": ["select_checkbox", "verify_checked", "deselect_checkbox", "verify_unchecked"],
        "required_validation": ["submit_without_selection", "verify_validation_feedback"],
        "boundary": ["enter_boundary_value", "verify_boundary_accepted", "enter_out_of_boundary_value", "verify_boundary_rejected_or_restricted"],
        "invalid_input": ["enter_invalid_value", "verify_validation_feedback"],
        "default_value": ["read_default_option", "verify_default_option"],
        "upload": ["upload_file", "verify_upload"],
        "valid_input": ["enter_valid_value", "verify_value_accepted"],
        "visibility": ["locate_control", "verify_visible_and_enabled"],
    }
    assertions = {
        "radio_single_selection": ["only_one_option_selected"],
        "selection": ["control_selected"],
        "checkbox_selection": ["checkbox_checked", "checkbox_unchecked"],
        "required_validation": ["validation_feedback_displayed"],
        "boundary": ["boundary_value_accepted", "out_of_boundary_value_rejected_or_restricted"],
    }
    return {
        "field_type": field_type,
        "behavior": behavior,
        "test_type": test_type,
        "actions": actions.get(behavior, ["execute_control_action", "verify_expected_result"]),
        "assertions": assertions.get(behavior, ["expected_result_verified"]),
    }


def _scenario_quality_gate(item: Dict[str, Any]) -> Tuple[bool, str]:
    mapping = item.get("mapping") or {}
    title = str(item.get("title") or item.get("description") or "")
    text = " ".join([
        title,
        " ".join(str(step.get("description") or "") for step in item.get("steps") or [] if isinstance(step, dict)),
        " ".join(str(result) for result in item.get("expected_results") or []),
    ]).casefold()
    field_type = _field_type_for_mapping(mapping)
    if not _scenario_compatible(title, mapping):
        return False, "field type incompatible with title"
    behavior = _scenario_behavior(title)
    test_type = str(item.get("test_type") or "functional").casefold()
    if behavior == "boundary" and test_type != "boundary":
        return False, "boundary title has non-boundary test type"
    if test_type == "boundary" and behavior != "boundary":
        return False, "boundary test type has no boundary behavior"
    if test_type == "validation" and behavior not in {"required_validation", "invalid_input"}:
        return False, "validation test type has no validation behavior"
    if behavior == "boundary" and not all(marker in text for marker in ("boundary", "maximum + 1", "rejected", "restricted")):
        return False, "boundary scenario lacks boundary probes and enforcement assertion"
    required_markers = {
        "radio_single_selection": ("select", "deselected", "only one"),
        "selection": ("select", "selected"),
        "checkbox_selection": ("select", "deselect"),
        "required_validation": ("validation",),
    }
    if behavior in required_markers and not all(marker in text for marker in required_markers[behavior]):
        return False, f"title/steps/results mismatch for {behavior}"
    if behavior == "radio_single_selection" and len(_radio_options(mapping)) < 2:
        return False, "single-selection scenario lacks two radio options"
    if field_type in {"radio", "checkbox", "dropdown"} and any(marker in text for marker in ("enter data", "enter text", "typed value", "entered value")):
        return False, "control cannot accept text input"
    locator_fields = ("selector", "id", "name", "xpath", "href", "css_selector", "select_id", "form_id", "page")
    if field_type not in {"page_load", "form"} and not any(str(mapping.get(key) or "").strip() for key in locator_fields):
        return False, "scenario has no supplied locator metadata"
    if field_type == "radio" and behavior == "radio_single_selection" and len(_radio_options(mapping)) < 2:
        return False, "single-selection scenario has no two-option group metadata"
    if not item.get("steps") or not item.get("expected_results") or not isinstance(mapping, dict):
        return False, "scenario is not Selenium-ready"
    automation_intent = item.get("automation_intent")
    if not isinstance(automation_intent, dict) or automation_intent.get("behavior") != behavior:
        return False, "automation intent does not match scenario behavior"
    return True, "aligned and automatable"


def _build_fallback_scenarios(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Conservative, analysis-driven generator.

    Only create scenarios that are directly supported by elements present in the analysis JSON.
    Do NOT add generic or speculative scenarios. If the analysis does not contain evidence for a
    feature, do not generate scenarios for it.
    """
    forms = analysis.get("forms") or []
    inputs = analysis.get("inputs") or []
    buttons = analysis.get("buttons") or []
    links = analysis.get("links") or []
    selects = analysis.get("selects") or []
    title = (analysis.get("title") or "").strip()
    url = (analysis.get("url") or "")

    # Prefer a meaningful module name: page title > host
    module_name = ""
    if title:
        module_name = title
    elif url:
        try:
            module_name = url.split("/")[2]
        except Exception:
            module_name = url
    module_name = module_name or "Page"

    def build(idx: int, description: str, priority: str, mapping: Dict[str, Any]) -> Dict[str, Any]:
        field_name = str(mapping.get("field_name") or mapping.get("name") or mapping.get("label") or "").strip() or None
        inferred_type = _infer_test_type(description, mapping)
        canonical = _scenario_contract(mapping, description, inferred_type)
        if canonical:
            canonical_title, build_steps, build_expected = canonical
            description = canonical_title
        else:
            build_steps = _scenario_steps_for_mapping(mapping, description, inferred_type)
            build_expected = _scenario_expected_results_for_mapping(mapping, description, inferred_type)
        return {
            "id": f"s{idx}",
            "module": module_name,
            "test_scenario_id": f"TS_{idx:02d}",
            "title": description,
            "description": description,
            "priority": priority,
            "test_type": inferred_type,
            "preconditions": ["Application is available", "Page is loaded successfully"],
            "steps": build_steps,
            "expected_results": build_expected,
            "automation_intent": _automation_intent(mapping, description, inferred_type),
            "field_name": field_name,
            "mapping": {
                **mapping,
                **({"field_name": field_name} if field_name else {}),
            },
        }

    def narrow_label(item: Dict[str, Any], fallback: str) -> str:
        label = str(item.get("label") or "").strip()
        if label:
            return label
        placeholder = str(item.get("placeholder") or "").strip()
        if placeholder:
            return placeholder
        value = str(item.get("name") or item.get("id") or item.get("text") or "").strip()
        return value or fallback

    def is_required(item: Dict[str, Any]) -> bool:
        return bool(item.get("required") or item.get("attrs", {}).get("required"))

    scenarios: List[Dict[str, Any]] = []
    seen = set()
    next_id = 1

    def add_scenario(description: str, priority: str, mapping: Dict[str, Any]):
        nonlocal next_id
        key = description.strip().lower()
        if not key or key in seen:
            return
        field_type = _field_type_for_mapping(mapping)
        validation_result = _scenario_compatible(description, mapping)
        LOGGER.info(
            "Agent1 scenario compatibility: field_name=%s field_type=%s generated_scenario=%s validation_result=%s",
            mapping.get("field_name") or mapping.get("label") or mapping.get("name"),
            field_type,
            description,
            "PASS" if validation_result else "DISCARD",
        )
        if not validation_result:
            return
        seen.add(key)
        candidate = build(next_id, description, priority, mapping)
        quality_passed, quality_reason = _scenario_quality_gate(candidate)
        LOGGER.info(
            "Agent1 scenario quality gate: field_name=%s field_type=%s scenario_title=%s validation_result=%s reason=%s",
            candidate.get("field_name") or mapping.get("label") or mapping.get("name"),
            field_type,
            candidate.get("title"),
            "PASS" if quality_passed else "DISCARD",
            quality_reason,
        )
        if not quality_passed:
            return
        scenarios.append(candidate)
        next_id += 1

    if title or analysis.get("counts", {}).get("content_blocks", 0) > 0:
        desc = f"Verify the page loads and primary content (title: '{title}') is visible." if title else "Verify the page loads and primary content is visible."
        add_scenario(desc, "high", {"page": "load", "expected_title": title} if title else {"page": "load"})

    if len(forms) > 0:
        for i, form in enumerate(forms, start=1):
            form_id = form.get("id") or form.get("name") or f"form{i}"
            field_count = len(form.get("inputs", [])) if isinstance(form.get("inputs"), list) else 0
            add_scenario(
                f"Verify form '{form_id}' is present and contains {field_count} expected fields.",
                "high",
                {"form_id": form_id, "field_count": field_count},
            )

            if field_count > 0:
                add_scenario(
                    f"Verify form '{form_id}' can be submitted successfully with valid data.",
                    "high",
                    {"form_id": form_id, "mode": "submit-valid"},
                )

                if any(is_required(field) for field in form.get("inputs", [])) or any(field.get("type") in ("email", "tel", "url", "number") for field in form.get("inputs", [])):
                    add_scenario(
                        f"Verify form '{form_id}' shows validation feedback when required or invalid fields are submitted.",
                        "high",
                        {"form_id": form_id, "mode": "submit-invalid"},
                    )

    for i, inp in enumerate(inputs, start=1):
        label = narrow_label(inp, f"input{i}")
        itype = str(inp.get("type") or "text").strip().lower()
        mapping = {
            "name": inp.get("name"),
            "id": inp.get("id"),
            "type": itype,
            "field_type": itype,
            "element_type": inp.get("element_type") or itype,
            "label": label,
            "group_name": inp.get("group_name") or inp.get("group_label") or inp.get("radio_group_name"),
            "options": inp.get("options") or inp.get("choices") or inp.get("radio_options") or [],
            "selector": inp.get("selector"),
        }
        for test_type, description in _compatible_field_scenarios(mapping):
            if test_type == "validation" and not is_required(inp):
                continue
            add_scenario(description, "high" if test_type in {"negative", "validation", "boundary"} else "medium", mapping)

    for i, sel in enumerate(selects, start=1):
        label = narrow_label(sel, f"select{i}")
        options = sel.get("options") or []
        mapping = {
            "select_id": sel.get("id") or sel.get("name"),
            "selector": sel.get("selector"),
            "id": sel.get("id"),
            "name": sel.get("name"),
            "type": "dropdown",
            "field_type": "dropdown",
            "label": label,
            "option_count": len(options),
        }
        add_scenario(
            f"Verify dropdown '{label}' allows selecting from {len(options)} available options.",
            "medium",
            mapping,
        )
        if sel.get("multiple"):
            add_scenario(
                f"Verify multi-select dropdown '{label}' allows selecting multiple options.",
                "medium",
                mapping,
            )

    for i, btn in enumerate(buttons, start=1):
        text = narrow_label(btn, f"button{i}")
        mapping = {
            "id": btn.get("id"),
            "text": btn.get("text"),
            "selector": btn.get("selector"),
        }
        add_scenario(
            f"Verify button/CTA '{text}' is visible and triggers the expected action.",
            "high",
            mapping,
        )

    for i, lk in enumerate(links, start=1):
        href = lk.get("href")
        if not href:
            continue
        text = narrow_label(lk, f"link{i}")
        add_scenario(
            f"Verify link '{text}' navigates to '{href}'.",
            "medium",
            {"href": href, "selector": lk.get("selector")},
        )

    if len(selects) == 0 and len(inputs) == 0 and len(buttons) == 0 and len(links) == 0 and len(forms) == 0:
        add_scenario(
            "Verify the page loads and visible content renders correctly.",
            "high",
            {"page": "load"},
        )

    has_password = any(isinstance(inp, dict) and inp.get("type") == "password" for inp in inputs)
    if has_password or ("login" in (url or "").lower()):
        add_scenario(
            "Verify authentication flow handles invalid credentials with an appropriate error message.",
            "high",
            {"page": "auth"},
        )

    return scenarios


import re

def _replace_placeholders_in_results(results, mapping: Dict[str, Any], title: str = None):
    if not results:
        return results

    # Try central extraction helper first
    try:
        name = extract_element_name(mapping, title)
    except Exception:
        name = None

    # Fallback heuristic if helper couldn't determine a name
    if not name:
        def extract_name():
            if isinstance(mapping, dict):
                for key in ("label", "field_name", "text", "name", "id"):
                    val = mapping.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
            if isinstance(title, str) and title:
                m = re.search(r"['\"]([^'\"]+)['\"]", title)
                if m:
                    return m.group(1).strip()
            return None
        name = extract_name()

    LOGGER.info("_replace_placeholders_in_results - derived_name=%s title=%s mapping=%s results_count=%s", name, title, mapping, len(results) if results else 0)

    out = []
    for r in results:
        if not isinstance(r, str):
            out.append(r)
            continue
        if name:
            rr = r.replace("Element", name).replace("Target Field", name).replace("Target Link", name).replace("Input Field", name)
            out.append(rr)
        else:
            out.append(r)
    return out


def _normalize_scenarios(parsed: Any, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(parsed, dict) and isinstance(parsed.get("scenarios"), list):
        scenarios = parsed["scenarios"]
    elif isinstance(parsed, list):
        scenarios = parsed
    else:
        scenarios = []

    normalized = []
    seen_ids = set()
    seen_descriptions = set()

    def normalize_item(item: Dict[str, Any], index: int) -> Dict[str, Any]:
        description = str(item.get("description") or item.get("title") or "").strip()
        module = str(item.get("module") or item.get("Module") or "General").strip() or "General"
        test_scenario_id = str(item.get("test_scenario_id") or item.get("TestScenarioId") or item.get("id") or f"TS_{index:02d}").strip() or f"TS_{index:02d}"
        mapping = item.get("mapping") or {}
        if isinstance(mapping, dict) and "field_name" not in mapping and item.get("field_name"):
            mapping = {**mapping, "field_name": item.get("field_name")}
        preconditions = item.get("preconditions") or ["Application is available", "Page is loaded successfully"]
        steps = item.get("steps") or item.get("test_steps") or _scenario_steps_for_mapping(mapping, description)
        inferred_test_type = _infer_test_type(description, mapping)
        expected_results = item.get("expected_results") or item.get("expected_result") or _scenario_expected_results_for_mapping(mapping, description, inferred_test_type)
        # Replace generic placeholders when possible
        if isinstance(expected_results, list):
            expected_results = _replace_placeholders_in_results(expected_results, mapping, description)
        elif isinstance(expected_results, str):
            expected_results = _replace_placeholders_in_results([expected_results], mapping, description)
        return {
            "id": item.get("id") or f"s{index}",
            "module": module,
            "test_scenario_id": test_scenario_id,
            "title": description,
            "description": description or f"Scenario {test_scenario_id}",
            "priority": item.get("priority") or "medium",
            "test_type": inferred_test_type,
            "preconditions": preconditions if isinstance(preconditions, list) else ["Application is available", "Page is loaded successfully"],
            "steps": steps if isinstance(steps, list) else _scenario_steps_for_mapping(mapping, description),
            "expected_results": expected_results if isinstance(expected_results, list) else [str(expected_results)],
            "automation_intent": _automation_intent(mapping, description, inferred_test_type),
            "field_name": item.get("field_name") or (mapping.get("field_name") if isinstance(mapping, dict) else None),
            "mapping": mapping,
        }

    for idx, item in enumerate(scenarios, start=1):
        if not isinstance(item, dict):
            continue
        description = str(item.get("description") or item.get("title") or "").strip()
        if not description:
            continue
        normalized_item = normalize_item(item, idx)
        canonical = _scenario_contract(
            normalized_item["mapping"],
            normalized_item["title"],
            normalized_item["test_type"],
        )
        if canonical:
            canonical_title, canonical_steps, canonical_results = canonical
            normalized_item["title"] = canonical_title
            normalized_item["description"] = canonical_title
            normalized_item["steps"] = canonical_steps
            normalized_item["expected_results"] = canonical_results
            normalized_item["automation_intent"] = _automation_intent(
                normalized_item["mapping"], canonical_title, normalized_item["test_type"]
            )
            LOGGER.info(
                "Agent1 scenario canonicalized: field_name=%s field_type=%s scenario_title=%s validation_result=CANONICAL",
                normalized_item.get("field_name") or normalized_item["mapping"].get("label"),
                _field_type_for_mapping(normalized_item["mapping"]),
                canonical_title,
            )
        lower_desc = normalized_item["description"].lower()
        compatibility = _scenario_compatible(normalized_item["description"], normalized_item["mapping"])
        LOGGER.info(
            "Agent1 scenario compatibility: field_name=%s field_type=%s generated_scenario=%s validation_result=%s",
            normalized_item.get("field_name") or normalized_item["mapping"].get("label"),
            _field_type_for_mapping(normalized_item["mapping"]),
            normalized_item["description"],
            "PASS" if compatibility else "DISCARD",
        )
        if not compatibility:
            replacement = _compatible_field_scenarios(normalized_item["mapping"])
            if replacement:
                replacement_type, replacement_description = replacement[0]
                normalized_item["description"] = replacement_description
                normalized_item["title"] = replacement_description
                normalized_item["test_type"] = replacement_type
                normalized_item["steps"] = _scenario_steps_for_mapping(normalized_item["mapping"], replacement_description, replacement_type)
                normalized_item["expected_results"] = _scenario_expected_results_for_mapping(normalized_item["mapping"], replacement_description, replacement_type)
                normalized_item["automation_intent"] = _automation_intent(
                    normalized_item["mapping"], replacement_description, replacement_type
                )
                LOGGER.info(
                    "Agent1 incompatible scenario regenerated: field_name=%s field_type=%s generated_scenario=%s validation_result=REGENERATED",
                    normalized_item.get("field_name") or normalized_item["mapping"].get("label"),
                    _field_type_for_mapping(normalized_item["mapping"]),
                    replacement_description,
                )
            else:
                continue
        quality_passed, quality_reason = _scenario_quality_gate(normalized_item)
        LOGGER.info(
            "Agent1 scenario quality gate: field_name=%s field_type=%s scenario_title=%s validation_result=%s reason=%s",
            normalized_item.get("field_name") or normalized_item["mapping"].get("label"),
            _field_type_for_mapping(normalized_item["mapping"]),
            normalized_item["title"],
            "PASS" if quality_passed else "DISCARD",
            quality_reason,
        )
        if not quality_passed:
            continue
        if lower_desc in seen_descriptions:
            continue
        seen_descriptions.add(lower_desc)
        normalized.append(normalized_item)

    # If the model produced no usable scenarios, fall back to conservative, analysis-driven generation.
    if not normalized:
        normalized = _build_fallback_scenarios(analysis)

    return normalized

    return normalized


async def generate_scenarios(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Generate scenarios from analysis JSON.

    By default, this uses a deterministic, analysis-driven generator to avoid
    hallucinated scenarios and keep results grounded in observed page elements.
    If USE_AI_SCENARIOS is enabled, it may attempt an optional Groq call as a
    secondary step, but it will fall back to the deterministic generator for
    reliable results.

    This function now adds an intent classification layer into the analysis
    context before invoking the LLM so the model receives explicit category
    guidance and can produce more specific, non-generic scenario descriptions.
    """
    if USE_AI_SCENARIOS:
        groq = GroqService()
        try:
            # Compute an intent classification map from the analysis and inject it
            from app.services.intent_classifier import classify_analysis

            try:
                intent_map = classify_analysis(analysis)
            except Exception:
                intent_map = {}

            analysis_with_intent = {**(analysis or {}), "intent_classification": intent_map}

            parsed = await groq.generate_scenarios(analysis_with_intent)
            normalized = _normalize_scenarios(parsed, analysis)
            if normalized:
                return {"scenarios": normalized}
        except GroqServiceError:
            pass

    return {"scenarios": _build_fallback_scenarios(analysis)}