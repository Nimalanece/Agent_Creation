# Fix: Generated Code Now Uses Supplied Test Data

## Problem
Generated Selenium code was not using supplied test data because:
1. Orchestrator generated `agent_2_contract` with test data but didn't prepare it for Agent 3
2. Selenium endpoint had to fallback to auto-extracting test data from `agent_2_contract` instead of using it directly
3. This fallback approach was fragile and required guessing the data structure

## Solution
Three-part fix to ensure test data flows properly from Agent 2 → Agent 3:

### Part 1: Orchestrator Extraction (orchestrator_service.py)
The orchestrator now explicitly extracts test data from `agent_2_contract` and includes it in the result:

```python
# After generating agent_2_contract, extract test data for Agent 3
agent3_test_data = {}
for data_category in ["positive_data", "negative_data", "boundary_data", "validation_data"]:
    if data_list and "generated_data" in first_dataset:
        agent3_test_data = {
            "scenario_id": first_dataset.get("scenario_id"),
            "requires_test_data": agent_2_contract_dict.get("requires_test_data", True),
            "generated_data": first_dataset.get("generated_data", {}),
            "data_category": data_category,
        }
        break

# Include in orchestrator result
result["agent_3_test_data"] = agent3_test_data
```

**Output**: The `/api/full-analysis` endpoint now returns `agent_3_test_data` alongside `agent_2_contract`

### Part 2: Improved Selenium Endpoint (routes/selenium.py)
The endpoint now has clear priority for test data:

1. **Priority 1**: Use provided `test_data` if supplied (directly passed)
2. **Priority 2**: Extract from `agent_2_contract` if provided (fallback)
3. **Priority 3**: Log warning if no test data available

Better logging shows which source the test data came from.

### Part 3: Schema Documentation (schemas.py)
Updated `Agent3GenerationRequest` schema to clarify:
- `test_data` field should be populated from orchestrator's `agent_3_test_data`
- `agent_2_contract` is a fallback for auto-extraction

## How to Use

### For API Clients:
1. Call `/api/full-analysis` endpoint
2. Extract `agent_3_test_data` from the response
3. Pass it as `test_data` when calling `/api/agent3/generate-selenium`

```json
// Step 1: Full analysis
POST /api/full-analysis
Response includes:
{
  "agent_3_test_data": {
    "scenario_id": "login-001",
    "generated_data": { "username": "test_user", "password": "test123" },
    "requires_test_data": true
  }
}

// Step 2: Generate Selenium code with test data
POST /api/agent3/generate-selenium
{
  "test_case": { ... },
  "test_data": { ... },  // <-- Pass agent_3_test_data here
  "application_url": "https://example.com",
  "agent_2_contract": { ... }  // Optional fallback
}
```

## Benefits
- ✅ Test data is no longer guessed or auto-extracted
- ✅ Clear, explicit data flow from orchestrator to code generation
- ✅ Better logging for debugging data flow issues
- ✅ Backward compatible (fallback extraction still works)
- ✅ Generated Selenium code now has correct test values injected

## Files Changed
1. `backend/app/services/orchestrator_service.py` - Extract test data
2. `backend/app/api/routes/selenium.py` - Clear priority logging
3. `backend/app/models/schemas.py` - Documentation

## Testing
To verify the fix:
```bash
# Call full_analysis endpoint and capture agent_3_test_data
curl -X POST http://localhost:8000/api/full-analysis \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Extract agent_3_test_data from response and pass to selenium endpoint
curl -X POST http://localhost:8000/api/agent3/generate-selenium \
  -H "Content-Type: application/json" \
  -d '{
    "test_case": {...},
    "test_data": {...},  # From agent_3_test_data
    "application_url": "https://example.com"
  }'
```
