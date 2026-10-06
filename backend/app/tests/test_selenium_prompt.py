import ast
import asyncio
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

import app.core.gemini_service as gemini_service
from app.core.gemini_service import GeminiService, GeminiServiceError
from app.models.schemas import Agent1PipelineResponse


PROMPT_DIR = Path(__file__).resolve().parents[2] / "app" / "prompts"


def render_prompt() -> str:
    environment = Environment(loader=FileSystemLoader(str(PROMPT_DIR)))
    return environment.get_template("generate_selenium.j2").render(
        test_case={},
        test_data={},
    )


def test_agent3_data_handoff_survives_full_analysis_response_model():
    payload = {
        "analysis": {"title": "Demo"},
        "application_url": "https://example.com",
        "page_title": "Example",
        "scenarios": [],
        "testcases": [],
        "discovered_locators": {},
        "agent_1_contract": {"application_name": "Example", "url": "https://example.com", "application_url": "https://example.com", "features": [], "feature_groups": [], "test_cases": [], "page_metadata": {"forms": [], "buttons": [], "fields": [], "dropdowns": [], "checkboxes": [], "links": []}, "agent_2_input": {"application_name": "Example", "url": "https://example.com", "test_cases": []}, "agent_3_input": {"application_name": "Example", "url": "https://example.com", "features": [], "test_scenarios": [], "test_cases": []}},
        "agent_2_contract": {"application_name": "Example", "url": "https://example.com", "positive_data": [], "negative_data": [], "boundary_data": [], "validation_data": []},
        "agent_3_test_data": {
            "scenario_id": "S1",
            "requires_test_data": True,
            "generated_data": {"positive": {"Email": ["john@example.com"]}},
        },
    }

    validated = Agent1PipelineResponse.model_validate(payload)
    assert validated.agent_3_test_data is not None
    assert validated.agent_3_test_data["generated_data"]["positive"]["Email"] == ["john@example.com"]


def test_selenium_prompt_requires_overlay_safe_clicks():
    prompt = render_prompt()

    required_fragments = (
        "scrollIntoView({block:'center'})",
        "element_to_be_clickable(locator)",
        "Attempt element.click() normally first",
        "ElementClickInterceptedException",
        "ElementNotInteractableException",
        'driver.execute_script("arguments[0].click();", element)',
        "DemoQA",
    )

    for fragment in required_fragments:
        assert fragment in prompt


def test_selenium_prompt_requires_defined_driver_fixture():
    prompt = render_prompt()

    assert "list every fixture name used" in prompt
    assert "@pytest.fixture def driver()" in prompt
    assert "driver = webdriver.Chrome()" in prompt
    assert "driver.quit()" in prompt
    assert "Do not use Playwright fixtures" in prompt


def test_generated_selenium_code_rejects_undefined_fixture():
    code = """import pytest
from selenium import webdriver

def test_page(driver):
    assert driver.title
"""

    with pytest.raises(GeminiServiceError, match="undefined pytest fixtures"):
        GeminiService._validate_code(code, {}, {}, enforce_fixtures=True)


def test_generated_selenium_code_accepts_complete_driver_fixture():
    code = """import pytest
from selenium import webdriver

@pytest.fixture
def driver():
    driver = webdriver.Chrome()
    try:
        yield driver
    finally:
        driver.quit()

def test_page(driver):
    assert driver.title
"""

    assert GeminiService._validate_code(code, {}, {}, enforce_fixtures=True) == code.strip()


def test_selenium_prompt_rejects_labels_and_generic_data():
    prompt = render_prompt()

    assert '"State and City"' in prompt
    assert '"First Name"' in prompt
    assert '"john@test.com"' in prompt
    assert '"sample"' in prompt
    assert 'ERROR: Missing or invalid metadata from Agent 1 or Agent 2.' in prompt


def test_selenium_prompt_enforces_exact_output_contract():
    prompt = render_prompt()

    assert 'Return executable Python code only.' in prompt
    assert 'Do not return markdown blocks.' in prompt
    assert 'Do not return JSON.' in prompt
    assert 'Do not return explanations.' in prompt
    assert 'The service has already validated and canonicalized the supplied locator metadata.' in prompt
    assert 'ERROR: Invalid locator metadata received from Agent 1.' not in prompt


def test_selenium_prompt_enforces_traceability_and_application_assertions():
    prompt = render_prompt()

    required_fragments = (
        "Every generated locator, action, and assertion must trace directly",
        "An input mapping is never a submit-button mapping",
        "Never place HTML anchors, labels, or markup inside a URL",
        "hidden radio or checkbox inputs",
        "validationMessage",
        "self-fulfilling assertions such as `assert True`",
        "every action maps to a declared step",
    )
    for fragment in required_fragments:
        assert fragment in prompt


def test_selenium_prompt_requires_coverage_matrix_before_generation():
    prompt = render_prompt()

    required_fragments = (
        "Coverage analysis is mandatory before code generation",
        "Scenario Title, Test Type, Steps, Expected Results, and Mapping",
        "scenario step -> Selenium action",
        "expected result -> assertion",
        "every scenario step has a matching Selenium action",
        "every expected result has at least one meaningful assertion",
        "Final coverage gate",
    )
    for fragment in required_fragments:
        assert fragment in prompt


def test_selenium_prompt_requires_100_percent_self_review_coverage():
    prompt = render_prompt()

    required_fragments = (
        "Self-review is mandatory before returning code",
        "step coverage as covered steps divided by total steps",
        "assertion coverage as covered expected results divided by total expected results",
        "Both must equal 100%",
        "step coverage = 100%",
        "assertion coverage = 100%",
        "Otherwise regenerate automatically",
    )
    for fragment in required_fragments:
        assert fragment in prompt


def test_validate_code_ignores_application_url_setup_metadata_as_locator():
    test_case = {
        "application_url": "https://example.com",
        "steps": [
            {"action": "click_element", "locator_type": "id", "locator_value": "submit"},
            {"action": "open_url", "locator_type": "", "locator_value": "application_url"},
        ],
        "expected_results": ["Submit is clickable"],
    }
    code = """from selenium.webdriver.common.by import By

def test_submit(driver):
    button = driver.find_element(By.ID, "submit")
    button.click()
    assert button.is_displayed()
"""

    assert GeminiService._validate_code(code, test_case, {}) == code.strip()


def test_selenium_prompt_requires_production_traceability_contract():
    prompt = render_prompt()

    required_fragments = (
        "preconditions and generated test data",
        "Every generated line must contribute directly",
        "Relevance filter",
        "lastName",
        "Field-type rules",
        "radio tests may verify visibility",
        "checkbox tests must cover both selection and deselection",
        "dropdown tests must select and verify",
        "Final quality gate",
        "Mapping Metadata",
        "Executable Selenium pytest syntax",
    )
    for fragment in required_fragments:
        assert fragment in prompt


def test_selenium_prompt_requires_same_page_locators():
    prompt = render_prompt()

    assert "Page consistency is mandatory" in prompt
    assert "Every locator must belong to the same page" in prompt
    assert "firstName" in prompt
    assert "Broken Links - Images" in prompt


