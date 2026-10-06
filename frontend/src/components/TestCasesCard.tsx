import React, { useMemo, useState } from "react";
import { TestCaseItem } from "../types/api";

interface Props {
  testcases?: TestCaseItem[] | null;
}

const PAGE_SIZES = [5, 10, 20];

const TestCasesCard: React.FC<Props> = ({ testcases }) => {
  const items = testcases || [];
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZES[0]);
  const [page, setPage] = useState<number>(1);
  const [seekPage, setSeekPage] = useState<number>(1);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [showAll, setShowAll] = useState(false);

  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const pageItems = useMemo(() => {
    if (showAll) {
      return items;
    }
    const start = (page - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [items, page, pageSize, showAll]);

  const pageNumbers = useMemo(() => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    const windowStart = Math.max(2, Math.min(page - 2, totalPages - 4));
    const pages = [1];
    if (windowStart > 2) {
      pages.push(-1);
    }
    for (let i = windowStart; i < windowStart + 3 && i < totalPages; i += 1) {
      pages.push(i);
    }
    if (windowStart + 3 < totalPages) {
      pages.push(-1);
    }
    pages.push(totalPages);
    return pages;
  }, [page, totalPages]);

  function goto(p: number) {
    const target = Math.min(Math.max(1, p), totalPages);
    setPage(target);
    setSeekPage(target);
  }

  function handleJump() {
    goto(seekPage);
  }

  function toggleExpand(id: string) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  const formatKey = (k: string) => {
    // convert snake_case or camelCase to Title Case for labels
    const spaced = k.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[_-]/g, ' ');
    return spaced.replace(/\w\S*/g, (txt) => txt.charAt(0).toUpperCase() + txt.substr(1));
  };

  return (
    <div className="bg-white shadow rounded-lg p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center">
        <div>
          <h2 className="text-lg font-medium">Test Cases</h2>
          <div className="text-sm text-gray-600">{total} cases</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => {
              setShowAll((prev) => {
                const next = !prev;
                if (next) {
                  setPage(1);
                  setSeekPage(1);
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
            onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
            className="rounded-lg border border-slate-600/70 bg-slate-950/70 px-2 py-1 text-sm text-slate-200 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-500/20"
            disabled={showAll}
          >
            {PAGE_SIZES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      {total === 0 ? (
        <p className="text-sm text-gray-500 mt-3">No test cases generated yet.</p>
      ) : (
        <>
          <div className="mt-3 space-y-3">
            {pageItems.map((t) => {
              const id = t.id || t.test_case_id || t.scenario_id || t.title;
              const expandedKey = String(id);
              const expectedResults = t.expected_results?.length ? t.expected_results : (t.expected_result ? [typeof t.expected_result === 'string' ? t.expected_result : JSON.stringify(t.expected_result)] : []);

              return (
                <div key={expandedKey} className="border rounded p-3">
                  <div className="flex justify-between items-start gap-4">
                    <div>
                      <h3 className="text-sm font-semibold">{t.title}</h3>
                      {t.description && <p className="text-xs text-gray-500">{t.description}</p>}
                      <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-gray-500">
                        {t.test_type && <span className="bg-gray-50 px-2 py-1 rounded">{t.test_type}</span>}
                        {t.scenario_id && <span className="bg-gray-50 px-2 py-1 rounded">Scenario: {t.scenario_id}</span>}
                        {t.feature_id && <span className="bg-gray-50 px-2 py-1 rounded">Feature: {t.feature_id}</span>}
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <span className="text-xs bg-gray-100 px-2 py-1 rounded">{(t as any).priority || "—"}</span>
                      <button
                        onClick={() => toggleExpand(expandedKey)}
                        className="text-xs text-blue-600 hover:underline"
                      >
                        {expanded[expandedKey] ? "Collapse" : "Details"}
                      </button>
                    </div>
                  </div>

                  {expanded[expandedKey] ? (
                    <div className="mt-2 text-sm text-gray-600">
                      {t.preconditions && t.preconditions.length > 0 && (
                        <div>
                          <h4 className="text-xs font-medium">Preconditions</h4>
                          <ul className="text-sm text-gray-600 list-disc ml-5">
                            {t.preconditions.map((p, idx) => (
                              <li key={idx}>{p}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      <div className="mt-2">
                        <h4 className="text-xs font-medium">Steps</h4>
                        <div className="mt-2 max-h-64 md:max-h-96 overflow-y-auto overflow-x-hidden pr-2 space-y-3">
                          {t.steps.map((stepObj: any, idx: number) => {
                            const stepNumber = stepObj.step_number ?? (idx + 1);
                            const keys = Object.keys(stepObj).filter((k) => k !== 'step_number');
                            return (
                              <div key={idx} className="bg-white border rounded-lg p-3 shadow-sm">
                                <div className="flex justify-between items-center">
                                  <div className="text-sm font-semibold">Step {stepNumber}</div>
                                  <div className="text-xs text-gray-500">{stepObj.action || ''}</div>
                                </div>
                                <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm text-gray-700">
                                  {keys.map((key) => (
                                    <div key={key} className="break-words">
                                      <div className="text-xs text-gray-500">{formatKey(key)}:</div>
                                      <div className="whitespace-pre-wrap break-words text-sm text-gray-800">{String(stepObj[key] ?? '')}</div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {t.input_fields && t.input_fields.length > 0 && (
                        <div className="mt-2">
                          <h4 className="text-xs font-medium">Input Fields</h4>
                          <p className="text-sm text-gray-600">{t.input_fields.join(", ")}</p>
                        </div>
                      )}

                      {t.required_data && t.required_data.length > 0 && (
                        <div className="mt-2">
                          <h4 className="text-xs font-medium">Required Data</h4>
                          <div className="space-y-2">
                            {t.required_data.map((rd, idx) => (
                              <div key={idx} className="bg-gray-50 border rounded p-2">
                                <div className="font-medium text-gray-800">{rd.field_name}</div>
                                <div className="text-xs text-gray-600">Type: {rd.field_type} | Format: {rd.expected_format}</div>
                                <div className="text-xs text-gray-600">Purpose: {rd.business_purpose}</div>
                                <div className="text-xs text-gray-600">Rules: {rd.validation_rules.join(", ")}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {t.automation_hints && (
                        <div className="mt-2">
                          <h4 className="text-xs font-medium">Automation Hints</h4>
                          <div className="bg-gray-50 border rounded p-2 text-xs">
                            <div><span className="font-medium">Page:</span> {t.automation_hints.page_name}</div>
                            <div><span className="font-medium">Actions:</span> {t.automation_hints.actions.join(", ") || "—"}</div>
                            <div><span className="font-medium">Assertions:</span> {t.automation_hints.assertions.join(", ") || "—"}</div>
                          </div>
                        </div>
                      )}

                      {expectedResults.length > 0 && (
                        <div className="mt-2">
                          <h4 className="text-xs font-medium">Expected Results</h4>
                          <ul className="text-sm text-gray-600 list-disc ml-5">
                            {expectedResults.map((er, idx) => (
                              <li key={idx}>{er}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {t.mapping && Object.keys(t.mapping).length > 0 && (
                        <div className="mt-2">
                          <h4 className="text-xs font-medium">Mapping</h4>
                          <pre className="text-xs bg-gray-50 border rounded p-2 overflow-x-auto">{JSON.stringify(t.mapping, null, 2)}</pre>
                        </div>
                      )}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>

          {!showAll && (
            <div className="mt-4 space-y-3">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => goto(page - 1)}
                    disabled={page <= 1}
                    className="px-3 py-1 bg-gray-100 rounded disabled:opacity-50"
                  >
                    Prev
                  </button>
                  {pageNumbers.map((num, idx) =>
                    num === -1 ? (
                      <span key={`gap-${idx}`} className="text-sm text-gray-500">…</span>
                    ) : (
                      <button
                        key={num}
                        onClick={() => goto(num)}
                        className={`px-3 py-1 rounded ${num === page ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-700"}`}
                      >
                        {num}
                      </button>
                    )
                  )}
                  <button
                    onClick={() => goto(page + 1)}
                    disabled={page >= totalPages}
                    className="px-3 py-1 bg-gray-100 rounded disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-600">Jump to page:</span>
                  <input
                    type="number"
                    min={1}
                    max={totalPages}
                    value={seekPage}
                    onChange={(e) => setSeekPage(Number(e.target.value))}
                    className="w-20 rounded-lg border border-slate-600/70 bg-slate-950/70 px-2 py-1 text-sm text-slate-200 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-500/20"
                  />
                  <button
                    onClick={handleJump}
                    className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                  >
                    Go
                  </button>
                </div>
              </div>
              <div className="text-sm text-gray-500">Page {page} of {totalPages}</div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default TestCasesCard;
