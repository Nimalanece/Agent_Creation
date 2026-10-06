export interface AnalysisResult {
  url: string;
  fetched_at?: string;
  title?: string;
  meta_description?: string;
  counts?: Record<string, number>;
  ids?: string[];
  classes?: Record<string, string[]>;
  buttons?: any[];
  inputs?: any[];
  selects?: any[];
  links?: any[];
  forms?: any[];
}

export interface ScenarioItem {
  id: string;
  module?: string;
  test_scenario_id?: string;
  title?: string;
  description?: string;
  priority?: string;
  test_type?: 'positive' | 'negative' | 'validation' | 'boundary' | 'functional' | 'navigation' | 'security';
  preconditions?: string[];
  steps?: any[];
  expected_results?: string[];
  field_name?: string;
  mapping?: Record<string, any>;
}

export interface TestCaseItem {
  id?: string;
  test_case_id?: string;
  feature_id?: string;
  scenario_id?: string;
  title: string;
  description?: string;
  test_type?: 'positive' | 'negative' | 'validation' | 'boundary' | 'functional' | 'navigation' | 'security';
  preconditions?: string[];
  steps: any[];
  expected_results?: string[];
  input_fields?: string[];
  required_data?: Agent1RequiredDataField[];
  automation_hints?: Agent1AutomationHints;
  expected_result?: any;
  priority?: string;
  mapping?: Record<string, any>;
}

export interface DemoInsight {
  id?: string;
  description?: string;
  likelihood?: 'low' | 'medium' | 'high';
}

export interface DiscoveredLocatorItem {
  tag?: string;
  id?: string;
  name?: string;
  type?: string;
  text?: string;
  placeholder?: string;
  href?: string;
  selector?: string;
}

export interface DiscoveredLocators {
  forms: Array<{ id?: string; name?: string; selector?: string; fields?: DiscoveredLocatorItem[] }>;
  inputs: DiscoveredLocatorItem[];
  buttons: DiscoveredLocatorItem[];
  links: DiscoveredLocatorItem[];
  headings: DiscoveredLocatorItem[];
}

export interface Agent1Feature {
  feature_id: string;
  name: string;
  description?: string;
}

export interface Agent1Step {
  step_number?: number;
  action: string;
  selector?: string;
  target?: string;
  value?: any;
  expected_value?: any;
  data_type?: string;
}

export interface Agent1AutomationHints {
  page_name: string;
  actions: string[];
  assertions: string[];
}

export interface Agent1RequiredDataField {
  field_name: string;
  field_type: 'email' | 'username' | 'password' | 'phone_number' | 'text' | 'number' | 'date' | 'search' | 'dropdown' | 'checkbox' | 'url';
  business_purpose: string;
  expected_format: string;
  validation_rules: string[];
}

export interface Agent1TestCase {
  test_case_id: string;
  feature_id: string;
  scenario_id: string;
  id?: string;
  title: string;
  test_type: 'positive' | 'negative' | 'validation' | 'boundary' | 'functional' | 'navigation' | 'security';
  priority: string;
  preconditions: string[];
  steps: any[];
  test_steps: Agent1Step[];
  input_fields: string[];
  required_data: Agent1RequiredDataField[];
  automation_hints: Agent1AutomationHints;
  expected_results: string[];
  expected_result: string;
  mapping: Record<string, any>;
}

export interface Agent1TestScenario {
  scenario_id: string;
  feature_id: string;
  id?: string;
  title: string;
  description?: string;
  priority: string;
  preconditions: string[];
  test_steps: Agent1Step[];
  expected_results: string[];
}

export interface Agent2GeneratedDataValue {
  value: string;
  status?: string;
  rationale?: string;
}

export interface Agent2DataSet {
  dataset_type: 'positive' | 'negative' | 'boundary' | 'validation';
  scenario_id: string;
  title: string;
  field_name: string;
  field_type: string;
  description: string;
  values: Agent2GeneratedDataValue[];
  expected_format: string;
  validation_rules: string[];
}

export interface Agent2GeneratedDataBundle {
  positive: Record<string, any[]>;
  negative: Record<string, any[]>;
  boundary: Record<string, any[]>;
  validation: Record<string, any[]>;
}

export interface Agent2ScenarioOutput {
  scenario_id: string;
  requires_test_data: boolean;
  generated_data: Agent2GeneratedDataBundle;
}

export interface Agent2Contract {
  application_name: string;
  url: string;
  positive_data: Agent2DataSet[];
  negative_data: Agent2DataSet[];
  boundary_data: Agent2DataSet[];
  validation_data: Agent2DataSet[];
  scenario_outputs?: Agent2ScenarioOutput[];
}

export interface Agent2Input {
  application_name: string;
  url: string;
  test_cases: Agent1TestCase[];
}

export interface Agent3Input {
  application_name: string;
  url: string;
  features: Agent1Feature[];
  test_scenarios: Agent1TestScenario[];
  test_cases: Agent1TestCase[];
}

export interface Agent1FeatureGroup {
  feature_id: string;
  feature: string;
  description?: string;
  test_scenarios: Agent1TestScenario[];
  test_cases: Agent1TestCase[];
}

export interface Agent1PageMetadata {
  forms: any[];
  buttons: any[];
  fields: any[];
  dropdowns: any[];
  checkboxes: any[];
  links: any[];
}

export interface Agent1Contract {
  application_name: string;
  url: string;
  application_url: string;
  page_title?: string;
  features: Agent1Feature[];
  feature_groups: Agent1FeatureGroup[];
  test_cases: Agent1TestCase[];
  page_metadata: Agent1PageMetadata;
  agent_2_input: Agent2Input;
  agent_3_input: Agent3Input;
}

export interface FullAnalysisResponse {
  analysis: AnalysisResult;
  application_url: string;
  page_title?: string;
  scenarios: ScenarioItem[];
  testcases: TestCaseItem[];
  page_metadata?: Agent1PageMetadata;
  discovered_locators?: DiscoveredLocators;
  agent_1_contract?: Agent1Contract;
  agent_2_contract?: Agent2Contract;

  // Demo mode fields (optional)
  defect_possibilities?: DemoInsight[];
  risk_areas?: Array<string | { area?: string; reason?: string }>;
  automation_coverage_percent?: number;
  recommended_smoke_tests?: string[];
  demo_insights?: Record<string, any>;
}