def test_selenium_prompt_requires_navigation_evidence_for_url_assertions():
    prompt = render_prompt()

    required_fragments = (
        "Navigation evidence gate",
        "If navigation cannot be proven",
        "generic selector such as `a.router-link`",
        "plain raw URL string",
    )
    for fragment in required_fragments:
        assert fragment in prompt


def test_unproven_navigation_does_not_block_url_assertions():
    test_case = {
        "title": "Verify the menu control updates the page",
        "test_type": "navigation",
        "steps": [
            {
                "action": "click_element",
                "locator_type": "id",
                "locator_value": "menuButton",
            },
            {
                "action": "verify_element_visible",
                "description": "Verify the menu panel is visible",
                "locator_type": "id",
                "locator_value": "menuPanel",
            },
        ],
        "expected_results": ["Menu panel is displayed"],
    }
    code = """
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(menu_locator))
    driver.find_element(By.ID, "menuButton").click()
    WebDriverWait(driver, 10).until(EC.url_contains("/menu"))
    assert "/menu" in driver.current_url
    """

    assert GeminiService._scenario_code_alignment_error(code, test_case) is None


def test_navigation_url_field_proves_destination():
    test_case = {
        "title": "Verify link navigates to dashboard",
        "test_type": "navigation",
        "steps": [{
            "action": "click_element",
            "locator_type": "css_selector",
            "locator_value": "a[href='/dashboard']",
        }],
        "mapping": {"url": "/dashboard"},
        "expected_results": ["URL contains /dashboard"],
    }

    assert GeminiService._navigation_url_evidence(test_case) == ["/dashboard"]


def test_unproven_navigation_accepts_supplied_ui_state_validation():
    test_case = {
        "title": "Verify the menu control updates the page",
        "test_type": "navigation",
        "steps": [
            {
                "action": "click_element",
                "locator_type": "id",
                "locator_value": "menuButton",
            },
            {
                "action": "verify_element_visible",
                "description": "Verify the menu panel is visible",
                "locator_type": "id",
                "locator_value": "menuPanel",
            },
        ],
        "expected_results": ["Menu panel is displayed"],
        "mapping": {"destination_id": "menuPanel"},
    }
    code = """
    menu_locator = (By.ID, "menuButton")
    WebDriverWait(driver, 10).until(EC.visibility_of_element_located(menu_locator))
    assert driver.find_element(By.ID, "menuButton").is_displayed()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(menu_locator))
    driver.find_element(By.ID, "menuButton").click()
    panel = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, "menuPanel"))
    )
    assert panel.is_displayed()
    """

    assert GeminiService._scenario_code_alignment_error(code, test_case) is None


def test_navigation_with_href_requires_href_based_locator():
    test_case = {
        "title": "Verify link navigation",
        "test_type": "navigation",
        "mapping": {"href": "/resizable", "destination_id": "resizableHeading"},
        "steps": [{
            "action": "click_element",
            "locator_type": "css_selector",
            "locator_value": "a.router-link",
        }],
        "expected_results": ["URL changes to /resizable", "Destination page loads"],
    }
    code = """
    link = driver.find_element(By.CSS_SELECTOR, "a.router-link")
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.router-link")))
    link.click()
    WebDriverWait(driver, 10).until(EC.url_contains("/resizable"))
    assert "/resizable" in driver.current_url
    heading = driver.find_element(By.ID, "resizableHeading")
    assert heading.is_displayed()
    """

    error = GeminiService._scenario_code_alignment_error(code, test_case)

    assert error and any(
        message in error
        for message in ("generic anchor locator", "href-based locator")
    )


def test_proven_navigation_requires_destination_page_locator():
    test_case = {
        "title": "Verify link navigation",
        "test_type": "navigation",
        "mapping": {"href": "/resizable"},
        "steps": [{
            "action": "click_element",
            "locator_type": "css_selector",
            "locator_value": "a[href='/resizable']",
        }],
        "expected_results": ["URL changes to /resizable"],
    }
    code = """
    link = driver.find_element(By.CSS_SELECTOR, "a[href='/resizable']")
    link.click()
    WebDriverWait(driver, 10).until(EC.url_contains("/resizable"))
    assert "/resizable" in driver.current_url
    """

    error = GeminiService._scenario_code_alignment_error(code, test_case)

    assert error and "destination page locator is required" in error


def test_navigation_rejects_reusing_original_link_as_destination_check():
    test_case = {
        "title": "Verify link navigation",
        "test_type": "navigation",
        "mapping": {"href": "/webtables", "destination_locator": {
            "locator_type": "css_selector",
            "locator_value": "a[href='/webtables']",
        }},
        "steps": [{
            "action": "click_element",
            "locator_type": "css_selector",
            "locator_value": "a[href='/webtables']",
        }],
        "expected_results": ["URL changes to /webtables", "Destination page loads"],
    }
    code = """
    link = driver.find_element(By.CSS_SELECTOR, "a[href='/webtables']")
    assert link.is_displayed()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='/webtables']")))
    link.click()
    WebDriverWait(driver, 10).until(EC.url_contains("/webtables"))
    assert "/webtables" in driver.current_url
    assert link.is_displayed()
    """

    error = GeminiService._scenario_code_alignment_error(code, test_case)

    assert error and "original navigation link" in error


def test_generation_metadata_rejects_locator_page_mismatch():
    test_case = {
        "application_url": "https://demoqa.com/broken",
        "steps": [{
            "action": "click_element",
            "element_name": "Broken Links - Images",
            "locator_type": "id",
            "locator_value": "firstName",
            "page_url": "/automation-practice-form",
        }],
        "expected_results": ["Broken Links - Images is clickable"],
        "mapping": {
            "page_url": "/automation-practice-form",
            "id": "firstName",
        },
    }

    errors = GeminiService.validate_generation_inputs(test_case, {"requires_test_data": False}, None)

    assert any("Page consistency failure" in error for error in errors)


def test_generation_metadata_accepts_locator_on_opened_page():
    test_case = {
        "application_url": "https://demoqa.com/automation-practice-form",
        "steps": [{
            "action": "enter_text",
            "element_name": "First Name",
            "locator_type": "id",
            "locator_value": "firstName",
            "page_url": "/automation-practice-form",
        }],
        "expected_results": ["First Name accepts input"],
        "mapping": {"page_url": "/automation-practice-form", "id": "firstName"},
    }

    assert not GeminiService.validate_generation_inputs(
        test_case,
        {"generated_data": {"First Name": ["Ada"]}},
        None,
    )


def test_selenium_prompt_rejects_unrelated_page_load_locators():
    prompt = render_prompt()

    assert "Do not add page-load locators" in prompt
    assert "router-link" in prompt
    assert "Remove every locator that cannot be traced directly" in prompt
    assert "https://pypi.org" in prompt


def test_generation_metadata_rejects_unrelated_application_host():
    test_case = {
        "application_url": "https://pypi.org",
        "steps": [{
            "action": "click_element",
            "element_name": "Browser Windows",
            "locator_type": "id",
            "locator_value": "tabButton",
        }],
        "expected_results": ["Browser Windows is clickable"],
        "mapping": {"page_name": "Browser Windows", "id": "tabButton"},
    }

    errors = GeminiService.validate_generation_inputs(test_case, {"requires_test_data": False}, None)

    assert any("Page consistency failure" in error for error in errors)


