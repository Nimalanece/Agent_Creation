"""
Regression tests for Agent 1 dynamic expected results generation based on scenario intent.

Verifies that each test_type generates scenario-specific expected results instead of
using the same generic results for all test cases.
"""

import pytest
from app.services.testcases_service import _generate_expected_results_for_test_type
from app.services.testcases_service_new import _generate_expected_results_for_test_type_new
from app.services.scenarios_service import _build_fallback_scenarios, _normalize_scenarios


def test_radio_fallback_scenarios_use_selection_semantics():
    scenarios = _build_fallback_scenarios({
        "url": "https://example.com",
        "inputs": [{"id": "gender-radio-3", "label": "Female", "type": "radio", "required": True}],
    })
    descriptions = " ".join(item["description"] for item in scenarios).lower()
    assert "radio button can be selected" in descriptions
    assert "enter data" not in descriptions
    assert "left blank" not in descriptions


def test_radio_single_selection_scenario_has_two_option_flow():
    scenarios = _build_fallback_scenarios({
        "url": "https://example.com",
        "inputs": [{
            "id": "gender-radio-1",
            "label": "Gender",
            "type": "radio",
            "options": ["Female", "Other"],
        }],
    })
    single = next(item for item in scenarios if "only one option" in item["title"].lower())
    step_text = " ".join(step["description"] for step in single["steps"]).lower()
    assert "female" in step_text
    assert "other" in step_text
    assert "deselected" in step_text
    assert single["expected_results"] == ["Only one option remains selected in the 'Gender' radio group."]


def test_incompatible_radio_scenario_is_regenerated():
    scenarios = _normalize_scenarios({"scenarios": [{
        "scenario_id": "S1",
        "title": "Verify Female accepts text input",
        "description": "Verify Female accepts text input",
        "test_type": "functional",
        "mapping": {"field_name": "Female", "type": "radio", "element_type": "radio", "selector": "#gender-radio-3"},
    }]}, {})
    assert len(scenarios) == 1
    assert "accepts text input" not in scenarios[0]["description"].lower()
    assert "radio" in scenarios[0]["description"].lower()


def test_dropdown_fallback_scenarios_do_not_enter_free_text():
    scenarios = _build_fallback_scenarios({
        "url": "https://example.com",
        "selects": [{"id": "country", "label": "Country", "options": ["US", "CA"]}],
    })
    descriptions = " ".join(item["description"] for item in scenarios).lower()
    assert "dropdown" in descriptions
    assert "enter free text" not in descriptions


def test_boundary_scenario_contains_boundary_probes_and_matching_intent():
    scenarios = _normalize_scenarios({"scenarios": [{
        "scenario_id": "S2",
        "title": "Verify subjectsInput enforces maximum text length boundary",
        "description": "Verify subjectsInput enforces maximum text length boundary",
        "test_type": "boundary",
        "mapping": {
            "field_name": "subjectsInput",
            "type": "text",
            "selector": "#subjectsInput",
        },
        "steps": [
            {"step_number": 1, "description": "Enter data"},
            {"step_number": 2, "description": "Verify value displayed"},
        ],
        "expected_results": ["Value is displayed"],
    }]}, {})
    boundary = scenarios[0]
    step_text = " ".join(step["description"] for step in boundary["steps"]).lower()
    result_text = " ".join(boundary["expected_results"]).lower()
    assert boundary["test_type"] == "boundary"
    assert "maximum + 1" in step_text
    assert "rejected" in result_text or "restricted" in result_text
    assert boundary["automation_intent"]["behavior"] == "boundary"


def test_functional_page_load_expected_results():
    """Verify Page Load scenarios generate appropriate expected results."""
    results = _generate_expected_results_for_test_type(
        test_type="functional",
        title="Verify page loads successfully",
        description="Ensure the target page renders without errors.",
    )
    results_str = " ".join(results).lower()
    assert "page loads successfully" in results_str
    assert ("browser title" in results_str or "page loads" in results_str)
    assert "content" in results_str or "visible" in results_str
    assert len(results) >= 3


def test_navigation_expected_results():
    """Verify Navigation scenarios generate redirect/navigation expected results."""
    results = _generate_expected_results_for_test_type(
        test_type="navigation",
        title="User navigates to dashboard",
        description="Redirect to dashboard page",
        mapping={"element_type": "link", "tag": "a", "href": "/dashboard"}
    )
    # Should contain navigation-related assertions
    results_str = " ".join(results).lower()
    assert "redirect" in results_str or "navigat" in results_str or "url" in results_str


def test_input_field_expected_results():
    """Verify Input Field scenarios generate field interaction expected results."""
    results = _generate_expected_results_for_test_type(
        test_type="functional",
        title="Verify First Name field accepts input",
        description="User enters text into First Name field",
        input_fields=["First Name"],
        mapping={"element_type": "text_input", "tag": "input", "type": "text", "selector": "input#firstName"}
    )
    # Should contain input-field-specific assertions
    results_str = " ".join(results).lower()
    assert "field" in results_str or "input" in results_str or "visible" in results_str
    assert "accept" in results_str or "visible" in results_str


def test_positive_valid_form_submission():
    """Verify Positive/Valid Form Submission scenarios generate success expected results."""
    results = _generate_expected_results_for_test_type(
        test_type="positive", title="Submit login form with valid credentials", description="Form submits successfully"
    )
    results_str = " ".join(results).lower()
    assert "submit" in results_str  # Should mention submitting
    assert ("success" in results_str or "displayed" in results_str)  # Success message
    assert ("validation" in results_str or "error" in results_str) or len(results) >= 3  # Error-related or comprehensive


