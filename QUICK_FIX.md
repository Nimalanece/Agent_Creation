# Quick Fix Guide: Gemini Metadata Error

**Error:** `ERROR: Missing or invalid metadata from Agent 1 or Agent 2`

## Root Cause
Gemini's template validation is failing because the test_case and/or test_data are incomplete.

## Quick Diagnosis

### Enable Debug Logging (1 minute)
```bash
cd backend
LOG_LEVEL=DEBUG python -m uvicorn app.main:app --reload
```

Make your API request, then **look for these log lines** in order:

1. **`INFO:app.api.routes.selenium:Agent3 request received:`**
   - Shows what endpoint received
   
2. **`DEBUG:app.core.gemini_service:Gemini template input:`**
   - Shows what's being processed
   
3. **`DEBUG:app.core.gemini_service:Gemini template rendered:`**
   - Shows actual JSON sent to Gemini

4. **`WARNING:app.core.gemini_service:Gemini raw output preview:`**
   - Shows Gemini's error response

## What to Check in the Logs

Look for these **required fields** in the template input logs:

```
test_case_keys=...          # Should include: application_url, test_steps, expected_results
test_case_steps=X           # X should be > 0 (not 0)
test_case_expected=...      # Should NOT be None/null
test_data_keys=...          # Should have fields if test requires input
```

## Fix Checklist

- [ ] `test_case` has `application_url` field? (Must be valid HTTP/HTTPS URL)
- [ ] `test_case` has `test_steps` list with entries? (Not empty)
- [ ] Each step has `locator_type` and `locator_value`? (Not placeholder values)
- [ ] `test_case` has `expected_results`? (Not empty/null)
- [ ] `test_data` has real values? (Not "test", "sample", "value")

## Common Issues & Fixes

### Issue: `test_case_steps=0`
**Fix:** Add test_steps list with at least 1 step
```python
test_case = {
    "test_steps": [
        {
            "action": "click_element",
            "locator_type": "id",
            "locator_value": "login-btn",
        }
    ]
}
```

### Issue: `test_case_expected=None`
**Fix:** Add expected_results field
```python
test_case = {
    "expected_results": ["Login successful"]
}
```

### Issue: `test_case_url=None`
**Fix:** Add application_url field
```python
test_case = {
    "application_url": "https://example.com"
}
```

### Issue: `test_data_keys=[]` but steps need input
**Fix:** Provide test_data with real values
```python
test_data = {
    "username": "john@example.com",
    "password": "SecurePass123!"
}
```

## Example: Complete Valid Request

```json
POST /api/agent3/generate-selenium

{
  "test_case": {
    "test_case_id": "TC001",
    "title": "Login with valid credentials",
    "application_url": "https://example.com/login",
    "test_steps": [
      {
        "action": "enter_text",
        "element_name": "Username",
        "locator_type": "id",
        "locator_value": "username-field",
        "locator_status": "available"
      },
      {
        "action": "click_element",
        "element_name": "Login Button",
        "locator_type": "id",
        "locator_value": "login-btn",
        "locator_status": "available"
      }
    ],
    "expected_results": ["User is logged in"]
  },
  "test_data": {
    "username": "john@example.com"
  }
}
```

Expected fields in test_case:
- ✓ application_url: Valid HTTPS URL
- ✓ test_steps: Array with at least 1 step
- ✓ Each step: action, locator_type, locator_value
- ✓ expected_results: Non-empty array

## Need More Help?

1. Run the diagnostic script:
   ```bash
   cd backend
   python diagnose_metadata.py
   ```

2. Read full guide:
   - See `DEBUG_METADATA_ERROR.md` for complete debugging guide
   - See `METADATA_ERROR_GUIDE.md` for validation requirements

3. Enable logging and share the logs showing:
   - What test_case_keys are present
   - What test_case_steps count is
   - What test_case_expected contains
   - What test_data_keys are provided
