"""
Example: Selector-Aware, Automation-Ready Step Generation

This example demonstrates Agent 1 enhancement where every generated step includes
complete locator metadata for Selenium automation readiness.

BEFORE (Generic):
{
  "step_number": 2,
  "action": "click_element",
  "target": "navigation_link"
}

AFTER (Selector-Aware):
{
  "step_number": 2,
  "action": "click_element",
  "element_name": "Select Menu",
  "selector": "a[href='/select-menu']",
  "locator_type": "css_selector",
  "locator_value": "a[href='/select-menu']"
}

Key Benefits:
1. Downstream agents (Agent 2, Agent 3) don't need to guess which element to interact with
2. Selenium automation can directly map actions to commands
3. Every element has a friendly name AND precise locator information
4. Expected results include explicit element names and expected values
"""

from app.services.element_detection import (
    get_element_specific_steps,
    get_element_specific_expected_results,
    ElementType,
)

def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")


def example_link_scenario():
    """Example: Navigation Link with selector awareness."""
    print_section("EXAMPLE 1: Navigation Link")
    
    mapping = {
        "label": "Select Menu",
        "selector": "a[href='/select-menu']",
        "href": "/select-menu",
        "element_type": "link",
        "tag": "a",
    }
    
    print("\nMapping (from page analysis):")
    print(f"  Element Name: {mapping['label']}")
    print(f"  Selector: {mapping['selector']}")
    print(f"  Element Type: {mapping['element_type']}")
    print(f"  Expected URL: {mapping['href']}")
    
    # Generate steps
    steps = get_element_specific_steps(ElementType.LINK, mapping)
    print("\nGenerated Steps (with Locator Metadata):")
    for step in steps:
        print(f"\n  Step {step['step_number']}: {step['action']}")
        print(f"    element_name: {step.get('element_name', 'N/A')}")
        print(f"    selector: {step.get('selector', 'N/A')}")
        print(f"    locator_type: {step.get('locator_type', 'N/A')}")
        print(f"    locator_value: {step.get('locator_value', 'N/A')}")
    
    # Generate expected results
    results = get_element_specific_expected_results(
        ElementType.LINK, "navigation", mapping, "Verify Select Menu link navigates"
    )
    print("\nExpected Results (with Explicit Values):")
    for result in results:
        print(f"  ✓ {result}")
    
    print("\n✅ Agent 3 can now directly use these locators to generate Selenium code:")
    print("   - No guessing required")
    print("   - Direct mapping to WebDriver.find_element() calls")
    print("   - Explicit assertions with element names")


def example_button_scenario():
    """Example: Button click with selector awareness."""
    print_section("EXAMPLE 2: Submit Button")
    
    mapping = {
        "label": "Submit Button",
        "id": "submit",
        "selector": "#submit",
        "element_type": "button",
        "tag": "button",
    }
    
    print("\nMapping (from page analysis):")
    print(f"  Element Name: {mapping['label']}")
    print(f"  Element ID: {mapping['id']}")
    print(f"  Selector: {mapping['selector']}")
    
    # Generate steps
    steps = get_element_specific_steps(ElementType.BUTTON, mapping)
    print("\nGenerated Steps:")
    for step in steps:
        print(f"\n  Step {step['step_number']}: {step['action']}")
        if 'element_name' in step:
            print(f"    element_name: '{step['element_name']}'")
        if 'locator_type' in step:
            print(f"    locator_type: {step['locator_type']}")
            print(f"    locator_value: {step['locator_value']}")
    
    # Generate expected results
    results = get_element_specific_expected_results(
        ElementType.BUTTON, "functional", mapping, "Click Submit button"
    )
    print("\nExpected Results:")
    for result in results:
        print(f"  ✓ {result}")
    
    print("\n✅ Selenium code generation becomes trivial:")
    print("   WebDriver.find_element('id', 'submit').click()")


def example_input_field_scenario():
    """Example: Text input field with selector awareness."""
    print_section("EXAMPLE 3: Text Input Field")
    
    mapping = {
        "label": "First Name",
        "field_name": "First Name",
        "id": "firstName",
        "selector": "input#firstName",
        "type": "text",
        "element_type": "text_input",
        "tag": "input",
        "placeholder": "Enter your first name",
    }
    
    print("\nMapping (from page analysis):")
    print(f"  Element Name: {mapping['label']}")
    print(f"  Element ID: {mapping['id']}")
    print(f"  Field Type: {mapping['type']}")
    print(f"  Placeholder: {mapping['placeholder']}")
    
    # Generate steps
    steps = get_element_specific_steps(ElementType.TEXT_INPUT, mapping)
    print("\nGenerated Steps:")
    for step in steps:
        print(f"\n  Step {step['step_number']}: {step['action']}")
        print(f"    element_name: '{step.get('element_name', 'N/A')}'")
        print(f"    locator_type: {step.get('locator_type', 'N/A')}")
        print(f"    locator_value: {step.get('locator_value', 'N/A')}")
        if 'value' in step:
            print(f"    value: '{step['value']}'")
    
    # Generate expected results
    results = get_element_specific_expected_results(
        ElementType.TEXT_INPUT, "positive", mapping, "Enter first name"
    )
    print("\nExpected Results:")
    for result in results:
        print(f"  ✓ {result}")


