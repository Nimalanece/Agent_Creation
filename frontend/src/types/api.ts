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
  mapping?: Record<string, any>;
}

export interface TestCaseItem {
  id: string;
  title: string;
  description?: string;
  preconditions?: string[];
  steps: any[];
  expected_result?: any;
  priority?: string;
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

export interface FullAnalysisResponse {
  analysis: AnalysisResult;
  scenarios: ScenarioItem[];
  testcases: TestCaseItem[];
  testdata: Record<string, any>;
  discovered_locators?: DiscoveredLocators;
  selenium_code: string;
  selenium_files?: Record<string, string>;

  // Demo mode fields (optional)
  defect_possibilities?: DemoInsight[];
  risk_areas?: Array<string | { area?: string; reason?: string }>;
  automation_coverage_percent?: number;
  recommended_smoke_tests?: string[];
  demo_insights?: Record<string, any>;
}