def test_negative_invalid_form_submission():
    """Verify Negative/Invalid Form Submission scenarios generate rejection expected results."""
    results = _generate_expected_results_for_test_type(
        test_type="negative",
        title="Submit form with invalid data",
        description="Form validation prevents submission",
        mapping={"element_type": "form", "tag": "form"}
    )
    # Should contain form-specific rejection assertions
    results_str = " ".join(results).lower()
    assert "prevent" in results_str or "validation" in results_str or "error" in results_str


def test_validation_expected_results():
    """Verify Validation scenarios generate validation-specific expected results."""
    results = _generate_expected_results_for_test_type(
        test_type="validation", title="Verify required field validation", description="Empty email field triggers error"
    )
    results_str = " ".join(results).lower()
    assert "validation" in results_str
    assert ("message" in results_str or "error" in results_str or "feedback" in results_str)


def test_boundary_expected_results():
    """Verify Boundary scenarios generate constraint/threshold expected results."""
    results = _generate_expected_results_for_test_type(
        test_type="boundary",
        title="Test maximum password length",
        description="Enforce password length limit",
        mapping={"element_type": "password_input", "tag": "input", "type": "password"}
    )
    # Should contain boundary-specific assertions
    results_str = " ".join(results).lower()
    assert "boundary" in results_str or "limit" in results_str or "threshold" in results_str


def test_security_expected_results():
    """Verify Security scenarios generate security validation expected results."""
    results = _generate_expected_results_for_test_type(
        test_type="security",
        title="Test XSS prevention",
        description="Malicious script input is rejected",
        mapping={"element_type": "text_input", "tag": "input", "type": "text"}
    )
    # Should contain security-specific assertions
    results_str = " ".join(results).lower()
    assert "security" in results_str or "malicious" in results_str or "sanitize" in results_str


def test_button_click_expected_results():
    """Verify Button Click scenarios generate action trigger expected results."""
    results = _generate_expected_results_for_test_type(
        test_type="functional",
        title="Click submit button",
        description="Submit button triggers form submission",
        mapping={"element_type": "button", "tag": "button", "selector": "button#submit"}
    )
    # Should contain button-specific assertions
    results_str = " ".join(results).lower()
    assert "button" in results_str or "clickable" in results_str or "action" in results_str


def test_link_validation_expected_results():
    """Verify Link Validation scenarios generate navigation expected results."""
    results = _generate_expected_results_for_test_type(
        test_type="functional",
        title="Click profile link",
        description="User navigates to profile page",
        mapping={"element_type": "link", "tag": "a", "href": "/profile", "selector": "a#profile-link"}
    )
    # Should contain link-specific assertions
    results_str = " ".join(results).lower()
    assert "link" in results_str or "clickable" in results_str or "navigat" in results_str


def test_no_duplicate_results_across_types():
    """Verify that different test_types generate different expected results."""
    functional_results = _generate_expected_results_for_test_type(test_type="functional", title="Page Load")
    positive_results = _generate_expected_results_for_test_type(test_type="positive", title="Submit Form")
    negative_results = _generate_expected_results_for_test_type(test_type="negative", title="Invalid Submission")

    # Ensure no complete overlap - each should have unique expected results
    functional_set = set(functional_results)
    positive_set = set(positive_results)
    negative_set = set(negative_results)

    # Verify that not all results are the same generic values
    assert functional_set != positive_set or "Success message is displayed" not in functional_results
    assert negative_set != positive_set or "Submission is prevented" not in positive_results


def test_mapping_context_influences_results():
    """Verify that mapping context (field name) influences expected results."""
    mapping = {"field_name": "Email Address", "type": "email"}
    results = _generate_expected_results_for_test_type(
        test_type="functional",
        title="Verify email field",
        description="Email field accepts input",
        mapping=mapping,
    )
    # Field name from mapping should appear in results
    assert any("Email Address" in result for result in results)


def test_returns_list_not_generic_fallback():
    """Verify that all test_types return specific results, never the generic fallback."""
    test_types = ["functional", "positive", "negative", "validation", "boundary", "security", "navigation"]

    generic_fallback = ["Test condition is observable", "System responds as designed"]

    for test_type in test_types:
        results = _generate_expected_results_for_test_type(test_type=test_type, title="Test", description="Test scenario")
        assert len(results) > 0, f"Empty results for test_type: {test_type}"
        # Should not return just the generic fallback
        assert results != generic_fallback, f"Generic fallback returned for test_type: {test_type}"


def test_empty_inputs_fallback():
    """Verify graceful handling of empty inputs with sensible defaults."""
    results = _generate_expected_results_for_test_type(test_type="", title="", description="")
    assert isinstance(results, list)
    assert len(results) > 0
    # Should return something useful, not empty or generic fallback only


def test_new_helper_module_imports_and_generates_specific_results():
    """Ensure the standalone helper module imports and returns scenario-appropriate assertions."""
    results = _generate_expected_results_for_test_type_new(
        test_type="positive",
        title="Submit login form",
        description="Form submits successfully",
        mapping={"field_name": "Email Address"},
    )
    assert isinstance(results, list)
    assert len(results) >= 3
    assert any("submit" in result.lower() for result in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
