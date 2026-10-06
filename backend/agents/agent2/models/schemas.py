from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Agent2GeneratedDataValue(BaseModel):
    value: Any
    status: str = "valid"
    rationale: Optional[str] = None


class Agent2DataSet(BaseModel):
    dataset_type: Literal["positive", "negative", "boundary", "validation"]
    scenario_id: Optional[str] = None
    title: str
    field_name: str
    field_type: str
    description: str
    generated_data: Dict[str, Any] = Field(default_factory=dict)
    values: List[Agent2GeneratedDataValue] = Field(default_factory=list)
    expected_format: str
    validation_rules: List[str] = Field(default_factory=list)


class Agent2TestDataPayload(BaseModel):
    application_name: str
    url: str
    test_cases: List[Dict[str, Any]] = Field(default_factory=list)


class Agent2GenerationRequest(BaseModel):
    application_name: Optional[str] = None
    url: Optional[str] = None
    scenarios: Optional[List[Dict[str, Any]]] = None
    test_cases: Optional[List[Dict[str, Any]]] = None
    agent_1_contract: Optional[Dict[str, Any]] = None


class Agent2GenerationResponse(BaseModel):
    application_name: str
    url: str
    requires_test_data: bool = True
    positive_data: List[Agent2DataSet] = Field(default_factory=list)
    negative_data: List[Agent2DataSet] = Field(default_factory=list)
    boundary_data: List[Agent2DataSet] = Field(default_factory=list)
    validation_data: List[Agent2DataSet] = Field(default_factory=list)
    scenario_outputs: List["Agent2ScenarioOutput"] = Field(default_factory=list)


class Agent2GeneratedDataBundle(BaseModel):
    positive: Dict[str, Any] = Field(default_factory=dict)
    negative: Dict[str, Any] = Field(default_factory=dict)
    boundary: Dict[str, Any] = Field(default_factory=dict)
    validation: Dict[str, Any] = Field(default_factory=dict)


class Agent2ScenarioInput(BaseModel):
    scenario_id: Optional[str] = Field(None, description="Stable Agent 1 scenario identifier (optional)")
    description: str = Field(..., min_length=1, description="Human-readable scenario objective")
    test_type: str = Field(..., min_length=1, description="Scenario intent category")
    mapping: Dict[str, Any] = Field(default_factory=dict, description="Agent 1 mapping payload for downstream data synthesis")

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("description cannot be empty")
        return cleaned

    @field_validator("test_type")
    @classmethod
    def validate_test_type(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        allowed = {"positive", "negative", "boundary", "validation", "functional", "navigation", "security"}
        if not normalized:
            raise ValueError("test_type cannot be empty")
        if normalized not in allowed:
            return "functional"
        return normalized


class Agent2ScenarioOutput(BaseModel):
    scenario_id: Optional[str] = Field(None, description="Agent 1 scenario identifier (preserved)")
    requires_test_data: bool = True
    generated_data: Agent2GeneratedDataBundle = Field(default_factory=Agent2GeneratedDataBundle)
