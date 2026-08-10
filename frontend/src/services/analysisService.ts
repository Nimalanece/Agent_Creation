import api from "./apiClient";
import type { FullAnalysisResponse } from "../types/api";

export async function runFullAnalysis(url: string, signal?: AbortSignal): Promise<FullAnalysisResponse> {
  const payload = { url, render_js: true };
  const resp = await api.post<FullAnalysisResponse>("/api/full-analysis", payload, { signal });
  return resp.data;
}