def test_validate_code_rejects_locator_from_another_page():
    test_case = {
        "application_url": "https://demoqa.com/browser-windows",
        "steps": [{
            "action": "click_element",
            "element_name": "Browser Windows",
            "locator_type": "id",
            "locator_value": "tabButton",
        }],
        "expected_results": ["Browser Windows is clickable"],
        "mapping": {"page_name": "Browser Windows", "id": "tabButton"},
    }
    code = """from selenium.webdriver.common.by import By

def test_browser_windows(driver):
    target = driver.find_element(By.ID, 'tabButton')
    target.click()
    driver.find_element(By.ID, 'firstName').is_displayed()
    assert target.is_displayed()
"""

    with pytest.raises(GeminiServiceError, match="Locator traceability failure"):
        GeminiService._validate_code(code, test_case, {})


def test_validate_code_rejects_markup_url_and_self_fulfilling_assertion():
    test_case = {
        "application_url": "https://example.com",
        "steps": [{"action": "open_url", "locator_type": "url", "locator_value": "application_url"}],
        "expected_results": ["Page loads successfully"],
    }
    code = """import pytest

def test_page(driver):
    driver.get('<a href=\"https://example.com\">Example</a>')
    assert True
"""
    with pytest.raises(GeminiServiceError, match="URL behavior"):
        GeminiService._validate_code(code, test_case, {})


@pytest.mark.parametrize("url_value", [
    '<a href="https://demoqa.com/text-box">Text Box</a>',
    'https://demoqa.com/text-box?target=_blank',
    'https://demoqa.com/text-box?rel=nofollow',
    'https://demoqa.com/text-box?title=TextBox',
])
def test_validate_code_rejects_markup_in_all_url_operations(url_value):
    code = f'''import pytest

def test_navigation(driver):
    driver.get({url_value!r})
    WebDriverWait(driver, 10).until(EC.url_contains({url_value!r}))
    assert {url_value!r} in driver.current_url
'''

    with pytest.raises(GeminiServiceError, match="forbidden .* markup"):
        GeminiService._validate_code(code, {}, {})


def test_validate_code_accepts_plain_urls_in_navigation_operations():
    code = '''import pytest

def test_navigation(driver):
    driver.get("https://demoqa.com/text-box")
    WebDriverWait(driver, 10).until(EC.url_changes("https://demoqa.com"))
    WebDriverWait(driver, 10).until(EC.url_contains("/text-box"))
    assert "/text-box" in driver.current_url
'''

    assert GeminiService._validate_code(code, {}, {}) == code.strip()


def test_validate_code_rejects_value_echo_as_negative_validation():
    test_case = {
        "application_url": "https://example.com",
        "test_type": "negative",
        "steps": [
            {"action": "enter_text", "locator_type": "id", "locator_value": "email"},
            {"action": "submit_form", "locator_type": "id", "locator_value": "submit"},
        ],
        "expected_results": ["Invalid email is rejected", "Validation message is displayed"],
        "mapping": {"field_type": "email", "id": "email"},
    }
    code = """from selenium.webdriver.common.by import By

def test_email(driver):
    field = driver.find_element(By.ID, 'email')
    field.send_keys('invalid')
    assert field.get_attribute('value') == 'invalid'
    driver.find_element(By.ID, 'submit').click()
"""
    with pytest.raises(GeminiServiceError, match="negative behavior"):
        GeminiService._validate_code(code, test_case, {})


def test_selenium_prompt_enforces_scenario_alignment_quality_gate():
    prompt = render_prompt()

    required_fragments = (
        "title, description, test_type, steps, expected_results, mapping, automation_intent",
        "every step has at least one Selenium action",
        "every expected result has at least one meaningful assertion",
        "Reject and regenerate any script that covers only part of the scenario",
    )
    for fragment in required_fragments:
        assert fragment in prompt


def test_selenium_prompt_requires_complete_navigation_flow():
    prompt = render_prompt()

    assert "verify the supplied target is visible" in prompt
    assert "wait for navigation" in prompt
    assert "destination path is contained in driver.current_url" in prompt
    assert "unique supplied destination element is present or visible" in prompt
    assert "A click-only script is invalid" in prompt


def test_selenium_prompt_requires_exact_href_locator_generation():
    prompt = render_prompt()

    assert "(By.CSS_SELECTOR, 'a[href=\"/accordian\"]')" in prompt
    assert "substitute the supplied href exactly" in prompt


def test_selenium_prompt_rejects_generic_navigation_locators():
    prompt = render_prompt()

    assert "a.router-link" in prompt
    assert "By.TAG_NAME, \"a\"" in prompt
    assert "By.LINK_TEXT, \"Book Store\"" in prompt
    assert "Every navigation locator must uniquely identify the target link" in prompt


def test_navigation_rejects_generic_anchor_when_href_exists():
    test_case = {
        "title": "Verify Book Store navigation",
        "test_type": "navigation",
        "mapping": {"href": "/books", "destination_id": "booksHeading"},
        "steps": [{"action": "click_element", "locator_type": "css_selector", "locator_value": "a.router-link"}],
        "expected_results": ["URL changes to /books", "Books page loads"],
    }
    code = """
    link = driver.find_element(By.CSS_SELECTOR, "a.router-link")
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.router-link")))
    link.click()
    """

    error = GeminiService._scenario_code_alignment_error(code, test_case)

    assert error and any(
        message in error
        for message in ("generic anchor locator", "href-based locator", "mapping.href is not used")
    )


def test_navigation_rejects_generic_anchor_even_when_explicitly_supplied():
    test_case = {
        "title": "Verify generic link navigation",
        "test_type": "navigation",
        "steps": [{"action": "click_element", "locator_type": "css_selector", "locator_value": "a"}],
        "expected_results": ["Link is clickable"],
    }
    code = """
    link = driver.find_element(By.CSS_SELECTOR, "a")
    link.click()
    assert link.is_displayed()
    """

    assert GeminiService._generic_navigation_locator_error(
        code, has_href=False, has_link_text=False, supplied_locator_count=1
    ) is not None


def test_validate_code_repairs_generic_anchor_from_href_mapping():
    test_case = {
        "title": "Verify Books navigation",
        "test_type": "navigation",
        "mapping": {"href": "/books"},
    }
    code = '''from selenium.webdriver.common.by import By

def test_books(driver):
    link = driver.find_element(By.CSS_SELECTOR, "a.router-link")
    link.click()
    assert link.is_displayed()
'''

    repaired = GeminiService._repair_generic_navigation_locators(code, test_case)

    assert 'a.router-link' not in repaired
    assert 'a[href="/books"]' in repaired


