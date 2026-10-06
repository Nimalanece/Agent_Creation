"""Element Type Detection and Element-Specific Test Generation Rules.

This module provides:
1. Scenario intent detection (navigation, form submission, validation, etc.)
2. Element type detection from multiple data sources (selector, mapping, description)
3. Element-specific step generation (different actions for links vs buttons vs inputs)
4. Element-specific expected results generation (scenario-specific assertions)
5. Element-specific automation hints (Selenium action vocabulary)

PRIORITY ORDER:
1. Scenario intent is evaluated FIRST (navigation, form submission, etc.)
2. Element type is evaluated SECOND based on intent and mapping
3. Template selection uses both intent and element type

This prevents element keywords in labels (e.g., "Check Box" in a link label)
from incorrectly overriding scenario intent.
"""

from typing import Any, Dict, List, Literal, Optional
from enum import Enum


class ElementType(str, Enum):
    """Supported element types for test generation."""
    
    TEXT_INPUT = "text_input"
    EMAIL_INPUT = "email_input"
    PASSWORD_INPUT = "password_input"
    NUMBER_INPUT = "number_input"
    PHONE_INPUT = "phone_input"
    DATE_INPUT = "date_input"
    SEARCH_INPUT = "search_input"
    URL_INPUT = "url_input"
    TEXTAREA = "textarea"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    DROPDOWN = "dropdown"
    SELECT = "select"
    BUTTON = "button"
    LINK = "link"
    FILE_UPLOAD = "file_upload"
    FORM = "form"
    PAGE_LOAD = "page_load"
    UNKNOWN = "unknown"


class ScenarioIntent(str, Enum):
    """Detected scenario intent/action type."""
    
    NAVIGATION = "navigation"  # Link click, redirect, navigation
    FORM_SUBMISSION = "form_submission"  # Form submit
    BUTTON_CLICK = "button_click"  # Button action
    CHECKBOX_SELECTION = "checkbox_selection"  # Checkbox interaction
    RADIO_SELECTION = "radio_selection"  # Radio button selection
    DROPDOWN_SELECTION = "dropdown_selection"  # Dropdown/select interaction
    FILE_UPLOAD_ACTION = "file_upload"  # File upload
    TEXT_INPUT_ACTION = "text_input"  # Text input interaction
    PAGE_LOAD = "page_load"  # Page loading
    VALIDATION = "validation"  # Validation check
    UNKNOWN = "unknown"  # Cannot determine intent


