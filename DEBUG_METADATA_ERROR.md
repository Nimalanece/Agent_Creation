# Debugging Gemini Metadata Errors

When you see: `ERROR: Missing or invalid metadata from Agent 1 or Agent 2.`

This error comes from **Gemini's template validation**, not the backend validation. Gemini is analyzing the test_case and test_data JSON and determining they don't have required fields.

## Enable Debug Logging

To see exactly what test_case and test_data are being sent to Gemini, enable DEBUG logging:

### Option 1: Environment Variable
```bash
export LOG_LEVEL=DEBUG
python -m uvicorn app.main:app --reload
```

### Option 2: Modify app/main.py
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Option 3: Temporary Console Test
```bash
cd backend
python -c "
import logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

import sys, pathlib, asyncio
sys.path.insert(0, str(pathlib.Path.cwd()))

from app.core.gemini_service import GeminiService

test_case = {
    'title': 'Test Login',
    'application_url': 'https://example.com',
    'test_steps': [{
        'action': 'click_element',
        'locator_type': 'id',
        'locator_value': 'login-btn',
    }],
    'expected_results': ['Login successful'],
}

test_data = {'username': 'test@example.com', 'password': 'pass123'}

try:
    asyncio.run(GeminiService().generate_selenium_code(test_case, test_data))
except Exception as e:
    print(f'Error: {e}')
"
```

## What Debug Logs Show

### Endpoint Log (selenium.py)
```
INFO:app.api.routes.selenium:Agent3 request received: test_case_keys=['title', 'application_url', ...] test_case_url=https://example.com test_steps=3 expected_results=['...'] test_data_keys=['username', 'password']
```

This shows what the endpoint received.

### Gemini Service Logs (gemini_service.py)
```
DEBUG:app.core.gemini_service:Gemini template input: test_case_keys=['title', 'application_url', ...] test_case_steps=3 test_case_expected=['...'] test_data_keys=['username', 'password']
```

This shows what's being sent to the Gemini template.

```
DEBUG:app.core.gemini_service:Gemini template rendered (first 1000 chars):
Agent 1 Test Case:
{"title": "Test Login", "application_url": "https://example.com", ...}

Agent 2 Test Data:
{"username": "test@example.com", "password": "pass123"}
```

This shows the actual JSON that Gemini receives.

## How to Use Logs to Debug

1. **Run server with DEBUG logging enabled**
2. **Make your API request to POST /api/agent3/generate-selenium**
3. **Check the logs for these messages in order:**
   - `Agent3 request received:` - What endpoint got
   - `Gemini template input:` - What's being processed
   - `Gemini template rendered:` - Actual JSON sent to Gemini
   - `WARNING:app.core.gemini_service:Gemini raw output:` - Gemini's response

4. **Compare what's in the JSON with the validation requirements:**

| Required Field | Check |
|----------------|-------|
| `application_url` | Must be valid HTTP/HTTPS URL |
| `test_steps` | Must be non-empty list |
| `test_steps[].locator_type` | Must be from valid list (id, css_selector, xpath, etc) |
| `test_steps[].locator_value` | Must not be empty or placeholder value |
| `expected_results` | Must be non-empty list or string |
| `test_data` (if needed) | Must have real values, not "sample"/"test"/"value" |

## Example: Debugging a Failure

### Log output shows:
```
DEBUG:app.core.gemini_service:Gemini template input: test_case_keys=['title'] test_case_steps=0 test_case_expected=None test_data_keys=[]
```

### Problem identified:
- `test_steps=0` - No steps provided
- `test_case_expected=None` - No expected results
- Only "title" key - missing application_url

### Fix:
```python
test_case = {
    'title': 'Test Login',
    'application_url': 'https://example.com',  # ← ADD THIS
    'test_steps': [                             # ← ADD STEPS
        {
            'action': 'click_element',
            'element_name': 'Login Button',
            'locator_type': 'id',
            'locator_value': 'login-btn',
            'locator_status': 'available',
        }
    ],
    'expected_results': ['Login successful'],  # ← ADD THIS
}
```

## Common Issues Found in Debug Logs

### Issue 1: Empty test_steps
```
test_case_steps=0  ← PROBLEM
```
**Fix**: Ensure test_case has non-empty test_steps list

### Issue 2: Missing application_url
```
test_case_url=None  ← PROBLEM
```
**Fix**: Add `application_url` field to test_case

### Issue 3: Missing expected_results
```
test_case_expected=None  ← PROBLEM
```
**Fix**: Add `expected_results` field to test_case

### Issue 4: No test_data values
```
test_data_keys=[]  ← PROBLEM (if test requires input)
```
**Fix**: Provide test_data dict with field values

### Issue 5: Placeholder values in test_data
```
test_data_keys=['username']
# But value is "sample", "test", or "value"
```
**Fix**: Use real, specific values like "john@example.com"

## Enable Logging Persistently

Create or update `backend/logging.conf`:

```ini
[loggers]
keys=root,app

[logger_root]
level=INFO
handlers=console

[logger_app]
level=DEBUG
qualname=app
handlers=console

[handlers]
keys=console

[handler_console]
class=StreamHandler
level=DEBUG
formatter=detailed
args=(sys.stderr,)

[formatters]
keys=detailed

[formatter_detailed]
format=%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

Then load it in app/main.py:
```python
import logging.config
logging.config.fileConfig('logging.conf', disable_existing_loggers=False)
```

## Questions?

If you're still seeing the metadata error after enabling debug logging:
1. Share the debug log output showing what test_case_keys and test_data_keys are in the logs
2. Compare against the validation requirements table above
3. Check if any field values are placeholders (sample, test, value)