def test_validate_code_repairs_generic_anchor_from_navigation_evidence():
    test_case = {
        "title": "Verify Books navigation",
        "test_type": "navigation",
        "steps": [{"action": "click_element", "locator_type": "css_selector", "locator_value": "a.router-link"}],
        "expected_results": ["URL changes to /books"],
    }
    code = '''from selenium.webdriver.common.by import By

def test_books(driver):
    link = driver.find_element(By.CSS_SELECTOR, "a.router-link")
    link.click()
    assert "/books" in driver.current_url
'''

    repaired = GeminiService._repair_generic_navigation_locators(code, test_case)

    assert 'a.router-link' not in repaired
    assert 'a[href="/books"]' in repaired


def test_validate_code_repairs_generic_anchor_from_nested_agent_contract():
    test_case = {
        "title": "Verify Books navigation",
        "test_type": "navigation",
        "mapping": {},
        "agent_1_contract": {
            "page_metadata": {
                "links": [{"href": "/books", "text": "Book Store"}],
            },
        },
        "steps": [{"action": "click_element", "locator_type": "css_selector", "locator_value": "a.router-link"}],
    }
    code = 'driver.find_element(By.CSS_SELECTOR, "a.router-link")'

    repaired = GeminiService._repair_generic_navigation_locators(code, test_case)

    assert 'a.router-link' not in repaired
    assert 'a[href="/books"]' in repaired


def test_validate_code_repairs_call_style_tag_name_anchor():
    test_case = {
        "title": "Verify Books navigation",
        "test_type": "navigation",
        "mapping": {"href": "/books"},
    }
    code = 'driver.find_element(By.TAG_NAME("a"))'

    repaired = GeminiService._repair_generic_navigation_locators(code, test_case)

    assert "By.TAG_NAME" not in repaired
    assert 'a[href="/books"]' in repaired


def test_validate_code_uses_nested_href_metadata_during_alignment_validation():
    test_case = {
        "title": "Verify Books navigation",
        "test_type": "navigation",
        "mapping": {},
        "agent_1_contract": {
            "page_metadata": {"links": [{"href": "/books", "text": "Book Store"}]},
        },
        "steps": [{"action": "click_element", "locator_type": "css_selector", "locator_value": "a.router-link"}],
        "expected_results": ["Books link is clickable"],
    }
    code = """from selenium.webdriver.common.by import By

def test_books(driver):
    link = driver.find_element(By.CSS_SELECTOR, "a.router-link")
    link.click()
    assert link.is_displayed()
"""

    result = GeminiService._validate_code(code, test_case, {})

    assert 'a.router-link' not in result
    assert 'a[href="/books"]' in result


def test_navigation_locator_priority_prefers_href_over_link_text():
    test_case = {
        "title": "Verify Accordian navigation",
        "test_type": "navigation",
        "mapping": {"href": "/accordian", "link_text": "Accordian", "destination_id": "accordianHeading"},
        "steps": [{"action": "click_element", "locator_type": "css_selector", "locator_value": "a[href='/accordian']"}],
        "expected_results": ["URL changes to /accordian", "Accordian page loads"],
    }
    code = """
    link = driver.find_element(By.CSS_SELECTOR, 'a[href="/accordian"]')
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[href="/accordian"]')))
    link.click()
    """

    assert GeminiService._scenario_code_alignment_error(code, test_case) is not None


def test_navigation_locator_priority_requires_exact_link_text_without_href():
    test_case = {
        "title": "Verify Book Store navigation",
        "test_type": "navigation",
        "mapping": {"link_text": "Book Store"},
        "steps": [{"action": "click_element", "locator_type": "link_text", "locator_value": "Book Store"}],
        "expected_results": ["Link is clickable"],
    }
    code = 'link = driver.find_element(By.PARTIAL_LINK_TEXT, "Book Store")\nlink.click()\n'

    error = GeminiService._scenario_code_alignment_error(code, test_case)

    assert error and "supplied link text" in error


def test_navigation_rejects_invented_link_text_when_dom_metadata_does_not_contain_it():
    test_case = {
        "title": "Verify Books navigation",
        "test_type": "navigation",
        "mapping": {"href": "/books", "link_text": "Application"},
        "page_metadata": {"links": [{"href": "/books", "text": "Book Store"}]},
        "steps": [{"action": "click_element", "locator_type": "link_text", "locator_value": "Application"}],
        "expected_results": ["Books page loads"],
    }
    repaired = GeminiService._repair_generic_navigation_locators(
        'driver.find_element(By.CSS_SELECTOR, "a.router-link")', test_case
    )

    assert "By.LINK_TEXT" not in repaired
    assert 'a[href="/books"]' in repaired


def test_navigation_locator_priority_uses_partial_link_text_as_last_fallback():
    test_case = {
        "title": "Verify Book navigation",
        "test_type": "navigation",
        "mapping": {"partial_link_text": "Book"},
        "steps": [{"action": "click_element", "locator_type": "partial_link_text", "locator_value": "Book"}],
        "expected_results": ["Link is clickable"],
    }
    code = 'link = driver.find_element(By.PARTIAL_LINK_TEXT, "Book")\nlink.click()\n'

    assert GeminiService._scenario_code_alignment_error(code, test_case) is None


def test_selenium_prompt_requires_mapping_and_no_extra_navigation_actions():
    prompt = render_prompt()

    assert "mapping contains `href`, use that exact href" in prompt
    assert "Never replace it with a generic selector" in prompt
    assert "highest-priority supplied metadata" in prompt
    assert "Remove every unrelated action, locator, field, and assertion" in prompt
    assert 'Remove HTML tags from URLs' in prompt


def test_generation_metadata_rejects_label_based_locator_values():
    test_case = {
        "application_url": "https://demoqa.com/automation-practice-form",
        "steps": [{
            "action": "enter_text",
            "element_name": "State and City",
            "locator_type": "id",
            "locator_value": "State and City",
            "locator_status": "locator unavailable",
        }],
        "expected_results": ["Entry succeeds"],
    }
    errors = GeminiService.validate_generation_inputs(test_case, {"generated_data": {"State and City": "Chennai"}}, None)
    assert errors
    assert any("Locator values must be actual supplied locators" in e for e in errors)


def test_validate_code_extracts_python_from_markdown_and_prose():
    code = '''Here is the test script:\n```python\nfrom selenium import webdriver\n\ndef test_demo():\n    driver = webdriver.Chrome()\n    assert True\n```\nThis is the final version.'''
    result = GeminiService._validate_code(code, {}, {})
    assert 'from selenium import webdriver' in result
    assert 'assert True' in result


def test_validate_code_ignores_trailing_explanation_after_valid_python():
    code = '''Here is the code:\n\nfrom selenium import webdriver\n\ndef test_demo():\n    driver = webdriver.Chrome()\n    assert True\n\nThis script validates the page state.'''
    result = GeminiService._validate_code(code, {}, {})
    assert 'from selenium import webdriver' in result
    assert 'assert True' in result
    assert 'This script validates the page state.' not in result


def test_validate_code_rejects_metadata_error_prefix_without_python_parse():
    code = 'ERROR: Missing or invalid metadata from Agent 1 or Agent 2. Missing fields: application_url, expected_results'
    with pytest.raises(GeminiServiceError, match='ERROR: Missing or invalid metadata from Agent 1 or Agent 2'):
        GeminiService._validate_code(code, {}, {})


