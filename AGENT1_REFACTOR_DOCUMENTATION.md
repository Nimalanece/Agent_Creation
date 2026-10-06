# Agent 1 Refactor: Element-Specific Test Case Generation

## Overview

Agent 1 (QA Discovery & Test Design Agent) has been refactored to generate **element-specific test cases** instead of reusing generic templates across different element types.

### Problem Solved

**Before:** Agent 1 was generating the same test steps and expected results for all elements:
```
Link "Check Box" navigation scenario:
❌ Steps: [locate_element, enter_text]  
❌ Expected: ["Field accepts input", "Value is displayed"]
Problem: Links should be CLICKED, not typed into!

Button submission scenario:
❌ Steps: [locate_element, enter_text]
❌ Expected: ["Field accepts input", "Value is displayed"]
Problem: Buttons can't have text entered!
```

**After:** Agent 1 now generates element-type-specific test cases:
```
Link "Check Box" navigation scenario:
✅ Steps: [locate_element, click_element]
✅ Expected: ["Link is clickable", "User is redirected", "URL matches '/checkbox'"]
✅ Mapping: {element_type: "link", tag: "a", href: "/checkbox"}

Button submission scenario:
✅ Steps: [locate_element, click_element]  
✅ Expected: ["Button is clickable", "Expected action is triggered"]
✅ Mapping: {element_type: "button", tag: "button"}

Text Input "First Name" scenario:
✅ Steps: [locate_element, enter_text]
✅ Expected: ["First Name is visible", "First Name accepts user input", "Value is displayed"]
✅ Mapping: {element_type: "text_input", tag: "input", type: "text"}
```

---

## Architecture Changes

### 1. New Module: `element_detection.py`

**Location:** `backend/app/services/element_detection.py`

**Purpose:** Provides centralized element type detection and element-specific rule generation.

**Key Components:**

#### Element Type Enum
```python
class ElementType(str, Enum):
    TEXT_INPUT = "text_input"
    EMAIL_INPUT = "email_input"
    PASSWORD_INPUT = "password_input"
    PHONE_INPUT = "phone_input"
    NUMBER_INPUT = "number_input"
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
```

#### Detection Function
```python
def detect_element_type(
    mapping: Optional[Dict[str, Any]] = None,
    description: str = "",
    title: str = "",
    selector: str = "",
) -> ElementType:
    """Detect element type from multiple data sources."""
```

**Detection Sources (Priority Order):**
1. Explicit `element_type` in mapping metadata
2. HTML5 `input_type` attributes (email, tel, password, etc.)
3. HTML tag names (a, button, input, select, form, etc.)
4. Field type from Agent 1 schema
5. Pattern matching in description/title/selector
6. CSS selector analysis

#### Step Generation Function
```python
def get_element_specific_steps(
    element_type: ElementType,
    mapping: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> List[Dict[str, Any]]:
    """Generate element-specific test steps based on element type."""
```

**Element-Specific Steps:**
- **Text Inputs:** `locate_element` → `enter_text`
- **Links:** `locate_element` → `click_element`
- **Buttons:** `locate_element` → `click_element`
- **Checkboxes:** `locate_element` → `select_checkbox`
- **Radio Buttons:** `locate_element` → `select_radio`
- **Dropdowns:** `locate_element` → `select_dropdown_option`
- **File Upload:** `locate_element` → `upload_file`
- **Forms:** `locate_element` → `populate_form` → `submit_form`
- **Page Load:** `open_url` → `verify_page_title` → `verify_element_visible`

#### Expected Results Function
```python
def get_element_specific_expected_results(
    element_type: ElementType,
    test_type: str = "functional",
    mapping: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> List[str]:
    """Generate element-specific expected results based on element type and test type."""
```

**Example Expected Results:**

