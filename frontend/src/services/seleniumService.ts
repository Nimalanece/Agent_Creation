import api from "./apiClient";

export async function generateSeleniumCode(testCase: unknown, testData: unknown, applicationUrl?: string, agent2Contract?: unknown): Promise<string> {
  const response = await api.post<{ code: string }>("/api/agent3/generate-selenium", {
    test_case: testCase,
    test_data: testData,
    application_url: applicationUrl,
    agent_2_contract: agent2Contract,  // NEW: Pass agent_2_contract for auto-extraction
  });
  return response.data.code;
}