def test_validate_code_rejects_placeholder_identifier_and_locator_string():
    for code in (
        "import pytest\n\ndef test_demo(element):\n    assert element\n",
        "from selenium.webdriver.common.by import By\n\ndef test_demo(driver):\n    driver.find_element(By.ID, 'input_field')\n",
    ):
        with pytest.raises(GeminiServiceError, match="placeholder identifiers"):
            GeminiService._validate_code(code, {}, {})


def test_validate_code_allows_element_name_bound_to_selenium_locator():
    code = "from selenium.webdriver.common.by import By\n\ndef test_demo(driver):\n    element = driver.find_element(By.ID, 'submit')\n    element.click()\n    assert element.is_displayed()\n"
    assert GeminiService._validate_code(code, {}, {}) == code.strip()


def test_validate_code_does_not_fail_for_unused_optional_locator():
    test_case = {
        "application_url": "https://example.com",
        "steps": [{
            "action": "click_element",
            "locator_type": "id",
            "locator_value": "submit",
        }],
        "expected_results": ["Submit is clickable"],
        "mapping": {"id": "userName"},
    }
    code = """from selenium.webdriver.common.by import By

def test_submit(driver):
    submit = driver.find_element(By.ID, "submit")
    submit.click()
    assert submit.is_displayed()
"""

    assert GeminiService._validate_code(code, test_case, {}) == code.strip()


def test_coverage_accepts_more_specific_locator_for_generic_supplied_locator():
    test_case = {
        "title": "Verify Books navigation",
        "test_type": "navigation",
        "mapping": {"href": "/books"},
        "steps": [{"action": "click_element", "locator_type": "css_selector", "locator_value": "a.router-link"}],
        "expected_results": ["Books link is clickable"],
    }
    tree = ast.parse("""def test_books():
    link = driver.find_element(By.CSS_SELECTOR, 'a[href="/books"]')
    link.click()
    assert link.is_displayed()
""")

    assert GeminiService._scenario_coverage_error(
        'a[href="/books"] link.click() assert link.is_displayed()', tree, test_case
    ) is None


def test_validate_code_rejects_generic_boundary_implementation():
    test_case = {
        "title": "Verify subjectsInput enforces maximum length boundary",
        "test_type": "boundary",
        "steps": [
            {"action": "enter_text", "locator_type": "id", "locator_value": "subjectsInput"},
            {"action": "enter_text", "locator_type": "id", "locator_value": "subjectsInput"},
            {"action": "enter_text", "locator_type": "id", "locator_value": "subjectsInput"},
        ],
        "expected_results": ["Maximum length is enforced"],
        "mapping": {"field_type": "text", "id": "subjectsInput"},
    }
    code = "from selenium.webdriver.common.by import By\n\ndef test_boundary(driver):\n    value = 'A'\n    driver.find_element(By.ID, 'subjectsInput').send_keys(value)\n    assert value == 'A'\n"
    with pytest.raises(GeminiServiceError, match="boundary behavior"):
        GeminiService._validate_code(code, test_case, {})


def test_validate_code_accepts_multiple_boundary_probes():
    test_case = {
        "title": "Verify subjectsInput enforces maximum length boundary",
        "test_type": "boundary",
        "steps": [
            {"action": "enter_text", "locator_type": "id", "locator_value": "subjectsInput"},
            {"action": "enter_text", "locator_type": "id", "locator_value": "subjectsInput"},
            {"action": "enter_text", "locator_type": "id", "locator_value": "subjectsInput"},
        ],
        "expected_results": ["Minimum accepted", "Maximum accepted", "Maximum + 1 rejected"],
        "mapping": {"field_type": "text", "id": "subjectsInput"},
    }
    code = "from selenium.webdriver.common.by import By\n\ndef test_boundary(driver):\n    field = driver.find_element(By.ID, 'subjectsInput')\n    min_length = 'A'\n    max_length = 'A' * 10\n    over_limit = 'A' * 11\n    field.send_keys(min_length)\n    assert len(min_length) >= 1\n    field.clear()\n    field.send_keys(max_length)\n    assert len(max_length) <= 10\n    field.clear()\n    field.send_keys(over_limit)\n    assert len(field.get_attribute('value')) <= max_length\n"
    assert GeminiService._validate_code(code, test_case, {}) == code.strip()


def test_validate_code_rejects_partial_checkbox_flow():
    test_case = {
        "title": "Verify Sports checkbox can be selected and deselected",
        "test_type": "positive",
        "steps": [
            {"action": "select_checkbox", "description": "Select checkbox"},
            {"action": "verify", "description": "Verify selected"},
            {"action": "deselect_checkbox", "description": "Deselect checkbox"},
            {"action": "verify", "description": "Verify deselected"},
        ],
        "expected_results": ["Checkbox selected", "Checkbox deselected"],
        "mapping": {"field_type": "checkbox", "id": "sports"},
    }
    code = "from selenium.webdriver.common.by import By\n\ndef test_checkbox(driver):\n    checkbox = driver.find_element(By.ID, 'sports')\n    checkbox.click()\n    assert checkbox.is_selected()\n"
    with pytest.raises(GeminiServiceError, match="checkbox behavior"):
        GeminiService._validate_code(code, test_case, {})


def test_validate_code_accepts_complete_checkbox_flow():
    test_case = {
        "title": "Verify Sports checkbox can be selected and deselected",
        "test_type": "positive",
        "steps": [
            {"action": "select_checkbox", "description": "Select checkbox"},
            {"action": "verify", "description": "Verify selected"},
            {"action": "deselect_checkbox", "description": "Deselect checkbox"},
            {"action": "verify", "description": "Verify deselected"},
        ],
        "expected_results": ["Checkbox selected", "Checkbox deselected"],
        "mapping": {"field_type": "checkbox", "id": "sports"},
    }
    code = "from selenium.webdriver.common.by import By\n\ndef test_checkbox(driver):\n    checkbox = driver.find_element(By.ID, 'sports')\n    checkbox.click()\n    assert checkbox.is_selected()\n    checkbox.click()\n    assert not checkbox.is_selected()\n"
    assert GeminiService._validate_code(code, test_case, {}) == code.strip()


def test_validate_code_counts_repeated_safe_click_helper_calls():
    test_case = {
        "title": "Verify Sports checkbox can be selected and deselected",
        "test_type": "positive",
        "steps": [
            {"action": "select_checkbox", "description": "Select checkbox"},
            {"action": "deselect_checkbox", "description": "Deselect checkbox"},
        ],
        "expected_results": ["Checkbox selected", "Checkbox deselected"],
        "mapping": {"field_type": "checkbox", "id": "sports"},
    }
    code = """from selenium.webdriver.common.by import By

def safe_click(element):
    element.click()

def test_checkbox(driver):
    checkbox = driver.find_element(By.ID, 'sports')
    safe_click(checkbox)
    assert checkbox.is_selected()
    safe_click(checkbox)
    assert not checkbox.is_selected()
"""

    assert GeminiService._validate_code(code, test_case, {}) == code.strip()