| Element Type | Functional | Positive | Negative | Validation | Boundary | Security |
|---|---|---|---|---|---|---|
| **Link** | Link is visible, Link is clickable, User is redirected | | Link navigation failed, Error displayed | | | Malicious URLs rejected |
| **Button** | Button is visible, Button is clickable, Action triggered | | Button click prevented | Field validation required | | |
| **Text Input** | Field is visible, Accepts input, Value displayed | | Invalid input rejected | Field required, Error shown | Length limits enforced | Input sanitized, XSS rejected |
| **Checkbox** | Visible, Can be selected, State changes | | Selection prevented | Required checkbox | Multiple constraints | |
| **Radio** | Visible, Can be selected, State retained | | Selection prevented | Must select one | | |
| **Dropdown** | Visible, Options accessible, Selected shown | | Invalid selection rejected | Required selection | | |
| **File Upload** | Visible, File accepted, Filename shown | | Invalid file type rejected | Size limits enforced | Large files handled | Malicious files rejected |
| **Form** | Visible, Fields accessible, Submittable | All fields valid, Success msg, No errors | Invalid data, Submission prevented, Errors shown | Required fields, Validation msg | | Required field validation |
| **Page Load** | Loads successfully, Title correct, Content visible | | Load fails, Error shown | | | No security warnings |

#### Automation Hints Function
```python
def get_element_specific_automation_hints(
    element_type: ElementType,
    mapping: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> Dict[str, Any]:
    """Generate Selenium-specific automation hints for each element type."""
```

Returns reusable action names and assertions for Selenium integration (Agent 3).

---

### 2. Updated: `scenarios_service.py`

**Changes:**
- Imported element detection utilities
- Refactored `_scenario_steps_for_mapping()` to use `detect_element_type()` and `get_element_specific_steps()`
- Refactored `_scenario_expected_results_for_mapping()` to use `detect_element_type()` and `get_element_specific_expected_results()`
- Updated function calls to pass `test_type` parameter for context-aware results

**Before:**
```python
def _scenario_steps_for_mapping(mapping, label):
    # Generic logic that reused enter_text for everything
    return [
        {"step_number": 1, "action": "locate_element", ...},
        {"step_number": 2, "action": "enter_text", ...},  # ❌ Wrong for links/buttons
    ]
```

**After:**
```python
def _scenario_steps_for_mapping(mapping, label):
    element_type = detect_element_type(mapping, ...)
    steps = get_element_specific_steps(element_type, mapping, ...)
    # Returns different steps based on element_type
    # Links: click_element
    # Buttons: click_element
    # Inputs: enter_text
    # etc.
    return steps
```

---

### 3. Updated: `testcases_service.py`

**Changes:**
- Imported element detection utilities
- Completely refactored `_generate_expected_results_for_test_type()` to use element detection
- Function now generates scenario-specific assertions matching both `element_type` AND `test_type`

**Before:**
```python
def _generate_expected_results_for_test_type(test_type, title, description, mapping, input_fields):
    # Nested if-statements checking test_type only
    if test_type == "functional":
        return ["Page loads successfully", "Browser title...", "Content visible"]
    if test_type == "navigation":
        return ["Redirected", "URL contains", "Page loads"]
    # etc - same results regardless of element type
```

**After:**
```python
def _generate_expected_results_for_test_type(test_type, title, description, mapping, input_fields):
    element_type = detect_element_type(mapping, description, title, ...)
    expected = get_element_specific_expected_results(
        element_type=element_type,
        test_type=test_type,
        mapping=mapping,
        description=description
    )
    # Returns different results based on BOTH element_type AND test_type
    return expected
```

---

### 4. Updated: Prompt Templates

#### `generate_scenarios.j2`
- Added **ELEMENT-SPECIFIC ACTIONS** section with explicit mappings for each element type
- Added **ELEMENT-SPECIFIC EXPECTED RESULTS** guidance
- Instructs LLM to generate different steps for links (click) vs inputs (enter_text) vs buttons
- Includes mapping metadata requirements (element_type, tag_name, selector, field_type)

#### `generate_testcases.j2`
- Added **ELEMENT-SPECIFIC ACTIONS** section with explicit "DO NOT MIX ACTIONS" warning
- Provides LLM with clear guidance on what actions apply to each element type
- Includes examples of correct vs incorrect actions
- Emphasizes that links should NEVER use enter_text
- Requires mapping objects to include element type information

---

## Generation Rules

### TEXT INPUT FAMILY
**Elements:** text, email, password, phone, number, date, search, URL, textarea

**Steps:**
```json
[
  {"step_number": 1, "action": "locate_element", "target": "input#firstName"},
  {"step_number": 2, "action": "enter_text", "target": "input#firstName", "value": "Sample Text"}
]
```

**Expected Results:**
- Functional: "Field is visible", "Field accepts input", "Value is displayed"
- Positive: Form submits successfully, Success message displayed
- Negative: "Validation fails", "Error displayed", "Submission prevented"
- Validation: "Validation enforced", "Error shown", "User feedback received"