def _infer_scenario_intent(
    description: str = "",
    title: str = "",
    mapping: Optional[Dict[str, Any]] = None,
) -> ScenarioIntent:
    """Infer scenario intent FIRST, before element type detection.
    
    Intent keywords take precedence over element keywords to prevent
    link labels like "Check Box" from being misclassified as checkboxes.
    
    Priority Order:
    1. Navigation (most specific action) - checked in title and description
    2. Button Click (explicit "click [word]* button" pattern in title)
    3. File Upload (very specific pattern)
    4. Checkbox/Radio/Dropdown (explicit selection actions)
    5. Form Submission (more general, checked after button click)
    6. Text Input
    7. Page Load
    8. Validation
    
    Returns:
        ScenarioIntent enum value based on action keywords in description/title.
    """
    mapping = mapping or {}
    desc_lower = str(description or "").lower()
    title_lower = str(title or "").lower()
    combined = f"{desc_lower} {title_lower}"
    
    # NAVIGATION intent (takes precedence over element keywords)
    navigation_keywords = [
        "navigate",
        "navigates to",
        "navigates",
        "redirect",
        "redirects to",
        "redirects",
        "open page",
        "opens page",
        "go to page",
        "goes to page",
        "click link",
        "visit page",
        "user is redirected",
        "url change",
        "url contains",
    ]
    if any(keyword in combined for keyword in navigation_keywords):
        return ScenarioIntent.NAVIGATION
    
    # BUTTON CLICK intent - check title specifically for "click ... button" pattern
    # This must be checked BEFORE form submission because "submit button" could match both
    # We prioritize explicit click-button patterns in the title
    button_title_keywords = [
        "click button",
        "click the button",
        "click submit",
        "click save",
        "click send",
        "click delete",
        "click reset",
        "click apply",
        "click ok",
        "button click",
        "button is clickable",
    ]
    if any(keyword in title_lower for keyword in button_title_keywords):
        return ScenarioIntent.BUTTON_CLICK
    
    # FILE UPLOAD intent (very specific)
    upload_keywords = [
        "upload file",
        "file upload",
        "upload a file",
    ]
    if any(keyword in combined for keyword in upload_keywords):
        return ScenarioIntent.FILE_UPLOAD_ACTION
    
    # CHECKBOX SELECTION intent (explicit action on checkbox)
    checkbox_keywords = [
        "check checkbox",
        "select checkbox",
        "checkbox can be selected",
        "checkbox is selected",
        "toggle checkbox",
        "uncheck checkbox",
    ]
    if any(keyword in combined for keyword in checkbox_keywords):
        return ScenarioIntent.CHECKBOX_SELECTION
    
    # RADIO SELECTION intent
    radio_keywords = [
        "select radio",
        "radio button can be selected",
        "radio option",
    ]
    if any(keyword in combined for keyword in radio_keywords):
        return ScenarioIntent.RADIO_SELECTION
    
    # DROPDOWN SELECTION intent
    dropdown_keywords = [
        "select dropdown",
        "dropdown option",
        "choose option",
    ]
    if any(keyword in combined for keyword in dropdown_keywords):
        return ScenarioIntent.DROPDOWN_SELECTION
    
    # FORM SUBMISSION intent (after button click pattern check)
    form_keywords = [
        "submit form",
        "form submit",
        "form submission",
        "submits form",
    ]
    if any(keyword in combined for keyword in form_keywords):
        return ScenarioIntent.FORM_SUBMISSION
    
    # TEXT INPUT intent (entering text into a field)
    input_keywords = [
        "enter text",
        "enters text",
        "input text",
        "type text",
        "accepts input",
        "accepts text",
    ]
    if any(keyword in combined for keyword in input_keywords):
        return ScenarioIntent.TEXT_INPUT_ACTION
    
    # PAGE LOAD intent
    pageload_keywords = [
        "page load",
        "page loads",
        "page is loaded",
        "browser title",
        "page title",
    ]
    if any(keyword in combined for keyword in pageload_keywords):
        return ScenarioIntent.PAGE_LOAD
    
    # VALIDATION intent
    validation_keywords = [
        "validation",
        "validate",
        "error message",
        "error is displayed",
        "field is required",
    ]
    if any(keyword in combined for keyword in validation_keywords):
        return ScenarioIntent.VALIDATION
    
    return ScenarioIntent.UNKNOWN