def test_validate_code_rejects_navigation_click_only_flow():
    test_case = {
        "title": "Verify link navigates to dynamic properties",
        "test_type": "navigation",
        "steps": [{
            "action": "click_element",
            "locator_type": "css_selector",
            "locator_value": "a[href='/dynamic-properties']",
        }],
        "expected_results": [
            "URL changes to destination (/dynamic-properties)",
            "Destination page loads successfully",
        ],
    }
    code = """from selenium.webdriver.common.by import By

def test_navigation(driver):
    driver.find_element(By.CSS_SELECTOR, "a[href='/dynamic-properties']").click()
    assert True
"""
    with pytest.raises(GeminiServiceError, match="navigation behavior"):
        GeminiService._validate_code(code, test_case, {})


def test_validate_code_accepts_complete_navigation_flow():
    test_case = {
        "application_url": "https://demoqa.com",
        "title": "Verify link navigates to dynamic properties",
        "test_type": "navigation",
        "steps": [{
            "action": "click_element",
            "locator_type": "css_selector",
            "locator_value": "a[href='/dynamic-properties']",
        }, {
            "action": "verify_element_visible",
            "description": "Verify destination page heading is visible",
            "locator_type": "id",
            "locator_value": "enableAfter",
        }],
        "expected_results": [
            "URL changes to destination (/dynamic-properties)",
            "Destination page loads successfully",
        ],
    }
    code = """from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def test_navigation(driver):
    link_locator = (By.CSS_SELECTOR, "a[href='/dynamic-properties']")
    link = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(link_locator))
    assert link.is_displayed()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(link_locator))
    assert link.is_enabled()
    link.click()
    WebDriverWait(driver, 10).until(EC.url_contains("/dynamic-properties"))
    assert "/dynamic-properties" in driver.current_url
    destination = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, "enableAfter"))
    )
    assert destination.is_displayed()
"""
    assert GeminiService._validate_code(code, test_case, {}) == code.strip()


def test_validate_code_rejects_unrelated_navigation_locator():
    test_case = {
        "application_url": "https://demoqa.com",
        "title": "Verify link Frames navigates to frames",
        "test_type": "navigation",
        "mapping": {"href": "/frames"},
        "steps": [{
            "action": "click_element",
            "locator_type": "css_selector",
            "locator_value": "a[href='/frames']",
        }, {
            "action": "verify_element_visible",
            "description": "Verify destination page heading is visible",
            "locator_type": "id",
            "locator_value": "framesHeading",
        }],
        "expected_results": ["URL changes to destination (/frames)", "Destination page loads successfully"],
    }
    code = """from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def test_frames(driver):
    link_locator = (By.CSS_SELECTOR, "a[href='/frames']")
    link = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(link_locator))
    assert link.is_displayed()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(link_locator))
    assert link.is_enabled()
    link.click()
    WebDriverWait(driver, 10).until(EC.url_contains('/frames'))
    assert '/frames' in driver.current_url
    destination = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'framesHeading')))
    assert destination.is_displayed()
    user_name = driver.find_element(By.ID, 'userName')
    assert user_name.is_displayed()
"""
    with pytest.raises(GeminiServiceError, match="unrelated navigation locators"):
        GeminiService._validate_code(code, test_case, {})


def test_href_mapping_selects_navigation_rules_before_stale_locator_rules():
    test_case = {
        "title": "Verify link navigates to links",
        "test_type": "functional",
        "mapping": {"href": "/links"},
        "test_steps": [{
            "action": "click_element",
            "locator_type": "css_selector",
            "locator_value": "a[href='/links']",
        }, {
            "action": "verify_element_visible",
            "element_name": "Destination page heading",
            "locator_type": "id",
            "locator_value": "linksHeading",
        }, {
            "action": "enter_text",
            "element_name": "Username",
            "locator_type": "id",
            "locator_value": "userName",
        }],
        "expected_results": ["URL changes to destination (/links)", "Destination page loads successfully"],
    }
    code = """from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def test_links(driver):
    locator = (By.CSS_SELECTOR, "a[href='/links']")
    link = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(locator))
    assert link.is_displayed()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(locator))
    assert link.is_enabled()
    link.click()
    WebDriverWait(driver, 10).until(EC.url_contains('/links'))
    assert '/links' in driver.current_url
    heading = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'linksHeading')))
    assert heading.is_displayed()
"""
    assert GeminiService._validate_code(code, test_case, {}) == code.strip()


def test_navigation_metadata_validation_ignores_unrelated_username_step():
    test_case = {
        "application_url": "https://demoqa.com",
        "title": "Verify link navigates to links",
        "test_type": "navigation",
        "mapping": {"href": "/links"},
        "test_steps": [
            {"action": "click_element", "locator_type": "css_selector", "locator_value": "a[href='/links']"},
            {"action": "verify_element_visible", "description": "Verify destination page heading is visible", "locator_type": "id", "locator_value": "linksHeading"},
            {"action": "enter_text", "element_name": "Username", "locator_type": "id", "locator_value": "userName"},
        ],
        "expected_results": ["URL changes to destination (/links)", "Destination page loads successfully"],
    }
    assert not GeminiService.validate_generation_inputs(test_case, {}, None)


def test_validate_code_allows_navigation_url_fallback_without_destination_metadata():
    test_case = {
        "application_url": "https://demoqa.com",
        "title": "Verify link Frames navigates to frames",
        "test_type": "navigation",
        "mapping": {"href": "/frames"},
        "steps": [{
            "action": "click_element",
            "locator_type": "css_selector",
            "locator_value": "a[href='/frames']",
        }],
        "expected_results": ["URL changes to destination (/frames)", "Destination page loads successfully"],
    }
    code = """from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def test_frames(driver):
    locator = (By.CSS_SELECTOR, "a[href='/frames']")
    link = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(locator))
    assert link.is_displayed()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(locator))
    assert link.is_enabled()
    link.click()
    WebDriverWait(driver, 10).until(EC.url_contains('/frames'))
    assert '/frames' in driver.current_url
"""
    with pytest.raises(GeminiServiceError, match="destination page locator is required"):
        GeminiService._validate_code(code, test_case, {})


def test_validate_code_counts_radio_action_helper_in_test_flow():
    test_case = {
        "title": "Verify Female radio button can be selected",
        "test_type": "positive",
        "steps": [
            {"action": "select_radio", "description": "Select radio"},
            {"action": "verify", "description": "Verify selected"},
        ],
        "expected_results": ["Radio selected"],
        "mapping": {"field_type": "radio", "id": "gender-female"},
    }
    code = "from selenium.webdriver.common.by import By\n\ndef safe_click(element):\n    element.click()\n\ndef test_radio(driver):\n    radio = driver.find_element(By.ID, 'gender-female')\n    safe_click(radio)\n    assert radio.is_selected()\n"
    assert GeminiService._validate_code(code, test_case, {}) == code.strip()


