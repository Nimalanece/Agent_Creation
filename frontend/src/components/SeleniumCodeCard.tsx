import React, { useMemo, useState } from "react";
import type { Agent1Contract, Agent2Contract, TestCaseItem } from "../types/api";
import { generateSeleniumCode } from "../services/seleniumService";

interface Props {
  contract?: Agent1Contract;
  testData?: Agent2Contract | null;
  testcases?: TestCaseItem[];
}

const SeleniumCodeCard: React.FC<Props> = ({ contract, testData, testcases = [] }) => {
  const [codeByScenario, setCodeByScenario] = useState<Record<string, string>>({});
  const [loadingScenario, setLoadingScenario] = useState<string | null>(null);
  const [copiedScenario, setCopiedScenario] = useState<string | null>(null);
  const [expandedScenario, setExpandedScenario] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cases = useMemo(() => {
    const normalizeCases = (items: TestCaseItem[]) => items
      .map((testCase) => ({
        ...testCase,
        scenario_id: testCase.scenario_id || (testCase as TestCaseItem & { test_scenario_id?: string }).test_scenario_id,
      }))
      .filter((testCase) => Boolean(testCase.scenario_id));
    const groupedCases = (contract?.feature_groups || []).flatMap((group) => group.test_cases || []);
    const contractCases = normalizeCases(contract?.agent_3_input?.test_cases || []);
    const featureCases = normalizeCases(groupedCases);
    const apiCases = normalizeCases(testcases);
    return contractCases.length > 0 ? contractCases : featureCases.length > 0 ? featureCases : apiCases;
  }, [contract, testcases]);

  const dataByScenario = useMemo(() => {
    const result: Record<string, Record<string, unknown>> = {};
    const contractData = testData as (Agent2Contract & { scenarioOutputs?: unknown[] }) | null | undefined;
    const scenarioOutputs = Array.isArray(contractData?.scenario_outputs)
      ? contractData.scenario_outputs
      : Array.isArray(contractData?.scenarioOutputs)
        ? contractData.scenarioOutputs
        : [];
    scenarioOutputs.forEach((item) => {
      if (item.scenario_id) result[item.scenario_id] = item as unknown as Record<string, unknown>;
    });

    // Merge older flattened Agent 2 datasets even when scenario_outputs exists.
    // Scenario IDs can differ between generated records, so never let an
    // unrelated scenario entry prevent a matching dataset from being used.
    if (contractData) {
      const addDatasets = (datasets: unknown, bucket: string) => {
        if (!Array.isArray(datasets)) return;
        datasets.forEach((dataset: any) => {
          const scenarioId = dataset?.scenario_id || dataset?.scenario || dataset?.test_scenario_id || dataset?.scenarioId;
          if (!scenarioId) return;
          const field = dataset?.field_name || dataset?.field || dataset?.name || "target_field";
          const values = Array.isArray(dataset?.values)
            ? dataset.values.map((item: any) => item?.value !== undefined ? item.value : item)
            : dataset?.generated_data?.[bucket]?.[field] || [];
          const existing = result[scenarioId] || {
            scenario_id: scenarioId,
            requires_test_data: true,
            generated_data: { positive: {}, negative: {}, boundary: {}, validation: {} },
          };
          (existing.generated_data as Record<string, Record<string, unknown>>)[bucket][field] = values;
          result[scenarioId] = existing;
        });
      };
      addDatasets((contractData as any).positive_data, "positive");
      addDatasets((contractData as any).negative_data, "negative");
      addDatasets((contractData as any).boundary_data, "boundary");
      addDatasets((contractData as any).validation_data, "validation");
    }
    return result;
  }, [testData]);

  async function handleGenerate(testCase: TestCaseItem) {
    const scenarioId = testCase.scenario_id;
    if (!scenarioId) return;
    setLoadingScenario(scenarioId);
    setError(null);
    try {
      const code = await generateSeleniumCode(
        testCase,
        dataByScenario[testCase.scenario_id || ""] || {},
        contract?.application_url || contract?.agent_3_input?.url,
        testData,  // NEW: Pass full agent_2_contract for backend auto-extraction
      );
      setCodeByScenario((current) => ({ ...current, [scenarioId]: code }));
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : detail?.message || detail?.error || err?.message || "Unable to generate Selenium code.",
      );
    } finally {
      setLoadingScenario(null);
    }
  }

  async function handleCopy(scenarioId: string) {
    const code = codeByScenario[scenarioId];
    if (!code) return;

    try {
      await navigator.clipboard.writeText(code);
      setCopiedScenario(scenarioId);
      window.setTimeout(() => setCopiedScenario((current) => current === scenarioId ? null : current), 1800);
    } catch {
      setError("Unable to copy Selenium code to the clipboard.");
    }
  }

  function handleDownload(scenarioId: string) {
    const code = codeByScenario[scenarioId];
    if (!code) return;
    const blob = new Blob([code], { type: "text/x-python;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `selenium-${scenarioId}.py`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  return (
    <section className="bg-white shadow rounded-lg p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="dashboard-kicker">Agent 3 output</div>
          <h2 className="mt-1 text-xl font-semibold text-white">Selenium Code</h2>
          <div className="text-sm text-gray-600">Production-ready pytest automation</div>
        </div>
      </div>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      {cases.length === 0 ? (
        <p className="mt-3 text-sm text-gray-500">No test cases available.</p>
      ) : (
        <div className="mt-3 space-y-3">
          {cases.map((testCase) => {
            const scenarioId = testCase.scenario_id;
            if (!scenarioId) return null;
            return (
              <div key={scenarioId} className="rounded-xl border border-gray-200">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 bg-gray-50 px-3 py-2">
                  <span className="text-sm font-semibold text-gray-700">Scenario ID: {scenarioId}</span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleGenerate(testCase)}
                      disabled={loadingScenario === scenarioId}
                      className="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      {loadingScenario === scenarioId ? "Generating..." : "Generate Code"}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleCopy(scenarioId)}
                      disabled={!codeByScenario[scenarioId] || loadingScenario === scenarioId}
                      aria-label={`Copy generated code for scenario ${scenarioId}`}
                      className="rounded border border-gray-300 bg-white px-3 py-1 text-xs text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {copiedScenario === scenarioId ? "Copied" : "Copy Code"}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDownload(scenarioId)}
                      disabled={!codeByScenario[scenarioId] || loadingScenario === scenarioId}
                      className="rounded border border-gray-300 bg-white px-3 py-1 text-xs text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Download
                    </button>
                  </div>
                </div>
                {codeByScenario[scenarioId] ? (
                  <div className={`code-viewer relative overflow-auto ${expandedScenario === scenarioId ? "fixed inset-4 z-50 max-h-none" : "max-h-96"}`}>
                    <button
                      type="button"
                      onClick={() => setExpandedScenario((current) => current === scenarioId ? null : scenarioId)}
                      className="absolute right-3 top-3 z-10 rounded border border-slate-600 bg-slate-900/90 px-2 py-1 text-[11px] text-slate-300 hover:text-white"
                    >
                      {expandedScenario === scenarioId ? "Collapse" : "Expand"}
                    </button>
                    <pre className="m-0 grid min-w-max grid-cols-[3rem_1fr] p-4 pr-20 text-xs text-slate-300">
                      {codeByScenario[scenarioId].split("\n").map((line, index) => (
                        <React.Fragment key={`${scenarioId}-${index}`}>
                          <span className="select-none pr-4 text-right text-slate-600">{index + 1}</span>
                          <span>{line || " "}</span>
                        </React.Fragment>
                      ))}
                    </pre>
                  </div>
                ) : (
                  <p className="px-3 py-3 text-sm text-gray-500">No Selenium code generated yet.</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};

export default SeleniumCodeCard;