---

### LINK ELEMENT
**Elements:** `<a>` tags with navigation intent

**Steps:**
```json
[
  {"step_number": 1, "action": "locate_element", "target": "a.router-link"},
  {"step_number": 2, "action": "click_element", "target": "a.router-link", "expected_url": "/checkbox"}
]
```

**Expected Results:**
- Functional: "Link is visible", "Link is clickable", "User redirected", "URL matches", "Page loads"
- Navigation: "Link is clickable", "Navigation successful", "URL matches destination"
- Security: "Link destination validated", "Malicious URLs rejected", "Only trusted destinations"

---

### BUTTON ELEMENT
**Elements:** `<button>` and `<input type="button">`

**Steps:**
```json
[
  {"step_number": 1, "action": "locate_element", "target": "button#submit"},
  {"step_number": 2, "action": "click_element", "target": "button#submit"}
]
```

**Expected Results:**
- Functional: "Button is visible", "Button is clickable", "Action triggered"
- Positive: "Action executed successfully", "Expected state change"
- Negative: "Click prevented", "Error displayed"

---

### CHECKBOX ELEMENT
**Elements:** `<input type="checkbox">`

**Steps:**
```json
[
  {"step_number": 1, "action": "locate_element", "target": "input#agree"},
  {"step_number": 2, "action": "select_checkbox", "target": "input#agree"}
]
```

**Expected Results:**
- Functional: "Checkbox is visible", "Can be selected", "State changes correctly"
- Validation: "Checkbox must be selected", "Error shown if required"

---

### RADIO BUTTON ELEMENT
**Elements:** `<input type="radio">`

**Steps:**
```json
[
  {"step_number": 1, "action": "locate_element", "target": "input[name=gender]"},
  {"step_number": 2, "action": "select_radio", "target": "input[name=gender]"}
]
```

**Expected Results:**
- Functional: "Option is visible", "Can be selected", "Selected state retained"
- Validation: "At least one option required", "Validation error if missing"

---

### DROPDOWN / SELECT ELEMENT
**Elements:** `<select>`, dropdown components

**Steps:**
```json
[
  {"step_number": 1, "action": "locate_element", "target": "select#country"},
  {"step_number": 2, "action": "select_dropdown_option", "target": "select#country", "value": "first_option"}
]
```

**Expected Results:**
- Functional: "Dropdown visible", "Options accessible", "Selection displayed"
- Validation: "Selection is required", "Validation error if empty"

---

### FILE UPLOAD ELEMENT
**Elements:** `<input type="file">`

**Steps:**
```json
[
  {"step_number": 1, "action": "locate_element", "target": "input#file-upload"},
  {"step_number": 2, "action": "upload_file", "target": "input#file-upload", "value": "test_file.txt"}
]
```

**Expected Results:**
- Functional: "Upload field visible", "File accepted", "Filename displayed"
- Negative: "Invalid file type rejected", "Error shown"
- Boundary: "File size limits enforced"
- Security: "File type validated", "Malicious files rejected"

---

### FORM ELEMENT
**Elements:** `<form>` tags

**Steps:**
```json
[
  {"step_number": 1, "action": "locate_element", "target": "form#login"},
  {"step_number": 2, "action": "populate_form", "target": "form#login", "value": "valid_data"},
  {"step_number": 3, "action": "submit_form", "target": "form#login"}
]
```

**Expected Results:**
- Positive: "All fields populated", "Submits successfully", "Success message", "No errors"
- Negative: "Invalid data rejected", "Submission prevented", "Errors displayed"
- Validation: "Validation rules enforced", "Clear error messages"

---

### PAGE LOAD ELEMENT
**Elements:** Page-level scenarios

**Steps:**
```json
[
  {"step_number": 1, "action": "open_url", "target": "application_url"},
  {"step_number": 2, "action": "verify_page_title", "expected_value": "expected_title"},
  {"step_number": 3, "action": "verify_element_visible", "target": "primary_content"}
]
```

**Expected Results:**
- Functional: "Page loads successfully", "Title matches", "Content visible"
- Security: "Security headers present", "Content from trusted sources"

---

## Integration Points

### Agent 1 → Agent 2
Mapping metadata now includes `element_type` and `tag_name`, allowing Agent 2 to:
- Skip non-input element types in test data generation
- Generate appropriate validation data for input fields
- Understand element-specific constraints

