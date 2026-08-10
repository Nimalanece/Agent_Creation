import api from "./apiClient";

export async function downloadSeleniumCode(code: string): Promise<Blob> {
  const resp = await api.post("/api/download-selenium", { code }, { responseType: "blob" });
  return resp.data as Blob;
}
