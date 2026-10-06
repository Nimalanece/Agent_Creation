"""
Diagnostic tool to identify which metadata validation is failing
"""
import sys
import pathlib
import json
from typing import Any, Dict

root = pathlib.Path(r'c:/Users/2000189345/Documents/agent creation/backend')
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from app.core.gemini_service import GeminiService

def diagnose_validation(test_case: Dict[str, Any], test_data: Dict[str, Any], url: str = None) -> None:
    """Run validation and show which specific checks fail"""
    errors = GeminiService.validate_generation_inputs(test_case, test_data, url)
    
    print("[DIAGNOSTIC] Metadata Validation Results")
    print("=" * 60)
    
    if errors:
        print(f"Status: FAILED ({len(errors)} error(s))")
        print("\nErrors:")
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")
    else:
        print("Status: PASSED")
        print("All metadata validation checks passed!")
    
    print("\nInput Summary:")
    print(f"  test_case keys: {list(test_case.keys()) if isinstance(test_case, dict) else 'Not a dict'}")
    print(f"  test_case type: {type(test_case).__name__}")
    print(f"  test_data keys: {list(test_data.keys()) if isinstance(test_data, dict) else 'Not a dict'}")
    print(f"  application_url: {url or test_case.get('application_url') if isinstance(test_case, dict) else 'N/A'}")
    
    if isinstance(test_case, dict):
        print(f"\n  test_case['test_steps'] count: {len(test_case.get('test_steps') or [])}")
        print(f"  test_case['expected_results']: {test_case.get('expected_results')}")
        print(f"  test_case['expected_result']: {test_case.get('expected_result')}")
        print(f"  test_case['required_data'] count: {len(test_case.get('required_data') or [])}")
        print(f"  test_case['application_url']: {test_case.get('application_url')}")
    
    if isinstance(test_data, dict):
        data_values = GeminiService._supplied_data_values(test_data)
        print(f"\n  test_data values count: {len(data_values)}")
        print(f"  test_data['requires_test_data']: {test_data.get('requires_test_data')}")

if __name__ == "__main__":
    # Example: test with minimal valid data
    example_test_case = {
        "test_case_id": "TC001",
        "title": "Test Login",
        "priority": "high",
        "application_url": "https://example.com",
        "test_steps": [
            {
                "action": "click_element",
                "element_name": "Username Field",
                "locator_type": "id",
                "locator_value": "username",
                "locator_status": "available"
            }
        ],
        "expected_results": ["Element is visible"],
    }
    
    example_test_data = {
        "username": "testuser@example.com",
    }
    
    print("Example 1: Minimal Valid Data")
    print("-" * 60)
    diagnose_validation(example_test_case, example_test_data)
    
    print("\n\n")
    
    # Example 2: Missing required fields
    incomplete_case = {
        "test_case_id": "TC002",
        "title": "Test Without URL",
        "priority": "high",
        # Missing application_url
        "test_steps": [
            {
                "action": "click_element",
                "element_name": "Button",
                # Missing locator_type and locator_value
            }
        ],
        # Missing expected_results
    }
    
    print("Example 2: Missing Required Fields")
    print("-" * 60)
    diagnose_validation(incomplete_case, {})