### Agent 1 → Agent 3 (Selenium)
Steps now use element-specific actions:
- `click_element` for navigable elements (links, buttons)
- `enter_text` for input elements
- `select_checkbox`/`select_radio` for selection elements
- `upload_file` for file inputs
- Automation hints include Selenium-style action names

---

## Test Coverage

### Regression Tests
**File:** `backend/app/tests/test_testcases_expected_results.py`

**Status:** ✅ **14/14 PASSING**

Tests validate:
- Page Load scenarios generate "Page loads successfully"
- Navigation scenarios generate "Link is clickable", "User is redirected"
- Input field scenarios generate field-specific assertions
- Positive form submission generates success assertions
- Negative form submission generates rejection assertions
- Validation scenarios generate validation assertions
- Boundary scenarios generate limit enforcement assertions
- Security scenarios generate security validation assertions
- Button click scenarios generate action-triggered assertions
- Link scenarios generate navigation-specific assertions
- Different test_types generate different expected results
- Mapping context influences results
- Results are lists, not generic fallbacks
- Empty inputs trigger sensible fallbacks

---

## Example Output

### Link Scenario (Before vs After)

**Before (Generic):**
```json
{
  "scenario_id": "TS_14",
  "title": "Verify link 'Check Box' navigates to '/checkbox'",
  "test_type": "navigation",
  "steps": [
    {"step_number": 1, "action": "locate_element", "target": "a.router-link"},
    {"step_number": 2, "action": "enter_text", "target": "a.router-link", "value": "Sample"}
  ],
  "expected_results": [
    "Target field accepts text input",
    "Entered value is displayed correctly"
  ],
  "mapping": {"href": "/checkbox", "selector": "a.router-link"}
}
```

**After (Element-Specific):**
```json
{
  "scenario_id": "TS_14",
  "title": "Verify link 'Check Box' navigates to '/checkbox'",
  "test_type": "navigation",
  "steps": [
    {"step_number": 1, "action": "locate_element", "target": "a.router-link"},
    {"step_number": 2, "action": "click_element", "target": "a.router-link", "expected_url": "/checkbox"}
  ],
  "expected_results": [
    "Link is visible",
    "Link is clickable",
    "User is redirected to target page",
    "URL contains '/checkbox'",
    "Target page loads successfully"
  ],
  "mapping": {
    "href": "/checkbox",
    "selector": "a.router-link",
    "element_type": "link",
    "tag_name": "a"
  }
}
```

---

## Verification

To verify element-specific generation:

```bash
cd backend
python -m pytest app/tests/test_testcases_expected_results.py -v
```

Expected output:
```
14 passed in 0.26s
```

Or run the example demonstrating all element types:
```bash
python example_element_specific_generation.py
```

---

## Key Benefits

1. ✅ **Correctness:** Links are clicked, not typed into
2. ✅ **Specificity:** Test assertions match element behavior
3. ✅ **Maintainability:** Element rules centralized in one module
4. ✅ **Extensibility:** New element types easily added
5. ✅ **Testability:** Comprehensive regression tests
6. ✅ **LLM Alignment:** Prompts guide LLM away from generic templates
7. ✅ **Downstream Compatibility:** Mapping includes element_type for Agent 2/3

---

## Files Changed

| File | Type | Change |
|------|------|--------|
| `backend/app/services/element_detection.py` | **NEW** | Element type detection and rule generation |
| `backend/app/services/scenarios_service.py` | **MODIFIED** | Integrated element detection |
| `backend/app/services/testcases_service.py` | **MODIFIED** | Integrated element detection |
| `backend/app/prompts/generate_scenarios.j2` | **MODIFIED** | Added element-specific guidance |
| `backend/app/prompts/generate_testcases.j2` | **MODIFIED** | Added element-specific guidance |
| `backend/app/tests/test_testcases_expected_results.py` | **MODIFIED** | Updated tests with mapping metadata |
| `backend/example_element_specific_generation.py` | **NEW** | Demonstration example |

---

## Next Steps

1. **Agent 2 Integration:** Update test data generation to skip non-input elements
2. **Agent 3 Integration:** Update Selenium code generation to use element-specific actions
3. **UI Updates:** Ensure frontend properly displays element-specific steps and assertions
4. **Full E2E Test:** Run complete workflow with actual page analysis
5. **LLM Validation:** Verify Groq LLM follows element-specific prompt guidance
