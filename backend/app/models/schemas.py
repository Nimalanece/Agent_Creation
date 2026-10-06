from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

class AnalyzeOptions(BaseModel):
    render_js: Optional[bool] = False
    depth: Optional[int] = 1

class AnalyzeRequest(BaseModel):
    url: str
    options: Optional[AnalyzeOptions] = None

class AnalyzeResponse(BaseModel):
    run_id: str
    status: Optional[str] = "queued"

class RunRequest(BaseModel):
    run_id: Optional[str] = None
    url: Optional[str] = None
    options: Optional[Dict[str, Any]] = None

class GenericResponse(BaseModel):
    run_id: str
    status: Optional[str] = "queued"

class Agent1Feature(BaseModel):
    feature_id: str
    name: str
    description: Optional[str] = None

class Agent1PageMetadata(BaseModel):
    forms: List[Dict[str, Any]] = Field(default_factory=list)
    buttons: List[Dict[str, Any]] = Field(default_factory=list)
    fields: List[Dict[str, Any]] = Field(default_factory=list)
    dropdowns: List[Dict[str, Any]] = Field(default_factory=list)
    checkboxes: List[Dict[str, Any]] = Field(default_factory=list)
    links: List[Dict[str, Any]] = Field(default_factory=list)

class Agent1TestStep(BaseModel):
    step_number: Optional[int] = None
    action: str
    selector: Optional[str] = None
    target: Optional[str] = None
    element_name: Optional[str] = None  # NEW: Automation-ready element name (e.g., "First Name", "Submit Button")
    locator_type: Optional[str] = None  # NEW: Type of locator (id, css_selector, xpath, class, etc.)
    locator_value: Optional[str] = None  # NEW: The actual locator value (e.g., "firstName", "a[href='/select-menu']")
    locator_status: str = "locator unavailable"
    value: Optional[Any] = None
    expected_value: Optional[Any] = None
    data_type: Optional[str] = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        if not str(value or "").strip():
            raise ValueError("action cannot be empty")
        return str(value).strip()

class Agent1AutomationHints(BaseModel):
    page_name: str = Field(default="Page")
    actions: List[str] = Field(default_factory=list)
    assertions: List[str] = Field(default_factory=list)

