# Agent 3 Metadata Error - Diagnosis & Solutions

## Overview

The error **"ERROR: Missing or invalid metadata from Agent 1 or Agent 2"** occurs when testcases fail validation before being sent to Gemini for Selenium code generation.

This guide explains what each validation check does and how to fix failures.

## Quick Diagnostic

### Run the Diagnostic Script
```bash
cd backend
python diagnose_metadata.py
```

This will show:
- Which validation checks pass/fail
- Summary of test_case and test_data fields
- Exact error messages

### Check Server Logs
When running the FastAPI server:
```bash
python -m uvicorn app.main:app --reload
```

Look for `ERROR` level logs with format:
```
Agent 3 metadata validation FAILED - N errors detected:
  - Error 1 message
  - Error 2 message
  - Error 3 message
test_case={...}
test_data={...}
```

## Validation Requirements

### 1. Input Types ✓ Required
**Check**: Both `test_case` and `test_data` must be dictionaries

**Error if fails**: 
- `Agent 1 test case and Agent 2 test data must be objects.`

**Fix**:
```python
# Must be dicts, not strings/lists/etc
test_case = {"title": "...", "test_steps": [...], ...}
test_data = {"username": "...", "password": "...", ...}
```

### 2. Application URL ✓ Required
**Check**: Test case must have `application_url` field or passed as parameter

**Error if fails**:
- `Missing application_url from upstream agents.`
- `application_url must be a valid plain HTTP or HTTPS URL.`

**Fix**:
```python
test_case = {
    "application_url": "https://example.com",  # ← MUST be valid HTTP/HTTPS
    # ... other fields
}
```

### 3. Test Steps ✓ Required
**Check**: Must have `test_steps` or `steps` list with at least one step

**Error if fails**:
- `Missing action metadata from Agent 1 test case.`

**Fix**:
```python
test_case = {
    "test_steps": [
        {
            "action": "click_element",
            "element_name": "Login Button",
            "locator_type": "id",
            "locator_value": "login-btn",
            # ... other fields
        }
    ],
    # ... other fields
}
```

### 4. Step Locators ✓ Required (for DOM actions)
**Check**: Each step that performs a DOM action must have valid `locator_type` and `locator_value`

**Valid locator types**:
- `id`, `name`, `data-testid`, `data_testid`, `href`, `css`, `css_selector`, `xpath`, `class`, `url`, `title`

**DOM action types**:
- `locate_element`, `click_element`, `enter_text`, `input_text`, `fill`, `send_keys`, `select_checkbox`, `select_radio`, `select_dropdown_option`, `upload_file`, `submit_form`, `populate_form`, `verify_element_visible`, `click`, `type_text`, `set_value`, `select_option`, `select_dropdown`, `check`, `uncheck`, `choose_radio`, `upload`, `submit`, `locate`, `assert_visible`, `verify_visible`

**Error if fails**:
- `Each DOM action must include locator_type and locator_value.`
- `Missing valid locator from Agent 1 test case.`

**Fix**:
```python
test_case = {
    "test_steps": [
        {
            "action": "click_element",
            "element_name": "Login Button",
            "locator_type": "id",           # ← MUST be from valid list
            "locator_value": "login-btn",   # ← MUST be non-empty
            "locator_status": "available",  # ← Should indicate it's verified
        },
        {
            "action": "verify_element_visible",
            "element_name": "Success Message",
            "locator_type": "css_selector",
            "locator_value": ".success-message",
            "locator_status": "available",
        }
    ],
}
```

### 5. Locator Values ✓ Required (must be real)
**Check**: Locator values must be actual locators, not labels, placeholders, or generic terms

**Blocked placeholder values**:
- `sample`, `test`, `value`, `element`, `input_field`, `submit_button`, `navigation_link`, `primary_content`, `application_url`

**Error if fails**:
- `Locator values must be actual supplied locators, not labels or placeholders.`
- `Locator values must be plain text.`

**Fix**:
```python
# WRONG - using label as locator value
test_case = {
    "test_steps": [{
        "action": "click_element",
        "element_name": "Submit Button",      # ← This is the LABEL
        "locator_value": "Submit Button",     # ← WRONG - using label
        "locator_type": "id",
    }]
}

# RIGHT - using actual locator
test_case = {
    "test_steps": [{
        "action": "click_element",
        "element_name": "Submit Button",      # ← This is the LABEL
        "locator_value": "submit-btn-id",     # ← CORRECT - actual locator
        "locator_type": "id",
    }]
}
```

