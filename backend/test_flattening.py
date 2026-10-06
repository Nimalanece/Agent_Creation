"""
Test the test_data flattening fix
"""
import sys
import pathlib

root = pathlib.Path(r'c:/Users/2000189345/Documents/agent creation/backend')
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from app.core.gemini_service import GeminiService

# Test case with nested test_data (as it comes from orchestrator)
test_case = {
    "test_case_id": "TC001",
    "title": "Test Login",
    "application_url": "https://demoqa.com/automation-practice-form",
    "test_steps": [
        {
            "action": "enter_text",
            "element_name": "Username Field",
            "locator_type": "id",
            "locator_value": "username-field",
            "locator_status": "available",
        },
        {
            "action": "click_element",
            "element_name": "Login Button",
            "locator_type": "id",
            "locator_value": "login-button",
            "locator_status": "available",
        }
    ],
    "expected_results": ["Login successful"],
}

# Nested test_data (as returned by build_test_data_contract)
test_data_nested = {
    "scenario_id": "SCENARIO001",
    "requires_test_data": True,
    "generated_data": {
        "username": "testuser@example.com",
        "password": "SecurePass123!",
    }
}

print("Testing test_data flattening...")
print("=" * 60)

# Test validation with nested structure
validation_errors = GeminiService.validate_generation_inputs(
    test_case, test_data_nested, None
)

print(f"\nValidation errors with nested test_data: {len(validation_errors)}")
if validation_errors:
    for error in validation_errors:
        print(f"  - {error}")
else:
    print("  PASS - No validation errors!")

print("\n" + "=" * 60)
print("Test Data Analysis:")
print(f"  Original keys: {list(test_data_nested.keys())}")
print(f"  Generated data: {test_data_nested.get('generated_data')}")

# Simulate what GeminiService does
clean_test_case = GeminiService._sanitize_input(test_case)
clean_test_data = GeminiService._sanitize_input(test_data_nested)

# Apply the flattening logic
if isinstance(clean_test_data, dict) and "generated_data" in clean_test_data:
    generated_data = clean_test_data.get("generated_data") or {}
    if isinstance(generated_data, dict):
        flattened = {}
        if "scenario_id" in clean_test_data:
            flattened["scenario_id"] = clean_test_data["scenario_id"]
        if "requires_test_data" in clean_test_data:
            flattened["requires_test_data"] = clean_test_data["requires_test_data"]
        flattened.update(generated_data)
        clean_test_data = flattened

print(f"\n  Flattened keys: {list(clean_test_data.keys())}")
print(f"  Flattened data: {clean_test_data}")

# Check extracted values
data_values = GeminiService._supplied_data_values(clean_test_data)
print(f"\n  Extracted data values: {data_values}")
print(f"  Value count: {len(data_values)}")

if len(data_values) > 0:
    print("\n[PASS] Flattening works! Gemini will receive flat field-value pairs.")
else:
    print("\n[FAIL] No data values extracted. Flattening may have failed.")