def detect_element_type(
    mapping: Optional[Dict[str, Any]] = None,
    description: str = "",
    title: str = "",
    selector: str = "",
) -> ElementType:
    """Detect element type with SCENARIO INTENT taking precedence.
    
    Detection Order (Priority):
    1. SCENARIO INTENT FIRST - Navigation, form submission, etc. override element keywords
    2. Explicit element_type in mapping
    3. HTML5 input type attributes
    4. HTML tag names
    5. Field type from Agent 1 schema
    6. Pattern matching in description/title (but respects intent)
    7. Selector analysis
    
    This prevents element keywords in labels (e.g., "Check Box" text on a link)
    from overriding the actual element type.
    
    Args:
        mapping: Mapping metadata with type, tag, selector, and other hints
        description: Test description text
        title: Test title text
        selector: CSS selector or XPath
        
    Returns:
        ElementType enum value
    """
    mapping = mapping or {}
    desc_lower = str(description or "").lower()
    title_lower = str(title or "").lower()
    selector_lower = str(selector or "").lower()
    
    # STEP 1: INFER SCENARIO INTENT FIRST
    # This takes precedence and prevents element keywords in labels from causing misclassification
    intent = _infer_scenario_intent(description, title, mapping)
    
    # MAP INTENT TO ELEMENT TYPE
    if intent == ScenarioIntent.NAVIGATION:
        return ElementType.LINK
    elif intent == ScenarioIntent.FORM_SUBMISSION:
        return ElementType.FORM
    elif intent == ScenarioIntent.BUTTON_CLICK:
        return ElementType.BUTTON
    elif intent == ScenarioIntent.CHECKBOX_SELECTION:
        return ElementType.CHECKBOX
    elif intent == ScenarioIntent.RADIO_SELECTION:
        return ElementType.RADIO
    elif intent == ScenarioIntent.DROPDOWN_SELECTION:
        return ElementType.DROPDOWN
    elif intent == ScenarioIntent.FILE_UPLOAD_ACTION:
        return ElementType.FILE_UPLOAD
    elif intent == ScenarioIntent.TEXT_INPUT_ACTION:
        return ElementType.TEXT_INPUT
    elif intent == ScenarioIntent.PAGE_LOAD:
        return ElementType.PAGE_LOAD
    # For VALIDATION and UNKNOWN, fall through to element type detection
    
    # STEP 2: EXPLICIT ELEMENT TYPE IN MAPPING
    # Extract mapping hints
    input_type = str(mapping.get("type") or mapping.get("input_type") or "").lower()
    tag_name = str(mapping.get("tag") or mapping.get("tag_name") or "").lower()
    field_type = str(mapping.get("field_type") or "").lower()
    element_type = str(mapping.get("element_type") or "").lower()
    kind = str(mapping.get("kind") or "").lower()
    
    # Check for explicit element type in mapping
    if element_type:
        if "text" in element_type:
            return ElementType.TEXT_INPUT
        if "email" in element_type:
            return ElementType.EMAIL_INPUT
        if "password" in element_type:
            return ElementType.PASSWORD_INPUT
        if "phone" in element_type:
            return ElementType.PHONE_INPUT
        if "number" in element_type:
            return ElementType.NUMBER_INPUT
        if "date" in element_type:
            return ElementType.DATE_INPUT
        if "checkbox" in element_type:
            return ElementType.CHECKBOX
        if "radio" in element_type:
            return ElementType.RADIO
        if "dropdown" in element_type or "select" in element_type:
            return ElementType.DROPDOWN
        if "button" in element_type:
            return ElementType.BUTTON
        if "link" in element_type:
            return ElementType.LINK
        if "file" in element_type or "upload" in element_type:
            return ElementType.FILE_UPLOAD
        if "form" in element_type:
            return ElementType.FORM
    
    # STEP 3: CHECK HTML5 INPUT TYPES
    if input_type:
        if input_type in ("email", "email-address"):
            return ElementType.EMAIL_INPUT
        if input_type in ("password", "passwd"):
            return ElementType.PASSWORD_INPUT
        if input_type in ("tel", "phone", "phone_number"):
            return ElementType.PHONE_INPUT
        if input_type in ("number", "numeric"):
            return ElementType.NUMBER_INPUT
        if input_type in ("date", "datetime", "datetime-local"):
            return ElementType.DATE_INPUT
        if input_type in ("search", "searchbox"):
            return ElementType.SEARCH_INPUT
        if input_type in ("url", "website"):
            return ElementType.URL_INPUT
        if input_type in ("file", "upload"):
            return ElementType.FILE_UPLOAD
        if input_type == "text":
            return ElementType.TEXT_INPUT
        if input_type == "checkbox":
            return ElementType.CHECKBOX
        if input_type == "radio":
            return ElementType.RADIO
    
    # STEP 4: CHECK TAG NAMES
    if tag_name:
        if tag_name == "textarea":
            return ElementType.TEXTAREA
        if tag_name == "button":
            return ElementType.BUTTON
        if tag_name == "a":
            return ElementType.LINK
        if tag_name in ("select", "dropdown"):
            return ElementType.DROPDOWN
        if tag_name == "input":
            # Default input to text, refined by other attributes
            return ElementType.TEXT_INPUT
        if tag_name == "form":
            return ElementType.FORM
    
    # STEP 5: CHECK FIELD_TYPE FROM AGENT 1 SCHEMA
    if field_type:
        field_mapping = {
            "email": ElementType.EMAIL_INPUT,
            "username": ElementType.TEXT_INPUT,
            "password": ElementType.PASSWORD_INPUT,
            "phone_number": ElementType.PHONE_INPUT,
            "phone": ElementType.PHONE_INPUT,
            "text": ElementType.TEXT_INPUT,
            "number": ElementType.NUMBER_INPUT,
            "date": ElementType.DATE_INPUT,
            "search": ElementType.SEARCH_INPUT,
            "dropdown": ElementType.DROPDOWN,
            "checkbox": ElementType.CHECKBOX,
            "url": ElementType.URL_INPUT,
        }
        if field_type in field_mapping:
            return field_mapping[field_type]
    
    # STEP 6: PATTERN MATCHING IN COMBINED TEXT
    # Only use these as fallback when intent is UNKNOWN or VALIDATION
    # This prevents keywords in labels from overriding the intent
    combined_text = f"{desc_lower} {title_lower} {selector_lower} {input_type} {tag_name} {field_type} {kind}"
    
    # NOTE: Removed "checkbox" and other element keywords from here
    # because they should only match if the intent detection matched them first.
    # This prevents "Check Box" in a link label from being misclassified.
    
    # Only match very specific patterns that indicate actual element interaction
    if "select" in combined_text and "option" in combined_text:
        return ElementType.DROPDOWN
    if "radio button" in combined_text:  # Explicit "radio button" pattern
        return ElementType.RADIO
    if "check.*box" in combined_text or "uncheck" in combined_text:  # Explicit action patterns
        return ElementType.CHECKBOX
    if "email" in combined_text and ("field" in combined_text or "input" in combined_text):
        return ElementType.EMAIL_INPUT
    if "password" in combined_text and ("field" in combined_text or "input" in combined_text):
        return ElementType.PASSWORD_INPUT
    if "phone" in combined_text or "telephone" in combined_text:
        return ElementType.PHONE_INPUT
    if "date" in combined_text and ("field" in combined_text or "input" in combined_text):
        return ElementType.DATE_INPUT
    if "search" in combined_text and ("field" in combined_text or "input" in combined_text):
        return ElementType.SEARCH_INPUT
    if "page load" in combined_text or "page loads" in combined_text:
        return ElementType.PAGE_LOAD
    
    # STEP 7: SELECTOR-BASED DETECTION
    if "input[type=" in selector_lower:
        if 'type="text"' in selector_lower or 'type="text' in selector_lower:
            return ElementType.TEXT_INPUT
        if 'type="email"' in selector_lower:
            return ElementType.EMAIL_INPUT
        if 'type="password"' in selector_lower:
            return ElementType.PASSWORD_INPUT
        if 'type="checkbox"' in selector_lower:
            return ElementType.CHECKBOX
        if 'type="radio"' in selector_lower:
            return ElementType.RADIO
        if 'type="file"' in selector_lower:
            return ElementType.FILE_UPLOAD
    
    if "input" in selector_lower and "[type=" not in selector_lower:
        return ElementType.TEXT_INPUT
    if "a" in selector_lower or "[href" in selector_lower:
        return ElementType.LINK
    if "button" in selector_lower:
        return ElementType.BUTTON
    if "select" in selector_lower or "dropdown" in selector_lower:
        return ElementType.DROPDOWN
    if "form" in selector_lower:
        return ElementType.FORM
    
    return ElementType.UNKNOWN


