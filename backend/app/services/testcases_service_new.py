from typing import Any, Dict, List


def _generate_expected_results_for_test_type_new(
    test_type: str = "functional",
    title: str = "",
    description: str = "",
    mapping: Dict[str, Any] = None,
    input_fields: List[str] = None,
) -> List[str]:
    """Generate scenario-specific expected results based on test intent and context.

    Args:
        test_type: The classification of the test (e.g., functional, positive, negative, navigation, security, validation, boundary).
        title: The test title or scenario name.
        description: The test description.
        mapping: Optional mapping context with field details.
        input_fields: Optional list of input field names involved in the test.

    Returns:
        List of specific, executable expected result assertions.
    """
    if mapping is None:
        mapping = {}
    else:
        mapping = dict(mapping)
    if input_fields is None:
        input_fields = []
    input_fields = [str(item).strip() for item in input_fields if str(item).strip()]

    test_type = str(test_type or "functional").strip().lower()
    title = str(title or "").strip().lower()
    description = str(description or "").strip().lower()
    field_name = str(
        mapping.get("field_name")
        or mapping.get("name")
        or mapping.get("label")
        or (input_fields[0] if input_fields else "Target field")
    ).strip()

    # Security Test (highest priority)
    if test_type == "security" or "xss" in description or "injection" in description:
        return [
            "Security validation is performed",
            "Malicious input is rejected",
            "Application remains secure",
        ]

    # Invalid Form Submission / Negative Test (check before positive)
    if test_type == "negative" or "invalid" in title or "negative" in title:
        return [
            "Submission is prevented",
            "Validation message is displayed",
            "Invalid fields are highlighted",
        ]

    # Valid Form Submission / Positive Test
    if test_type == "positive" or ("submit" in title and "invalid" not in title and "negative" not in title):
        return [
            f"{field_name} form submits successfully",
            "Success message is displayed",
            "No validation errors appear",
        ]

    # Navigation Scenario
    if test_type == "navigation" or "redirect" in title or "redirect" in description:
        return [
            "User is redirected to the target page",
            "URL contains expected path",
            "Target page loads successfully",
        ]

    # Link Validation Scenario
    if "link" in title or ("navigate" in description and "form" not in title):
        return [
            "Link is clickable",
            "Navigation occurs successfully",
            "URL matches expected destination",
        ]

    # Button Click Scenario (but not form submission)
    if ("button" in title or "click" in title) and "submit" not in title and "form" not in title:
        return [
            "Button is clickable",
            "Expected action is triggered",
            "State change is observable",
        ]

    # Input Field Scenario (must check before generic functional)
    if "input" in title or "field" in title or "text input" in description or "enter" in description:
        return [
            f"{field_name} is visible",
            f"{field_name} accepts user input",
            "Entered value is displayed correctly",
        ]

    # Validation Test
    if test_type == "validation" or "validation" in title or ("error" in description and "form" not in title):
        return [
            f"{field_name} validation check is performed",
            "Validation message is displayed",
            "User feedback indicates validation failure",
        ]

    # Boundary Test
    if test_type == "boundary" or "boundary" in title or "limit" in description or "length" in description:
        return [
            f"{field_name} boundary condition is tested",
            "Limit is enforced",
            "System behaves correctly at threshold",
        ]

    # Page Load Scenario (catch-all for functional type)
    if test_type == "functional" or "page load" in title or "page load" in description:
        return [
            "Page loads successfully",
            "Browser title equals expected title",
            "Primary content is visible",
        ]

    # Default fallback
    return ["Test condition is observable", "System responds as designed"]