def test_validate_code_rejects_text_entry_for_radio_scenario():
    test_case = {
        "title": "Verify only one gender option can be selected",
        "test_type": "boundary",
        "steps": [{"action": "select_radio", "locator_type": "id", "locator_value": "gender-male"}],
        "expected_results": ["Only one option remains selected"],
        "mapping": {"field_type": "radio", "id": "gender-male"},
    }
    code = "from selenium.webdriver.common.by import By\n\ndef test_radio(driver):\n    driver.find_element(By.ID, 'gender-male').send_keys('Male')\n    assert True\n"
    with pytest.raises(GeminiServiceError, match="radio behavior"):
        GeminiService._validate_code(code, test_case, {})


def test_validate_code_accepts_radio_checked_state_assertion():
    test_case = {
        "title": "Verify Female radio button can be selected",
        "test_type": "positive",
        "steps": [{"action": "select_radio", "locator_type": "id", "locator_value": "gender-female"}],
        "expected_results": ["Female radio button is selected"],
        "mapping": {"field_type": "radio", "id": "gender-female"},
    }
    code = "from selenium.webdriver.common.by import By\n\ndef test_radio(driver):\n    radio = driver.find_element(By.ID, 'gender-female')\n    radio.click()\n    assert radio.get_attribute('checked') == 'true'\n"
    assert GeminiService._validate_code(code, test_case, {}) == code.strip()


def test_validate_code_accepts_hidden_radio_associated_label_locator():
    test_case = {
        "title": "Verify radio option can be selected",
        "test_type": "functional",
        "steps": [{
            "action": "select_radio",
            "locator_type": "id",
            "locator_value": "gender-radio-1",
        }],
        "expected_results": ["Radio option is selected"],
        "mapping": {"field_type": "radio", "id": "gender-radio-1"},
    }
    code = """from selenium.webdriver.common.by import By

def test_radio(driver):
    label = driver.find_element(By.CSS_SELECTOR, "label[for='gender-radio-1']")
    label.click()
    radio = driver.find_element(By.ID, 'gender-radio-1')
    assert radio.is_selected()
"""

    assert GeminiService._validate_code(code, test_case, {}) == code.strip()


def test_validate_code_uses_mapped_radio_target_over_stale_sibling_step():
    test_case = {
        "title": "Verify Female radio option can be selected",
        "test_type": "functional",
        "steps": [{
            "action": "select_radio",
            "locator_type": "id",
            "locator_value": "gender-radio-1",
        }],
        "expected_results": ["Female radio option is selected"],
        "mapping": {
            "field_type": "radio",
            "id": "gender-radio-3",
            "label": "Female",
        },
    }
    code = """from selenium.webdriver.common.by import By

def test_radio(driver):
    radio = driver.find_element(By.ID, 'gender-radio-3')
    radio.click()
    assert radio.is_selected()
"""

    assert GeminiService._validate_code(code, test_case, {}) == code.strip()


def test_validate_code_rejects_negative_input_only_test():
    test_case = {
        "title": "Verify Mobile Number rejects invalid text input",
        "test_type": "negative",
        "steps": [
            {"action": "enter_text", "description": "Enter invalid input"},
            {"action": "submit_form", "description": "Submit form"},
            {"action": "verify", "description": "Verify rejection and validation feedback"},
        ],
        "expected_results": ["Invalid value rejected", "Validation message displayed"],
        "mapping": {"field_type": "phone", "id": "mobile"},
    }
    code = "from selenium.webdriver.common.by import By\n\ndef test_mobile(driver):\n    field = driver.find_element(By.ID, 'mobile')\n    field.send_keys('@@@@@')\n    assert field.get_attribute('value') != ''\n"
    with pytest.raises(GeminiServiceError, match="negative behavior"):
        GeminiService._validate_code(code, test_case, {})


def test_validate_code_accepts_complete_negative_flow():
    test_case = {
        "title": "Verify Mobile Number rejects invalid text input",
        "test_type": "negative",
        "steps": [
            {"action": "enter_text", "description": "Enter invalid input"},
            {"action": "submit_form", "description": "Submit form"},
            {"action": "verify", "description": "Verify rejection and validation feedback"},
        ],
        "expected_results": ["Invalid value rejected", "Validation message displayed"],
        "mapping": {"field_type": "phone", "id": "mobile"},
    }
    code = "from selenium.webdriver.common.by import By\n\ndef test_mobile(driver):\n    field = driver.find_element(By.ID, 'mobile')\n    field.send_keys('@@@@@')\n    driver.find_element(By.ID, 'submit').click()\n    assert 'invalid' in field.get_attribute('aria-invalid')\n    assert driver.find_element(By.ID, 'error-message').is_displayed()\n"
    assert GeminiService._validate_code(code, test_case, {}) == code.strip()


def test_describe_missing_metadata_extracts_fields_from_error_text():
    details = GeminiService._describe_missing_metadata(
        {"application_url": "https://example.com"},
        {"generated_data": {}},
        "ERROR: Missing or invalid metadata from Agent 1 or Agent 2. Missing fields: application_url, generated_data",
    )
    assert "application_url" in details["agent1"]
    assert "generated_data" in details["agent2"]


def test_validate_code_repairs_windows_path_escapes_in_generated_python():
    code = '''from selenium import webdriver\n\npath = "C:\\Users\\demo\\project\\app.py"\n\ndef test_demo():\n    driver = webdriver.Chrome()\n    assert path\n'''
    result = GeminiService._validate_code(code, {}, {})
    assert 'C:\\Users\\demo\\project\\app.py' in result
    assert 'path =' in result


def test_generation_metadata_validation_requires_real_locators_and_data():
    test_case = {
        "application_url": "https://demoqa.com/automation-practice-form",
        "steps": [{
            "action": "enter_text",
            "element_name": "Email",
            "locator_type": "id",
            "locator_value": "userEmail",
        }],
        "expected_results": ["Email is accepted"],
    }
    assert not GeminiService.validate_generation_inputs(
        test_case,
        {"generated_data": {"Email": "john@test.com"}},
        None,
    )

    invalid_case = {
        **test_case,
        "steps": [{
            "action": "click_element",
            "element_name": "Submit",
            "locator_type": "id",
            "locator_value": "Submit",
        }],
    }
    assert GeminiService.validate_generation_inputs(
        invalid_case,
        {"generated_data": {"Email": "john@test.com"}},
        None,
    )
    assert GeminiService.validate_generation_inputs(
        test_case,
        {"generated_data": {"Email": "test"}},
        None,
    )


def test_agent2_category_generated_data_is_preserved_for_agent3_prompt():
    test_case = {
        "application_url": "https://demoqa.com/automation-practice-form",
        "steps": [{
            "action": "enter_text",
            "element_name": "Email",
            "locator_type": "id",
            "locator_value": "userEmail",
        }],
        "expected_results": ["Email is accepted"],
    }
    test_data = {
        "scenario_id": "S1",
        "requires_test_data": True,
        "generated_data": {
            "positive": [{"Email": "john@example.com"}],
            "negative": [],
            "boundary": [],
            "validation": [],
        },
    }
    assert not GeminiService.validate_generation_inputs(test_case, test_data, None)

    prompt = gemini_service.ENV.get_template("generate_selenium.j2").render(
        test_case=test_case,
        test_data=test_data,
    )
    assert '"generated_data"' in prompt
    assert '"positive"' in prompt
    assert '"john@example.com"' in prompt


