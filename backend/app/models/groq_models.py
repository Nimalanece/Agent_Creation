from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class GroqResponse(BaseModel):
    raw: Dict[str, Any]
    parsed: Optional[Any] = None

class ScenarioItem(BaseModel):
    id: str
    module: Optional[str] = None
    test_scenario_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    mapping: Optional[Dict[str, Any]] = None

class ScenarioList(BaseModel):
    scenarios: List[ScenarioItem]

class TestCaseItem(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    preconditions: Optional[List[str]] = None
    steps: List[Dict[str, Any]]
    expected_result: Optional[Any] = None
    priority: Optional[str] = None

class TestCaseList(BaseModel):
    testcases: List[TestCaseItem]

class TestData(BaseModel):
    cases: Dict[str, Any]

class SeleniumBundle(BaseModel):
    files: Dict[str, str]
    metadata: Optional[Dict[str, Any]]