def _extract_locator_type_and_value(
    selector: Optional[str] = None,
    mapping: Optional[Dict[str, Any]] = None,
) -> tuple[str, str]:
    """Extract the best locator type and value from selector and mapping.
    
    Returns:
        Tuple of (locator_type, locator_value)
        locator_type: "id", "css_selector", "xpath", "class", "name", etc.
        locator_value: The actual selector value
    
    Priority:
    1. ID selector (#id or id attribute)
    2. CSS selector from selector field
    3. XPath
    4. Class selector
    5. Name attribute
    6. Tag name with attribute (for links, etc.)
    """
    mapping = mapping or {}
    selector_str = str(selector or "").strip()
    
    # Try to extract ID from mapping
    element_id = str(mapping.get("id") or "").strip()
    if element_id:
        return ("id", element_id)
    
    # Try to extract ID from CSS selector pattern
    if selector_str.startswith("#"):
        return ("id", selector_str[1:])
    if "id=" in selector_str.lower() or "[id=" in selector_str.lower():
        # Extract id value from selector like "input[id='firstName']" or "[id='firstName']"
        import re
        match = re.search(r"\[?id[=\'\"]([^\'\"\]]+)[\'\"]?\]?", selector_str, re.IGNORECASE)
        if match:
            return ("id", match.group(1))
    
    # Return CSS selector as default
    if selector_str:
        return ("css_selector", selector_str)
    
    # Try to extract from mapping field name
    # A business label is not a DOM locator. Leave the step unavailable when
    # the analysis did not provide an actual id, name, selector, or XPath.
    return ("", "")


def _format_element_name(mapping: Optional[Dict[str, Any]] = None) -> str:
    """Extract friendly element name from mapping metadata.
    
    Tries in order:
    1. label field
    2. text field  
    3. field_name / name field
    4. placeholder
    5. aria-label
    6. Default to "Element"
    """
    mapping = mapping or {}
    
    candidates = [
        mapping.get("label"),
        mapping.get("text"),
        mapping.get("field_name") or mapping.get("name"),
        mapping.get("placeholder"),
        mapping.get("aria_label"),
    ]
    
    for candidate in candidates:
        candidate_str = str(candidate or "").strip()
        if candidate_str and candidate_str.lower() != "none":
            # Clean up the name
            return candidate_str[:50]  # Limit length
    
    return "Element"