class Agent1RequiredDataField(BaseModel):
    field_name: str
    field_type: Literal[
        "email", "username", "password", "phone_number", "phone", "text", "textarea", "address", "multiline", "number", "date", "search", "dropdown", "select", "radio", "checkbox", "file", "url"
    ]
    business_purpose: str
    expected_format: str
    validation_rules: List[str] = Field(default_factory=list)

    @field_validator("field_name")
    @classmethod
    def validate_field_name(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("field_name cannot be empty")
        return cleaned

class Agent1TestCase(BaseModel):
    test_case_id: Optional[str] = None
    feature_id: Optional[str] = None
    scenario_id: Optional[str] = None
    id: Optional[str] = None
    title: str
    priority: str
    test_type: Literal["positive", "negative", "validation", "boundary", "functional", "navigation", "security"] = "functional"
    application_url: Optional[str] = None
    preconditions: List[str] = Field(default_factory=list)
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    test_steps: List[Agent1TestStep] = Field(default_factory=list)
    input_fields: List[str] = Field(default_factory=list)
    required_data: List[Agent1RequiredDataField] = Field(default_factory=list)
    automation_hints: Agent1AutomationHints = Field(default_factory=Agent1AutomationHints)
    expected_results: List[str] = Field(default_factory=list)
    expected_result: str = Field(default="Element is visible")
    mapping: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("test_type")
    @classmethod
    def validate_test_type(cls, value: str) -> str:
        allow = {"positive", "negative", "validation", "boundary", "functional", "navigation", "security"}
        normalized = str(value or "functional").strip().lower()
        if normalized not in allow:
            return "functional"
        return normalized

    @model_validator(mode="after")
    def normalize_legacy_members(self):
        if not self.steps and self.test_steps:
            self.steps = [
                {
                    "step_number": idx + 1,
                    "action": step.action,
                    **({"target": step.selector} if step.selector else {}),
                    **({"element_name": step.element_name} if step.element_name else {}),
                    **({"locator_type": step.locator_type} if step.locator_type else {}),
                    **({"locator_value": step.locator_value} if step.locator_value else {}),
                    **({"value": step.value} if step.value is not None else {}),
                    **({"expected_value": step.expected_value} if step.expected_value is not None else {}),
                    **({"data_type": step.data_type} if step.data_type else {}),
                }
                for idx, step in enumerate(self.test_steps)
            ]
        if not self.expected_results and self.expected_result:
            self.expected_results = [self.expected_result]
        if not self.mapping:
            self.mapping = {}
        if self.input_fields and not self.required_data:
            self.required_data = [
                Agent1RequiredDataField(
                    field_name=field_name,
                    field_type="text",
                    business_purpose="User interaction value",
                    expected_format="text value",
                    validation_rules=["cannot be empty"],
                )
                for field_name in self.input_fields
                if str(field_name).strip()
            ]
        return self

class Agent1TestScenario(BaseModel):
    scenario_id: Optional[str] = None
    feature_id: str
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    priority: str
    test_type: Literal["positive", "negative", "validation", "boundary", "functional", "navigation", "security"] = "functional"
    preconditions: List[str] = Field(default_factory=list)
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    test_steps: List[Agent1TestStep] = Field(default_factory=list)
    expected_results: List[str] = Field(default_factory=list)
    field_name: Optional[str] = None
    mapping: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("test_type")
    @classmethod
    def validate_test_type(cls, value: str) -> str:
        allow = {"positive", "negative", "validation", "boundary", "functional", "navigation", "security"}
        normalized = str(value or "functional").strip().lower()
        if normalized not in allow:
            return "functional"
        return normalized

    @model_validator(mode="after")
    def normalize_legacy_members(self):
        if not self.steps and self.test_steps:
            self.steps = [
                {
                    "step_number": idx + 1,
                    "action": step.action,
                    **({"target": step.selector} if step.selector else {}),
                    **({"value": step.value} if step.value is not None else {}),
                    **({"expected_value": step.expected_value} if step.expected_value is not None else {}),
                }
                for idx, step in enumerate(self.test_steps)
            ]
        if not self.mapping:
            self.mapping = {}
        if not self.field_name:
            field_name = self.mapping.get("field_name") or self.mapping.get("name") or self.mapping.get("label") or None
            if isinstance(field_name, str) and field_name.strip():
                self.field_name = field_name.strip()
        return self

class Agent2TestDataInput(BaseModel):
    application_name: str
    url: str
    test_cases: List[Agent1TestCase] = Field(default_factory=list)

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

class Agent2Contract(BaseModel):
    application_name: str
    url: str
    positive_data: List[Agent2DataSet] = Field(default_factory=list)
    negative_data: List[Agent2DataSet] = Field(default_factory=list)
    boundary_data: List[Agent2DataSet] = Field(default_factory=list)
    validation_data: List[Agent2DataSet] = Field(default_factory=list)

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
    # Per-scenario outputs to provide a one-to-one mapping with Agent 1 scenarios
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
        return normalized if normalized in allowed else "functional"

class Agent2ScenarioOutput(BaseModel):
    scenario_id: Optional[str] = Field(None, description="Agent 1 scenario identifier (preserved)")
    requires_test_data: bool = Field(default=True)
    generated_data: Agent2GeneratedDataBundle = Field(default_factory=Agent2GeneratedDataBundle)

class Agent3SeleniumInput(BaseModel):
    application_name: str
    url: str
    features: List[Agent1Feature] = Field(default_factory=list)
    test_scenarios: List[Agent1TestScenario] = Field(default_factory=list)
    test_cases: List[Agent1TestCase] = Field(default_factory=list)

class Agent1FeatureGroup(BaseModel):
    feature_id: str
    feature: str
    description: Optional[str] = None
    test_scenarios: List[Agent1TestScenario] = Field(default_factory=list)
    test_cases: List[Agent1TestCase] = Field(default_factory=list)

class Agent1Contract(BaseModel):
    application_name: str
    url: str
    application_url: str
    page_title: Optional[str] = None
    features: List[Agent1Feature] = Field(default_factory=list)
    feature_groups: List[Agent1FeatureGroup] = Field(default_factory=list)
    test_cases: List[Agent1TestCase] = Field(default_factory=list)
    page_metadata: Agent1PageMetadata = Field(default_factory=Agent1PageMetadata)

    agent_2_input: Agent2TestDataInput
    agent_3_input: Agent3SeleniumInput

class Agent1PipelineResponse(BaseModel):
    analysis: Dict[str, Any]
    application_url: str
    page_title: Optional[str] = None
    scenarios: List[Dict[str, Any]]
    testcases: List[Dict[str, Any]]
    discovered_locators: Optional[Dict[str, Any]] = None
    agent_1_contract: Agent1Contract
    agent_2_contract: Optional[Agent2Contract] = None
    agent_3_test_data: Optional[Dict[str, Any]] = Field(
        None,
        description="Direct Agent 3 test data bundle extracted by the orchestrator and passed to Selenium generation.",
    )


class Agent3GenerationRequest(BaseModel):
    test_case: Dict[str, Any]
    # test_data should be populated from orchestrator result's agent_3_test_data field
    # It contains generated_data for test value substitution in Selenium code
    test_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Test data from orchestrator (agent_3_test_data). Contains generated_data for test value substitution."
    )
    application_url: Optional[str] = None
    # Optional: pass full agent_2_contract to auto-extract test_data if not provided
    # This is a fallback if test_data is not directly passed
    agent_2_contract: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Full Agent2 contract for fallback extraction of test_data if test_data field is empty"
    )


class Agent3GenerationResponse(BaseModel):
    scenario_id: Optional[str] = None
    code: str