def example_checkbox_scenario():
    """Example: Checkbox with selector awareness."""
    print_section("EXAMPLE 4: Checkbox")
    
    mapping = {
        "label": "Sports",
        "id": "hobbies-checkbox-1",
        "selector": "#hobbies-checkbox-1",
        "element_type": "checkbox",
        "tag": "input",
        "type": "checkbox",
    }
    
    print("\nMapping (from page analysis):")
    print(f"  Element Name: {mapping['label']}")
    print(f"  Element ID: {mapping['id']}")
    print(f"  Selector: {mapping['selector']}")
    
    # Generate steps
    steps = get_element_specific_steps(ElementType.CHECKBOX, mapping)
    print("\nGenerated Steps:")
    for step in steps:
        print(f"\n  Step {step['step_number']}: {step['action']}")
        print(f"    element_name: '{step.get('element_name', 'N/A')}'")
        print(f"    locator_type: {step.get('locator_type', 'N/A')}")
        print(f"    locator_value: {step.get('locator_value', 'N/A')}")
    
    # Generate expected results
    results = get_element_specific_expected_results(
        ElementType.CHECKBOX, "functional", mapping, "Select Sports checkbox"
    )
    print("\nExpected Results:")
    for result in results:
        print(f"  ✓ {result}")


def example_dropdown_scenario():
    """Example: Dropdown select with selector awareness."""
    print_section("EXAMPLE 5: Dropdown Selection")
    
    mapping = {
        "label": "Country",
        "selector": "select#country",
        "element_type": "dropdown",
        "tag": "select",
        "field_name": "Country",
    }
    
    print("\nMapping (from page analysis):")
    print(f"  Element Name: {mapping['label']}")
    print(f"  Selector: {mapping['selector']}")
    print(f"  Element Type: {mapping['element_type']}")
    
    # Generate steps
    steps = get_element_specific_steps(ElementType.DROPDOWN, mapping)
    print("\nGenerated Steps:")
    for step in steps:
        print(f"\n  Step {step['step_number']}: {step['action']}")
        print(f"    element_name: '{step.get('element_name', 'N/A')}'")
        print(f"    locator_type: {step.get('locator_type', 'N/A')}")
        print(f"    locator_value: {step.get('locator_value', 'N/A')}")
        if 'value' in step:
            print(f"    value: {step['value']}")
    
    # Generate expected results
    results = get_element_specific_expected_results(
        ElementType.DROPDOWN, "positive", mapping, "Select country option"
    )
    print("\nExpected Results:")
    for result in results:
        print(f"  ✓ {result}")


def example_file_upload_scenario():
    """Example: File upload with selector awareness."""
    print_section("EXAMPLE 6: File Upload")
    
    mapping = {
        "label": "Upload Picture",
        "id": "uploadPicture",
        "selector": "#uploadPicture",
        "element_type": "file_upload",
        "tag": "input",
        "type": "file",
    }
    
    print("\nMapping (from page analysis):")
    print(f"  Element Name: {mapping['label']}")
    print(f"  Element ID: {mapping['id']}")
    print(f"  Selector: {mapping['selector']}")
    
    # Generate steps
    steps = get_element_specific_steps(ElementType.FILE_UPLOAD, mapping)
    print("\nGenerated Steps:")
    for step in steps:
        print(f"\n  Step {step['step_number']}: {step['action']}")
        print(f"    element_name: '{step.get('element_name', 'N/A')}'")
        print(f"    locator_type: {step.get('locator_type', 'N/A')}")
        print(f"    locator_value: {step.get('locator_value', 'N/A')}")
        if 'value' in step:
            print(f"    value: {step['value']}")
    
    # Generate expected results
    results = get_element_specific_expected_results(
        ElementType.FILE_UPLOAD, "positive", mapping, "Upload profile picture"
    )
    print("\nExpected Results:")
    for result in results:
        print(f"  ✓ {result}")


def main():
    """Run all examples."""
    print("\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*78 + "║")
    print("║  Agent 1 Selector-Aware, Automation-Ready Step Generation" + " "*23 + "║")
    print("║" + " "*78 + "║")
    print("╚" + "="*78 + "╝")
    
    print("\nThis demonstration shows how Agent 1 now generates automation-ready steps")
    print("with complete locator metadata, enabling downstream agents to directly")
    print("generate Selenium code without guessing or inferring element information.")
    
    example_link_scenario()
    example_button_scenario()
    example_input_field_scenario()
    example_checkbox_scenario()
    example_dropdown_scenario()
    example_file_upload_scenario()
    
    print_section("SUMMARY")
    print("\n✅ All Element Types Supported:")
    print("  • Links (navigation)")
    print("  • Buttons (actions)")
    print("  • Text/Email/Password/Phone/Number/Date/Search/URL Inputs")
    print("  • Textareas")
    print("  • Checkboxes")
    print("  • Radio Buttons")
    print("  • Dropdowns/Select Elements")
    print("  • File Uploads")
    print("  • Forms")
    print("  • Page Load Events")
    
    print("\n✅ Every Step Includes:")
    print("  • element_name: Friendly human-readable name")
    print("  • selector: CSS selector or locator expression")
    print("  • locator_type: id, css_selector, xpath, class, name, etc.")
    print("  • locator_value: Raw locator value for direct Selenium use")
    
    print("\n✅ Every Expected Result:")
    print("  • Includes explicit element names (e.g., 'First Name', 'Submit')")
    print("  • Includes expected values (e.g., '/select-menu', 'success')")
    print("  • Is specific to test_type (functional, positive, negative, etc.)")
    print("  • Is specific to element_type (link, button, input, etc.)")
    
    print("\n✅ Benefits for Downstream Agents:")
    print("  • Agent 2 (Data Generator): Gets clear field names and types")
    print("  • Agent 3 (Selenium Generator): Gets complete locator metadata")
    print("  • No guessing, inference, or additional analysis needed")
    print("  • Direct mapping to WebDriver commands")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    main()