def get_element_specific_steps(
    element_type: ElementType,
    mapping: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> List[Dict[str, Any]]:
    """Generate element-specific test steps with locator metadata.
    
    Every step includes automation-ready metadata:
    - element_name: Friendly name of the element
    - selector: CSS selector or locator
    - locator_type: "id", "css_selector", "xpath", etc.
    - locator_value: The actual locator value (without prefix)
    
    Args:
        element_type: The detected or specified element type
        mapping: Mapping metadata with selectors and details
        description: Test description for additional context
        
    Returns:
        List of test step dictionaries with full locator metadata
    """
    mapping = mapping or {}
    selector = str(mapping.get("selector") or mapping.get("id") or "").strip()
    field_name = str(mapping.get("field_name") or mapping.get("name") or mapping.get("label") or "field").strip()
    
    # Extract locator information
    locator_type, locator_value = _extract_locator_type_and_value(selector, mapping)
    element_name = _format_element_name(mapping)
    
    # TEXT INPUT FAMILY
    if element_type in (ElementType.TEXT_INPUT, ElementType.EMAIL_INPUT, ElementType.PASSWORD_INPUT,
                       ElementType.PHONE_INPUT, ElementType.NUMBER_INPUT, ElementType.DATE_INPUT,
                       ElementType.SEARCH_INPUT, ElementType.URL_INPUT, ElementType.TEXTAREA):
        return [
            {
                "step_number": 1,
                "action": "locate_element",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
            {
                "step_number": 2,
                "action": "enter_text",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
                "value": f"Sample {field_name}",
            },
        ]
    
    # CHECKBOX
    elif element_type == ElementType.CHECKBOX:
        return [
            {
                "step_number": 1,
                "action": "locate_element",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
            {
                "step_number": 2,
                "action": "select_checkbox",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
        ]
    
    # RADIO BUTTON
    elif element_type == ElementType.RADIO:
        return [
            {
                "step_number": 1,
                "action": "locate_element",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
            {
                "step_number": 2,
                "action": "select_radio",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
        ]
    
    # DROPDOWN / SELECT
    elif element_type in (ElementType.DROPDOWN, ElementType.SELECT):
        return [
            {
                "step_number": 1,
                "action": "locate_element",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
            {
                "step_number": 2,
                "action": "select_dropdown_option",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
                "value": "first_option",
            },
        ]
    
    # FILE UPLOAD
    elif element_type == ElementType.FILE_UPLOAD:
        return [
            {
                "step_number": 1,
                "action": "locate_element",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
            {
                "step_number": 2,
                "action": "upload_file",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
                "value": "test_file.txt",
            },
        ]
    
    # BUTTON
    elif element_type == ElementType.BUTTON:
        return [
            {
                "step_number": 1,
                "action": "locate_element",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
            {
                "step_number": 2,
                "action": "click_element",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
        ]
    
    # LINK
    elif element_type == ElementType.LINK:
        href = str(mapping.get("href") or mapping.get("url") or "destination").strip()
        return [
            {
                "step_number": 1,
                "action": "locate_element",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
            {
                "step_number": 2,
                "action": "click_element",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
                "expected_url": href,
            },
        ]
    
    # FORM
    elif element_type == ElementType.FORM:
        return [
            {
                "step_number": 1,
                "action": "locate_element",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
            {
                "step_number": 2,
                "action": "populate_form",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
                "value": "valid_test_data",
            },
            {
                "step_number": 3,
                "action": "submit_form",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
        ]
    
    # PAGE LOAD
    elif element_type == ElementType.PAGE_LOAD:
        return [
            {
                "step_number": 1,
                "action": "open_url",
                "target": "application_url",
                "element_name": "Application",
                "selector": "application_url",
                "locator_type": "url",
                "locator_value": "application_url",
            },
            {
                "step_number": 2,
                "action": "verify_page_title",
                "target": "page_title",
                "element_name": "Page Title",
                "selector": "page_title",
                "locator_type": "title",
                "locator_value": "expected_title",
                "expected_value": "expected_title",
            },
            {
                "step_number": 3,
                "action": "verify_element_visible",
                "target": "primary_content",
                "element_name": "Primary Content",
                "selector": "primary_content",
                "locator_type": "css_selector",
                "locator_value": "primary_content",
            },
        ]
    
    # UNKNOWN / DEFAULT
    else:
        return [
            {
                "step_number": 1,
                "action": "locate_element",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
            {
                "step_number": 2,
                "action": "verify_element_visible",
                "target": selector,
                "element_name": element_name,
                "selector": selector,
                "locator_type": locator_type,
                "locator_value": locator_value,
            },
        ]


def get_element_specific_expected_results(
    element_type: ElementType,
    test_type: str = "functional",
    mapping: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> List[str]:
    """Generate element-specific expected results with explicit values.
    
    Includes actual element names and expected values instead of generic assertions.
    
    Args:
        element_type: The detected or specified element type
        test_type: The test type (functional, positive, negative, validation, boundary, navigation, security)
        mapping: Mapping metadata with element info
        description: Test description for context
        
    Returns:
        List of expected result assertion strings with explicit values
    """
    mapping = mapping or {}
    field_name = _format_element_name(mapping)
    href = str(mapping.get("href") or mapping.get("url") or "").strip()
    test_type = str(test_type or "functional").strip().lower()
    
    # TEXT INPUT FAMILY
    if element_type in (ElementType.TEXT_INPUT, ElementType.EMAIL_INPUT, ElementType.PASSWORD_INPUT,
                       ElementType.PHONE_INPUT, ElementType.NUMBER_INPUT, ElementType.DATE_INPUT,
                       ElementType.SEARCH_INPUT, ElementType.URL_INPUT, ElementType.TEXTAREA):
        if test_type == "negative":
            return [
                f"'{field_name}' validation fails for invalid input",
                "Validation error message is displayed",
                "Form submission is prevented",
            ]
        elif test_type == "validation":
            return [
                f"'{field_name}' validation rule is enforced",
                "Validation message is displayed with guidance",
                "User receives clear feedback about requirements",
            ]
        elif test_type == "boundary":
            return [
                f"'{field_name}' accepts input within acceptable range",
                "Boundary condition is handled correctly",
                "System behavior is consistent at limits",
            ]
        elif test_type == "security":
            return [
                f"'{field_name}' input is sanitized",
                "XSS and injection attempts are prevented",
                "Application remains secure",
            ]
        else:  # functional, positive, default
            return [
                f"'{field_name}' is visible and accessible",
                f"'{field_name}' accepts user input",
                f"Entered value in '{field_name}' is displayed correctly",
            ]
    
    # CHECKBOX
    elif element_type == ElementType.CHECKBOX:
        if test_type == "negative":
            return [
                f"'{field_name}' checkbox selection is prevented",
                "Error message is displayed",
                f"'{field_name}' checkbox state remains unchanged",
            ]
        elif test_type == "boundary":
            return [
                f"'{field_name}' checkbox state toggles correctly",
                "Multiple selection constraints are enforced",
                "System handles edge cases properly",
            ]
        else:  # functional, positive, validation
            return [
                f"'{field_name}' checkbox is visible and accessible",
                f"'{field_name}' checkbox can be selected",
                f"'{field_name}' checkbox state changes correctly",
            ]
    
    # RADIO BUTTON
    elif element_type == ElementType.RADIO:
        if test_type == "negative":
            return [
                f"'{field_name}' radio selection is prevented",
                "Error message is displayed",
                f"'{field_name}' radio state remains unchanged",
            ]
        elif test_type == "validation":
            return [
                f"At least one '{field_name}' option must be selected",
                "Validation error is displayed when required",
                "User feedback indicates selection requirement",
            ]
        else:  # functional, positive
            return [
                f"'{field_name}' radio option is visible and accessible",
                f"'{field_name}' radio option can be selected",
                f"'{field_name}' selected state is retained",
            ]
    
    # DROPDOWN / SELECT
    elif element_type in (ElementType.DROPDOWN, ElementType.SELECT):
        if test_type == "negative":
            return [
                f"Invalid option in '{field_name}' is rejected",
                "Error message is displayed",
                f"Previous selection in '{field_name}' is retained",
            ]
        elif test_type == "validation":
            return [
                f"'{field_name}' option selection is required",
                "Validation error is displayed for invalid selection",
                "User receives clear guidance on requirements",
            ]
        else:  # functional, positive
            return [
                f"'{field_name}' dropdown is visible and accessible",
                f"'{field_name}' dropdown options are accessible",
                f"Selected option in '{field_name}' is displayed correctly",
            ]
    
    # FILE UPLOAD
    elif element_type == ElementType.FILE_UPLOAD:
        if test_type == "negative":
            return [
                f"Invalid file type in '{field_name}' is rejected",
                "Error message indicates file requirements",
                f"'{field_name}' file upload is prevented",
            ]
        elif test_type == "boundary":
            return [
                f"'{field_name}' file size limits are enforced",
                "System handles large files correctly",
                "Upload behaves correctly at boundaries",
            ]
        elif test_type == "security":
            return [
                f"'{field_name}' file type validation is enforced",
                "Malicious file types are rejected",
                "Uploaded file is stored securely",
            ]
        else:  # functional, positive
            return [
                f"'{field_name}' file upload field is visible",
                f"File is accepted by '{field_name}'",
                f"Uploaded filename is displayed in '{field_name}'",
            ]
    
    # BUTTON
    elif element_type == ElementType.BUTTON:
        button_action = _extract_button_action(description)
        if test_type == "negative":
            return [
                f"'{field_name}' button click is prevented",
                "Error message is displayed",
                f"{button_action} does not occur",
            ]
        elif test_type == "validation":
            return [
                f"'{field_name}' button validation is performed",
                "Required fields are checked before action",
                "User feedback prevents invalid action",
            ]
        else:  # functional, positive
            return [
                f"'{field_name}' button is visible and clickable",
                f"'{field_name}' button is enabled",
                f"{button_action} is triggered after click",
            ]
    
    # LINK
    elif element_type == ElementType.LINK:
        if test_type == "negative":
            return [
                f"'{field_name}' link navigation is prevented",
                "Error message is displayed",
                "User remains on current page",
            ]
        elif test_type == "security":
            return [
                f"'{field_name}' link destination is validated",
                "Malicious URLs are rejected",
                "Navigation occurs only to trusted destinations",
            ]
        else:  # functional, positive, navigation
            results = [
                f"'{field_name}' link is visible and clickable",
                f"'{field_name}' link is enabled",
                f"User is redirected after clicking '{field_name}'",
            ]
            if href:
                results.append(f"URL changes to or contains '{href}'")
            results.append(f"'{field_name}' target page loads successfully")
            return results
    
    # FORM
    elif element_type == ElementType.FORM:
        form_name = _format_element_name(mapping)
        if test_type == "positive":
            return [
                f"All required fields in '{form_name}' are populated",
                f"'{form_name}' submits successfully",
                "Success message is displayed",
                "No validation errors appear",
            ]
        elif test_type == "negative":
            return [
                f"Invalid data is entered into '{form_name}'",
                f"'{form_name}' submission is prevented",
                "Validation errors are displayed for invalid fields",
                "Invalid fields are highlighted",
            ]
        elif test_type == "validation":
            return [
                f"'{form_name}' validation rules are enforced",
                "Validation messages are displayed for each error",
                "User feedback is clear and actionable",
            ]
        else:  # functional
            return [
                f"'{form_name}' is visible and accessible",
                f"All fields in '{form_name}' are accessible",
                f"'{form_name}' can be submitted",
            ]
    
    # PAGE LOAD
    elif element_type == ElementType.PAGE_LOAD:
        page_title = str(mapping.get("page_title") or mapping.get("title") or "page").strip()
        if test_type == "negative":
            return [
                "Page fails to load",
                "Error message is displayed to user",
                "User is informed of the issue",
            ]
        elif test_type == "security":
            return [
                "Page security headers are present",
                "Content is loaded from trusted sources only",
                "No security warnings are displayed",
            ]
        else:  # functional, positive
            results = [
                "Page loads successfully",
                "Page content is fully rendered",
                "Primary content is visible and accessible",
            ]
            if page_title:
                results.insert(1, f"Browser title matches '{page_title}'")
            return results
    
    # UNKNOWN / DEFAULT
    else:
        return [
            f"'{field_name}' is visible and accessible",
            f"'{field_name}' is enabled and responsive",
            f"'{field_name}' behaves as expected",
        ]


def _extract_button_action(description: str) -> str:
    """Extract expected button action from description.
    
    Returns description of what should happen after the button is clicked.
    """
    desc_lower = str(description or "").lower()
    
    if "submit" in desc_lower:
        return "Form submission occurs"
    elif "save" in desc_lower:
        return "Data is saved"
    elif "delete" in desc_lower:
        return "Item is deleted"
    elif "send" in desc_lower:
        return "Message is sent"
    elif "reset" in desc_lower:
        return "Form is reset to default values"
    elif "apply" in desc_lower:
        return "Changes are applied"
    elif "search" in desc_lower:
        return "Search is performed"
    elif "download" in desc_lower:
        return "File is downloaded"
    elif "upload" in desc_lower:
        return "File is uploaded"
    else:
        return "Expected action is triggered"


def get_element_specific_automation_hints(
    element_type: ElementType,
    mapping: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> Dict[str, Any]:
    """Generate Selenium-specific automation hints based on element type.
    
    Args:
        element_type: The detected or specified element type
        mapping: Mapping metadata
        description: Test description
        
    Returns:
        Dictionary with page_name, actions, and assertions
    """
    mapping = mapping or {}
    page_name = str(mapping.get("page_name") or mapping.get("page") or "Page").strip() or "Page"
    field_name = str(mapping.get("field_name") or mapping.get("name") or mapping.get("label") or "element").strip()
    
    # TEXT INPUT FAMILY
    if element_type in (ElementType.TEXT_INPUT, ElementType.EMAIL_INPUT, ElementType.PASSWORD_INPUT,
                       ElementType.PHONE_INPUT, ElementType.NUMBER_INPUT, ElementType.DATE_INPUT,
                       ElementType.SEARCH_INPUT, ElementType.URL_INPUT, ElementType.TEXTAREA):
        return {
            "page_name": page_name,
            "actions": [f"locate_{field_name}", f"clear_{field_name}", f"enter_{field_name}", "verify_value_displayed"],
            "assertions": [f"{field_name}_visible", f"{field_name}_accepts_input", "value_displayed_correctly"],
        }
    
    # CHECKBOX
    elif element_type == ElementType.CHECKBOX:
        return {
            "page_name": page_name,
            "actions": [f"locate_{field_name}", f"check_{field_name}", "verify_checkbox_state"],
            "assertions": [f"{field_name}_visible", f"{field_name}_can_be_checked", "checkbox_state_changed"],
        }
    
    # RADIO BUTTON
    elif element_type == ElementType.RADIO:
        return {
            "page_name": page_name,
            "actions": [f"locate_{field_name}", f"select_{field_name}", "verify_radio_state"],
            "assertions": [f"{field_name}_visible", f"{field_name}_can_be_selected", "radio_state_retained"],
        }
    
    # DROPDOWN / SELECT
    elif element_type in (ElementType.DROPDOWN, ElementType.SELECT):
        return {
            "page_name": page_name,
            "actions": [f"locate_{field_name}", f"open_{field_name}_dropdown", "select_option", "verify_selection"],
            "assertions": [f"{field_name}_visible", "options_accessible", "selected_option_displayed"],
        }
    
    # FILE UPLOAD
    elif element_type == ElementType.FILE_UPLOAD:
        return {
            "page_name": page_name,
            "actions": [f"locate_{field_name}", "upload_file", "verify_upload_success"],
            "assertions": ["file_accepted", "filename_displayed", "upload_complete"],
        }
    
    # BUTTON
    elif element_type == ElementType.BUTTON:
        return {
            "page_name": page_name,
            "actions": [f"locate_{field_name}_button", f"click_{field_name}", "verify_action_triggered"],
            "assertions": ["button_visible", "button_clickable", "action_triggered"],
        }
    
    # LINK
    elif element_type == ElementType.LINK:
        return {
            "page_name": page_name,
            "actions": [f"locate_{field_name}_link", f"click_{field_name}", "verify_navigation"],
            "assertions": ["link_visible", "link_clickable", "navigation_successful", "url_matches"],
        }
    
    # FORM
    elif element_type == ElementType.FORM:
        return {
            "page_name": page_name,
            "actions": ["locate_form", "populate_form_fields", "click_submit", "verify_submission"],
            "assertions": ["form_visible", "fields_accessible", "submission_successful", "success_message_displayed"],
        }
    
    # PAGE LOAD
    elif element_type == ElementType.PAGE_LOAD:
        return {
            "page_name": page_name,
            "actions": ["open_application", "verify_page_title", "verify_content_loaded"],
            "assertions": ["page_loaded", "title_correct", "content_visible"],
        }
    
    # UNKNOWN / DEFAULT
    else:
        return {
            "page_name": page_name,
            "actions": ["locate_element", "verify_visibility"],
            "assertions": ["element_visible"],
        }