def test_generated_code_must_use_a_value_for_each_input_field():
    test_case = {
        "application_url": "https://demoqa.com/automation-practice-form",
        "steps": [
            {"action": "enter_text", "element_name": "Email", "locator_type": "id", "locator_value": "userEmail"},
            {"action": "enter_text", "element_name": "Name", "locator_type": "id", "locator_value": "userName"},
        ],
        "expected_results": ["Form accepts the values"],
    }
    test_data = {
        "requires_test_data": True,
        "generated_data": {
            "positive": {
                "Email": ["john@example.com"],
                "Name": ["John Doe"],
            },
        },
    }
    code = """import pytest
from selenium.webdriver.common.by import By

def test_S1(driver):
    driver.find_element(By.ID, "userEmail").send_keys("john@example.com")
    driver.find_element(By.ID, "userName").clear()
"""

    with pytest.raises(GeminiServiceError, match="supplied values for fields"):
        GeminiService._validate_code(code, test_case, test_data)


def test_generation_metadata_allows_resolved_navigation_url_without_data():
    test_case = {
        "application_url": "https://demoqa.com",
        "steps": [{
            "action": "open_url",
            "locator_type": "url",
            "locator_value": "application_url",
        }],
        "expected_results": ["Page loads successfully"],
    }
    assert not GeminiService.validate_generation_inputs(
        test_case,
        {"requires_test_data": False, "generated_data": {}},
        None,
    )


def test_generation_metadata_allows_page_title_assertion_without_dom_locator():
    test_case = {
        "application_url": "https://demoqa.com",
        "steps": [{
            "action": "verify_page_title",
            "element_name": "Page Title",
            "locator_type": "title",
            "locator_value": "demoqa",
        }],
        "expected_results": ["Browser title matches demoqa"],
    }
    assert not GeminiService.validate_generation_inputs(
        test_case,
        {"requires_test_data": False, "generated_data": {}},
        None,
    )


def test_generation_metadata_allows_verified_dom_id_matching_label():
    test_case = {
        "application_url": "https://demoqa.com",
        "steps": [{
            "action": "click_element",
            "element_name": "Submit",
            "locator_type": "id",
            "locator_value": "submit",
            "locator_status": "available",
        }],
        "expected_results": ["Submit is clickable"],
    }
    assert not GeminiService.validate_generation_inputs(
        test_case,
        {"requires_test_data": False, "generated_data": {}},
        None,
    )


def test_generation_metadata_accepts_common_agent1_action_aliases():
    actions = ("click", "type_text", "select_option", "check", "choose_radio", "upload", "submit")
    for action in actions:
        test_case = {
            "application_url": "https://demoqa.com",
            "steps": [{
                "action": action,
                "element_name": "Control",
                "locator_type": "css_selector",
                "locator_value": "#control",
                "locator_status": "available",
            }],
            "expected_results": ["Control is handled"],
        }
        test_data = {
            "requires_test_data": action in {"type_text", "select_option", "upload"},
            "generated_data": {"positive": {"Control": ["valid-value"]}},
        }
        assert not GeminiService.validate_generation_inputs(test_case, test_data, None), action


def test_generation_metadata_prefers_normalized_steps_over_raw_label_steps():
    test_case = {
        "application_url": "https://demoqa.com",
        "steps": [{
            "action": "click_element",
            "element_name": "Submit",
            "locator_type": "id",
            "locator_value": "Submit",
        }],
        "test_steps": [{
            "action": "click_element",
            "element_name": "Submit",
            "locator_type": "id",
            "locator_value": "submit",
            "locator_status": "available",
        }],
        "expected_results": ["Submit is clickable"],
    }
    assert not GeminiService.validate_generation_inputs(
        test_case,
        {"requires_test_data": False, "generated_data": {}},
        None,
    )


def test_gemini_accepts_aq_prefixed_google_key_for_query_auth(monkeypatch):
    requests = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "import pytest\nfrom selenium import webdriver\n\n\n@pytest.fixture\ndef driver():\n    driver = webdriver.Chrome()\n    try:\n        yield driver\n    finally:\n        driver.quit()\n\n\ndef test_S1(driver):\n    element = driver.find_element('id', 'submit')\n    element.click()\n    assert element.is_displayed()\n"}]}}]}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            requests.append((args, kwargs))
            return Response()

    monkeypatch.setattr(gemini_service.httpx, "AsyncClient", lambda **kwargs: Client())
    service = GeminiService(api_key="AQ." + "x" * 20)
    asyncio.run(service.generate_selenium_code(
        {
            "application_url": "https://example.com",
            "steps": [{"action": "click_element", "locator_type": "id", "locator_value": "submit"}],
            "expected_results": ["Submit is clickable"],
        },
        {"requires_test_data": False},
        None,
    ))

    _, request_kwargs = requests[0]
    assert requests[0][0][0] == gemini_service.API_URL.format(model=service.model)
    assert request_kwargs["params"] == {"key": service.api_key}
    assert "Authorization" not in request_kwargs["headers"]


def test_gemini_uses_query_key_without_bearer_header(monkeypatch):
    requests = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "import pytest\nfrom selenium import webdriver\n\n\n@pytest.fixture\ndef driver():\n    driver = webdriver.Chrome()\n    try:\n        yield driver\n    finally:\n        driver.quit()\n\n\ndef test_S1(driver):\n    element = driver.find_element('id', 'submit')\n    element.click()\n    assert element.is_displayed()\n"}]}}]}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            requests.append((args, kwargs))
            return Response()

    monkeypatch.setattr(gemini_service.httpx, "AsyncClient", lambda **kwargs: Client())
    service = GeminiService(api_key="AIza" + "x" * 20)
    result = asyncio.run(service.generate_selenium_code(
        {
            "application_url": "https://example.com",
            "steps": [{"action": "click_element", "locator_type": "id", "locator_value": "submit"}],
            "expected_results": ["Submit is clickable"],
        },
        {"requires_test_data": False},
        None,
    ))

    assert result.startswith("import pytest")
    assert requests[0][0][0] == gemini_service.API_URL.format(model=service.model)
    _, request_kwargs = requests[0]
    assert request_kwargs["params"] == {"key": service.api_key}
    assert request_kwargs["headers"] == {"Content-Type": "application/json"}
    assert "Authorization" not in request_kwargs["headers"]


def test_navigation_scenario_does_not_require_missing_agent2_data():
    test_case = {
        "application_url": "https://demoqa.com",
        "title": "Verify link 'Selectable' navigates to '/selectable'",
        "test_type": "navigation",
        "input_fields": ["userName", "userEmail"],
        "required_data": [{"field_name": "userName"}],
        "steps": [{
            "action": "click_element",
            "element_name": "Selectable",
            "locator_type": "css_selector",
            "locator_value": "a[href='/selectable']",
            "locator_status": "available",
        }],
        "expected_results": ["URL contains '/selectable'"],
    }
    assert not GeminiService.validate_generation_inputs(test_case, {}, None)
