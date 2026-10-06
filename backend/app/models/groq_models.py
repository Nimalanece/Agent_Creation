from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class GroqResponse(BaseModel):
    raw: Dict[str, Any]
    parsed: Optional[Any] = None

class RequiredDataField(BaseModel):
    field_name: str
    field_type: str
    business_purpose: str
    expected_format: str
    validation_rules: Optional[List[str]] = None

class StepItem(BaseModel):
    step_number: Optional[int] = None
    action: str
    target: Optional[str] = None
    expected_value: Optional[Any] = None
    data_type: Optional[str] = None

class TestCaseItem(BaseModel):
    id: str
    scenario_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    test_type: Optional[str] = None
    priority: Optional[str] = None
    preconditions: Optional[List[str]] = None
    steps: List[StepItem]
    expected_results: Optional[List[str]] = None
    expected_result: Optional[str] = None
    input_fields: Optional[List[str]] = None
    required_data: Optional[List[RequiredDataField]] = None
    automation_hints: Optional[Dict[str, Any]] = None
    mapping: Optional[Dict[str, Any]] = None

class ScenarioItem(BaseModel):
    id: str
    module: Optional[str] = None
    test_scenario_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    test_type: Optional[str] = None
    mapping: Optional[Dict[str, Any]] = None

    @staticmethod
    def allow_test_type(value: Optional[str]) -> Optional[str]:
        allowed = {"positive", "negative", "validation", "boundary", "functional", "navigation", "security"}
        if not value:
            return "functional"
        normalized = str(value).strip().lower()
        return normalized if normalized in allowed else "functional"

class ScenarioList(BaseModel):
    application_name: Optional[str] = None
    scenarios: List[ScenarioItem]
    test_cases: Optional[List[TestCaseItem]] = None

    @staticmethod
    def scenario_policy(value: Any) -> Any:
        return value

class TestCaseList(BaseModel):
    application_name: Optional[str] = None
    testcases: Optional[List[TestCaseItem]] = None
    test_cases: Optional[List[TestCaseItem]] = None

    @staticmethod
    def normalize_cases(value: Any) -> Any:
        return value
