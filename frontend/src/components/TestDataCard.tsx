import React, { useMemo, useState } from "react";
import type { Agent2Contract } from "../types/api";

interface Props {
  contract?: Agent2Contract | null;
  loading?: boolean;
}

const PAGE_SIZES = [5, 10, 15];

const TestDataCard: React.FC<Props> = ({ contract, loading = false }) => {
  // Normalize scenario outputs: backend may return different shapes (scenario_outputs, scenarioOutputs),
  // or provide per-dataset arrays (positive_data etc.). Prefer explicit scenario_outputs when present.
  const scenarioOutputs = useMemo(() => {
    if (!contract) return [];
    if (Array.isArray((contract as any).scenario_outputs)) return (contract as any).scenario_outputs;
    if (Array.isArray((contract as any).scenarioOutputs)) return (contract as any).scenarioOutputs;

    // Fall back: assemble scenario_outputs from dataset arrays (positive_data, negative_data, boundary_data, validation_data)
    const byId: Record<string, any> = {};
    const addFromArray = (arr: any[], bucket: string) => {
      if (!Array.isArray(arr)) return;
      arr.forEach((ds) => {
        const sid = ds?.scenario_id || ds?.scenario || ds?.test_scenario_id || ds?.scenarioId;
        if (!sid) return;
        if (!byId[sid]) {
          byId[sid] = { scenario_id: sid, requires_test_data: true, generated_data: { positive: {}, negative: {}, boundary: {}, validation: {} } };
        }
        const field = ds?.field_name || ds?.field || ds?.name || ds?.title || "target_field";
        const values = Array.isArray(ds?.values) ? ds.values.map((v: any) => (v && v.value !== undefined ? v.value : v)) : ds?.values || ds?.generated_data?.[bucket]?.[field] || ds?.generated_data || [];
        // If values are objects with {value} unwrap
        const flat = values.map((v: any) => (v && v.value !== undefined ? v.value : v));
        byId[sid].generated_data[bucket][field] = flat;
      });
    };

    addFromArray((contract as any).positive_data, 'positive');
    addFromArray((contract as any).negative_data, 'negative');
    addFromArray((contract as any).boundary_data, 'boundary');
    addFromArray((contract as any).validation_data, 'validation');

    return Object.values(byId);
  }, [contract]);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZES[0]);
  const [showAll, setShowAll] = useState(false);

  // Developer debug: log the normalized scenario outputs received from backend
  // and expose a small banner in UI so triage is easier without opening raw JSON.
  // Remove or gate this in production if desired.
  console.log("TestDataCard: normalized scenarioOutputs:", scenarioOutputs);

  // Sort by Agent 1 scenario_id (preserve original ordering by ID). Missing IDs go last.
  const sortedScenarios = useMemo(() => {
    return [...scenarioOutputs].sort((a, b) => {
      const aId = a.scenario_id || "";
      const bId = b.scenario_id || "";
      if (!aId && !bId) return 0;
      if (!aId) return 1;
      if (!bId) return -1;
      return aId.localeCompare(bId, undefined, { numeric: true, sensitivity: "base" });
    });
  }, [scenarioOutputs]);

  const pageCount = Math.max(1, Math.ceil(sortedScenarios.length / pageSize));

  const current = useMemo(() => {
    if (showAll) {
      return sortedScenarios;
    }
    const start = (page - 1) * pageSize;
    return sortedScenarios.slice(start, start + pageSize);
  }, [sortedScenarios, page, pageSize, showAll]);


  return (
    <div className="bg-white shadow rounded-lg p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center">
        <div>
          <h2 className="text-lg font-medium">Test Data</h2>
          <div className="text-sm text-gray-600">{sortedScenarios.length} scenario(s) with test data</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => {
              setShowAll((prev) => {
                const next = !prev;
                if (next) {
                  setPage(1);
                }
                return next;
              });
            }}
            className="px-3 py-1 border rounded bg-gray-50 hover:bg-gray-100"
          >
            {showAll ? "Paginate" : "Show all"}
          </button>
          <label className="text-sm text-gray-600">Page size:</label>
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setPage(1);
            }}
            className="border rounded px-2 py-1 text-sm"
            disabled={showAll}
          >
            {PAGE_SIZES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-gray-500 mt-3">Running Agent 2 test data generation...</p>
      ) : !contract ? (
        <p className="text-sm text-gray-500 mt-3">No test data generated yet.</p>
      ) : (
        <div className="mt-3">
          <div className="text-sm text-gray-700 mb-2">
            <span className="font-medium">Application:</span> {contract.application_name || "Unknown Application"}
          </div>
          <div className="text-sm text-gray-700 mb-4">
            <span className="font-medium">URL:</span> {contract.url || "—"}
          </div>

          {/* Debug banner: show quick summary of scenario_outputs received */}
          <div className="mb-3 p-2 bg-blue-50 border border-blue-100 rounded text-sm text-blue-800">
            <div className="font-medium">Debug: Agent 2 scenario outputs</div>
            <div className="text-xs text-blue-700 mt-1">
              Received {scenarioOutputs.length} scenario(s).
              {scenarioOutputs.length > 0 && (
                <div className="mt-1 truncate">IDs: {scenarioOutputs.map((s: any) => s.scenario_id || "(no id)").slice(0,10).join(", ")}{scenarioOutputs.length > 10 ? ", ..." : ""}</div>
              )}
            </div>
          </div>

          {/* Scenario cards - one per Agent 1 scenario_id */}
          <div className="space-y-3">
            {current.map((sc, idx) => (
              <div key={sc.scenario_id || `scenario-${(page - 1) * pageSize + idx}`} className="border rounded p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-semibold">Scenario ID: {(sc.scenario_id && !/^SCN\d+/i.test(sc.scenario_id)) ? sc.scenario_id : "(no id)"}</div>
                    <div className="text-xs text-gray-500">Requires Test Data: {sc.requires_test_data ? "Yes" : "No"}</div>
                  </div>
                </div>

                <div className="mt-3">
                  {/* Debug banner when generated_data is empty despite requires_test_data = true */}
                  {sc.requires_test_data && (() => {
                    const gd = sc.generated_data || { positive: {}, negative: {}, boundary: {}, validation: {} };
                    const isEmpty = !Object.keys(gd).some((k) => Object.keys((gd as any)[k]).length > 0);
                    if (isEmpty) {
                      const counts = Object.keys(gd).reduce((acc, k) => {
                        acc[k] = Object.keys((gd as any)[k] || {}).reduce((c, f) => c + (((gd as any)[k][f] || []).length || 0), 0);
                        return acc;
                      }, {} as Record<string, number>);

                      return (
                        <div className="mb-3 border-l-4 border-yellow-400 bg-yellow-50 p-3 rounded">
                          <div className="text-sm font-semibold text-yellow-800">Debug: No generated data</div>
                          <div className="text-xs text-yellow-700 mt-1">The engine returned an empty dataset for this scenario. Helpful information for triage:</div>
                          <ul className="text-xs text-yellow-700 mt-2 list-disc list-inside">
                            <li>Scenario ID: <span className="font-medium">{sc.scenario_id || "(no id)"}</span></li>
                            <li>Requires Test Data: <span className="font-medium">{sc.requires_test_data ? "Yes" : "No"}</span></li>
                            <li>Generated counts: <span className="font-medium">Positive: {counts.positive || 0}, Negative: {counts.negative || 0}, Boundary: {counts.boundary || 0}, Validation: {counts.validation || 0}</span></li>
                          </ul>
                        </div>
                      );
                    }
                    return null;
                  })()}

                  {/* Render generated_data as human-friendly sections */}
                  {sc.requires_test_data ? (
                    (() => {
                      const gd = sc.generated_data || { positive: {}, negative: {}, boundary: {}, validation: {} };
                      const isEmpty = !Object.keys(gd).some((k) => Object.keys((gd as any)[k]).length > 0);
                      if (isEmpty) {
                        return null; // debug banner shown above when empty
                      }

                      const renderValues = (vals: any[]) => (
                        <ul className="list-disc list-inside ml-4 max-h-40 overflow-auto">
                          {vals.map((v, i) => (
                            <li key={i} className="text-sm text-gray-800 break-words">{typeof v === 'string' && v === '' ? '""' : String(v)}</li>
                          ))}
                        </ul>
                      );

                      const sectionFor = (label: string, bucket: Record<string, any>, accent: string) => (
                        <div className="min-w-0 rounded border border-gray-200 bg-gray-50 p-3">
                          <div className={`mb-2 border-b pb-2 text-sm font-semibold ${accent}`}>{label}</div>
                          {Object.keys(bucket).length === 0 ? (
                            <div className="text-xs text-gray-500">No values</div>
                          ) : (
                            <div className="space-y-2">
                              {Object.entries(bucket).map(([field, values]) => (
                                <div key={field} className="rounded border border-gray-200 bg-white p-2">
                                  <div className="truncate text-xs font-semibold text-gray-600" title={field}>{field}</div>
                                  <div className="mt-1">{renderValues((values as any[]) || [])}</div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );

                      return (
                        <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                          {sectionFor('Positive Data', (gd as any).positive || {}, 'text-green-700')}
                          {sectionFor('Negative Data', (gd as any).negative || {}, 'text-red-700')}
                          {sectionFor('Boundary Data', (gd as any).boundary || {}, 'text-amber-700')}
                          {sectionFor('Validation Data', (gd as any).validation || {}, 'text-blue-700')}
                        </div>
                      );
                    })()
                  ) : (
                    <div className="mt-2 text-xs text-gray-500">No test data required for this scenario.</div>
                  )}
                </div>
              </div>
            ))}

            {/* Pagination controls */}
            <div className="flex items-center justify-center space-x-4 mt-4">
              <button
                className="px-3 py-1 bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
              >
                Previous
              </button>

              <div className="text-sm text-gray-700">Page {page} of {pageCount}</div>

              <button
                className="px-3 py-1 bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                disabled={page >= pageCount}
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TestDataCard;

