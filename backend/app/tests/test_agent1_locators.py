from app.services.orchestrator_service import _build_agent1_step


def test_agent1_replaces_label_with_dom_locator():
    step = _build_agent1_step(
        {
            "action": "enter_text",
            "element_name": "First Name",
            "locator_type": "id",
            "locator_value": "First Name",
        },
        1,
        {"scenario_id": "S1", "mapping": {}},
        {"inputs": [{"label": "First Name", "name": "First Name", "id": "firstName", "selector": "input#firstName"}]},
    )

    assert step.element_name == "First Name"
    assert step.locator_type == "id"
    assert step.locator_value == "firstName"
    assert step.locator_status == "available"


def test_agent1_marks_missing_dom_locator_unavailable():
    step = _build_agent1_step(
        {
            "action": "click_element",
            "element_name": "Submit",
            "locator_type": "id",
            "locator_value": "Submit",
        },
        1,
        {"scenario_id": "S2", "mapping": {}},
        {"buttons": [{"text": "Submit"}]},
    )

    assert step.element_name == "Submit"
    assert step.locator_type == ""
    assert step.locator_value == ""
    assert step.locator_status == "locator unavailable"


def test_agent1_prefers_css_selector_when_dom_name_is_visible_label():
    step = _build_agent1_step(
        {"action": "select_dropdown_option", "element_name": "State and City"},
        1,
        {"scenario_id": "S3", "mapping": {}},
        {"selects": [{"label": "State and City", "name": "State and City", "selector": "div#stateCity"}]},
    )

    assert step.locator_type == "css_selector"
    assert step.locator_value == "div#stateCity"
    assert step.locator_status == "available"
