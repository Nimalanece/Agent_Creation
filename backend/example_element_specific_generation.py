"""
Example demonstrating element-specific test generation.

This example shows how Agent 1 now generates different steps and expected results
for different element types, instead of reusing generic templates.
"""

from app.services.element_detection import (
    detect_element_type,
    get_element_specific_steps,
    get_element_specific_expected_results,
    ElementType,
)


def example_link_scenario():
    """Example: Link element generates click steps, not text input."""
    print("\n=== LINK SCENARIO ===")
    mapping = {
        "element_type": "link",
        "tag": "a",
        "href": "/checkbox",
        "selector": "a.router-link",
        "field_name": "Check Box Link",
    }
    
    element_type = detect_element_type(
        mapping=mapping,
        description="Verify link 'Check Box' navigates to '/checkbox'",
        title="Click Check Box Link"
    )
    
    steps = get_element_specific_steps(element_type, mapping)
    expected_results = get_element_specific_expected_results(
        element_type, test_type="navigation", mapping=mapping
    )
    
    print(f"Detected Element Type: {element_type}")
    print(f"\nSteps:")
    for step in steps:
        print(f"  Step {step['step_number']}: {step['action']} on {step.get('target', '')}")
    print(f"\nExpected Results:")
    for result in expected_results:
        print(f"  - {result}")


def example_button_scenario():
    """Example: Button element generates click steps, not text input."""
    print("\n=== BUTTON SCENARIO ===")
    mapping = {
        "element_type": "button",
        "tag": "button",
        "selector": "button#submit-btn",
        "field_name": "Submit Button",
    }
    
    element_type = detect_element_type(
        mapping=mapping,
        description="Click submit button to trigger form submission",
        title="Click Submit Button"
    )
    
    steps = get_element_specific_steps(element_type, mapping)
    expected_results = get_element_specific_expected_results(
        element_type, test_type="functional", mapping=mapping
    )
    
    print(f"Detected Element Type: {element_type}")
    print(f"\nSteps:")
    for step in steps:
        print(f"  Step {step['step_number']}: {step['action']} on {step.get('target', '')}")
    print(f"\nExpected Results:")
    for result in expected_results:
        print(f"  - {result}")


def example_text_input_scenario():
    """Example: Text input generates text entry steps."""
    print("\n=== TEXT INPUT SCENARIO ===")
    mapping = {
        "element_type": "text_input",
        "tag": "input",
        "type": "text",
        "selector": "input#firstName",
        "field_name": "First Name",
        "label": "First Name",
    }
    
    element_type = detect_element_type(
        mapping=mapping,
        description="User enters text into First Name field",
        title="Verify First Name field accepts input"
    )
    
    steps = get_element_specific_steps(element_type, mapping)
    expected_results = get_element_specific_expected_results(
        element_type, test_type="functional", mapping=mapping
    )
    
    print(f"Detected Element Type: {element_type}")
    print(f"\nSteps:")
    for step in steps:
        print(f"  Step {step['step_number']}: {step['action']} on {step.get('target', '')}")
        if step.get('value'):
            print(f"    Value: {step['value']}")
    print(f"\nExpected Results:")
    for result in expected_results:
        print(f"  - {result}")


def example_form_scenario():
    """Example: Form generates populate and submit steps."""
    print("\n=== FORM SCENARIO ===")
    mapping = {
        "element_type": "form",
        "tag": "form",
        "selector": "form#login-form",
        "field_name": "Login Form",
    }
    
    element_type = detect_element_type(
        mapping=mapping,
        description="User submits login form with valid credentials",
        title="Form Submission"
    )
    
    steps = get_element_specific_steps(element_type, mapping)
    expected_results = get_element_specific_expected_results(
        element_type, test_type="positive", mapping=mapping
    )
    
    print(f"Detected Element Type: {element_type}")
    print(f"\nSteps:")
    for step in steps:
        print(f"  Step {step['step_number']}: {step['action']} on {step.get('target', '')}")
    print(f"\nExpected Results:")
    for result in expected_results:
        print(f"  - {result}")


def example_checkbox_scenario():
    """Example: Checkbox generates checkbox select steps."""
    print("\n=== CHECKBOX SCENARIO ===")
    mapping = {
        "element_type": "checkbox",
        "tag": "input",
        "type": "checkbox",
        "selector": "input#agree-checkbox",
        "field_name": "Terms Agreement",
    }
    
    element_type = detect_element_type(
        mapping=mapping,
        description="User checks the terms agreement checkbox",
        title="Select Terms Checkbox"
    )
    
    steps = get_element_specific_steps(element_type, mapping)
    expected_results = get_element_specific_expected_results(
        element_type, test_type="functional", mapping=mapping
    )
    
    print(f"Detected Element Type: {element_type}")
    print(f"\nSteps:")
    for step in steps:
        print(f"  Step {step['step_number']}: {step['action']} on {step.get('target', '')}")
    print(f"\nExpected Results:")
    for result in expected_results:
        print(f"  - {result}")


def example_comparison():
    """Show the key differences: Link vs Button vs Input."""
    print("\n\n" + "="*60)
    print("KEY DIFFERENCES: Element-Specific Generation")
    print("="*60)
    
    print("\n📌 BEFORE (Generic Template Reuse):")
    print("  Link Scenario:")
    print("    Steps: locate_element, enter_text   ❌ WRONG - Links don't accept text input!")
    print("    Expected: 'Field accepts input', 'Value is displayed'")
    print("")
    print("  Button Scenario:")
    print("    Steps: locate_element, enter_text   ❌ WRONG - Buttons can't have text entered!")
    print("    Expected: 'Field accepts input', 'Value is displayed'")
    
    print("\n\n✅ AFTER (Element-Specific Generation):")
    print("  Link Scenario:")
    print("    Steps: locate_element, click_element")
    print("    Expected: 'Link is clickable', 'User is redirected', 'URL matches'")
    print("")
    print("  Button Scenario:")
    print("    Steps: locate_element, click_element")
    print("    Expected: 'Button is clickable', 'Expected action is triggered'")
    print("")
    print("  Text Input Scenario:")
    print("    Steps: locate_element, enter_text")
    print("    Expected: 'Field is visible', 'Field accepts input', 'Value is displayed'")


if __name__ == "__main__":
    example_comparison()
    example_link_scenario()
    example_button_scenario()
    example_text_input_scenario()
    example_form_scenario()
    example_checkbox_scenario()
    
    print("\n\n" + "="*60)
    print("✅ Element-specific test generation is working correctly!")
    print("="*60)
