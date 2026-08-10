import { useCallback, useRef, useState } from "react";
import type { FullAnalysisResponse } from "../types/api";
import { runFullAnalysis } from "../services/analysisService";

export function useFullAnalysis() {
  const [data, setData] = useState<FullAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    if (controllerRef.current) {
      controllerRef.current.abort();
      controllerRef.current = null;
      setLoading(false);
    }
  }, []);

  const run = useCallback(async (url: string) => {
    // cancel previous if running
    cancel();
    setError(null);
    setData(null);
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    try {
      const result = await runFullAnalysis(url, controller.signal);
      setData(result);
    } catch (err: any) {
      if (err?.name === "CanceledError" || err?.message === "canceled") {
        // request was cancelled
        setError("Request cancelled");
      } else {
        setError(err?.response?.data?.detail || err?.message || "Failed to run analysis");
      }
    } finally {
      setLoading(false);
      controllerRef.current = null;
    }
  }, [cancel]);

  return {
    data,
    loading,
    error,
    run,
    cancel,
  } as const;
}