### 6. Expected Results ✓ Required
**Check**: Test case must have `expected_results` (list) or `expected_result` (string)

**Error if fails**:
- `Missing expected results from Agent 1 test case.`

**Fix**:
```python
test_case = {
    "expected_results": ["Login form is displayed", "User is authenticated"],
    # OR use singular form:
    # "expected_result": "Login form is displayed",
}
```

### 7. Test Data Values ✓ Conditional
**Check**: If test case requires input data (has input actions or required_data fields), test_data must provide values

**Error if fails**:
- `Missing usable field-specific values from Agent 2 test data.`
- `Agent 2 test data contains placeholder values.`

**When required**:
- Test case has input actions like `enter_text`, `input_text`, `fill`, `send_keys`, `type_text`, `set_value`, `select_dropdown_option`, `upload_file`
- Test case has `required_data` or `input_fields` list (unless it's navigation-only)

**When NOT required**:
- Test case is navigation-only (title contains: `navigate`, `page load`, `visibility`, `presence`, `landing`)
- Test case has `requires_test_data: false`
- Test case only has non-input actions like `click_element`, `verify_visible`

**Fix**:
```python
# If test_case has input fields
test_case = {
    "input_fields": ["username", "password"],
    "test_steps": [
        {"action": "enter_text", "locator_type": "id", "locator_value": "user-field", ...},
        {"action": "enter_text", "locator_type": "id", "locator_value": "pass-field", ...},
    ]
}

# Then test_data MUST provide values
test_data = {
    "username": "testuser@example.com",  # ← Real value
    "password": "SecurePass123!",        # ← Real value (NOT "password" placeholder)
}
```

## Complete Valid Example

```python
test_case = {
    "test_case_id": "TC001",
    "title": "Login with valid credentials",
    "priority": "high",
    "application_url": "https://example.com/login",
    "test_steps": [
        {
            "action": "enter_text",
            "element_name": "Username Field",
            "locator_type": "id",
            "locator_value": "username-input",
            "locator_status": "available",
        },
        {
            "action": "enter_text",
            "element_name": "Password Field",
            "locator_type": "id",
            "locator_value": "password-input",
            "locator_status": "available",
        },
        {
            "action": "click_element",
            "element_name": "Login Button",
            "locator_type": "css_selector",
            "locator_value": "button.login-btn",
            "locator_status": "available",
        },
        {
            "action": "verify_element_visible",
            "element_name": "Dashboard",
            "locator_type": "xpath",
            "locator_value": "//div[@id='dashboard']",
            "locator_status": "available",
        }
    ],
    "expected_results": ["User is logged in", "Dashboard is visible"],
    "input_fields": ["username", "password"],
}

test_data = {
    "username": "john@example.com",
    "password": "SecurePass123!",
}
```

## Troubleshooting Checklist

- [ ] `test_case` is a dict (not string/list/None)
- [ ] `test_data` is a dict (not string/list/None)
- [ ] `application_url` is present and valid HTTP/HTTPS
- [ ] `test_steps` list exists and has at least 1 step
- [ ] Each step has: `action`, `locator_type`, `locator_value`
- [ ] `locator_type` is from valid list (id, css_selector, xpath, etc)
- [ ] `locator_value` is not empty and not a placeholder
- [ ] `expected_results` or `expected_result` is present
- [ ] If test has input actions, `test_data` provides real values
- [ ] No placeholder values in `test_data` (like "test", "sample", "value")
- [ ] No HTML/control characters in locator values or URLs

## Getting More Details

When debugging, check the Enhanced Error Log output which shows:
```
Agent 3 metadata validation FAILED - N errors detected:
  - Error message 1
  - Error message 2
  - Error message 3
test_case={title='...', application_url='...', test_steps_count=3, expected_results=[...]}
test_data={keys=['field1', 'field2'], data_values_count=2}
```

This tells you:
- Exact validation failures
- Number of test steps found
- What data fields are provided
- Count of usable data values

## Questions?

Refer to the diagnostic script output or check `app/core/gemini_service.py` lines 184-321 for the complete validation logic.
