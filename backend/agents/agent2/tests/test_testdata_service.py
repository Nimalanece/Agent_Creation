from backend.agents.agent2.models.schemas import Agent2GenerationRequest
from backend.agents.agent2.services.testdata_service import build_test_data_contract


def test_build_test_data_contract_from_agent1_payload():
    payload = Agent2GenerationRequest(
        application_name="Example App",
        url="https://example.com/login",
        agent_1_contract={
            "test_cases": [
                {
                    "title": "Login test",
                    "scenario_id": "SCN001",
                    "input_fields": [
                        {"name": "username", "field_type": "username"},
                        {"name": "password", "field_type": "password"},
                    ],
                    "required_data": [
                        {"name": "email", "field_type": "email"}
                    ],
                }
            ]
        },
    )

    response = build_test_data_contract(payload)

    assert response.application_name == "Example App"
    assert response.url == "https://example.com/login"
    assert response.requires_test_data is True
    assert len(response.positive_data) >= 1
    assert response.negative_data[0].values[0].value != "sample_value"
    assert all(value != "alphabetic-phone" for dataset in response.validation_data for value in [v.value for v in dataset.values])
    assert all(value != "LeadingSpace" for dataset in response.validation_data for value in [v.value for v in dataset.values])
    assert all(value != "TrailingSpace" for dataset in response.validation_data for value in [v.value for v in dataset.values])

    username_validation = next(
        (dataset for dataset in response.validation_data if dataset.field_name == "username"),
        None,
    )
    email_validation = next(
        (dataset for dataset in response.validation_data if dataset.field_name == "email"),
        None,
    )

    assert username_validation is not None
    assert [item.value for item in username_validation.values] == ["", " ", " John", "John ", "@@@@@", "<script>alert('test')</script>"]
    assert email_validation is not None
    assert [item.value for item in email_validation.values] == ["", "user@", "@gmail.com", "user@@gmail.com", "user gmail.com"]


def test_skips_navigation_or_page_load_scenarios():
    payload = Agent2GenerationRequest(
        application_name="Example App",
        url="https://example.com/login",
        agent_1_contract={
            "test_cases": [
                {
                    "title": "Page load verification",
                    "scenario_id": "SCN002",
                    "test_type": "navigation",
                    "input_fields": [],
                }
            ]
        },
    )

    response = build_test_data_contract(payload)

    assert response.requires_test_data is False
    assert not response.positive_data
    assert not response.negative_data
    assert not response.boundary_data
    assert not response.validation_data
