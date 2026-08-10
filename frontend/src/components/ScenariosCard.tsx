import React, { useMemo, useState } from "react";
import { utils, writeFile } from "xlsx";
import { ScenarioItem } from "../types/api";

interface Props {
  scenarios?: ScenarioItem[] | null;
}

const PAGE_SIZES = [5, 10, 20];

const ScenariosCard: React.FC<Props> = ({ scenarios }) => {
  const items = scenarios || [];
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

  function exportScenarios() {
    const rows = items.map((scenario) => ({
      Module: scenario.module || "General",
      TestScenarioId: scenario.test_scenario_id || scenario.id,
      Description: scenario.description || scenario.title || "",
      Priority: scenario.priority || "",
      Mapping: scenario.mapping ? JSON.stringify(scenario.mapping) : "",
    }));

    const worksheet = utils.json_to_sheet(rows);
    const workbook = utils.book_new();
    utils.book_append_sheet(workbook, worksheet, "Scenarios");
    writeFile(workbook, "test-scenarios.xlsx");
  }

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

  return (
    <div className="bg-white shadow rounded-lg p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center">
        <div>
          <h2 className="text-lg font-medium">Test Scenarios</h2>
          <div className="text-sm text-gray-600">{total} scenarios</div>
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
          <button
            type="button"
            onClick={exportScenarios}
            className="px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700"
          >
            Export XLS
          </button>
          <label className="text-sm text-gray-600">Page size:</label>
          <select
            value={pageSize}
            onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
            className="border rounded px-2 py-1 text-sm"
            disabled={showAll}
          >
            {PAGE_SIZES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      {total === 0 ? (
        <p className="text-sm text-gray-500 mt-3">No scenarios generated yet.</p>
      ) : (
        <>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Module</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Test Scenario ID</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Priority</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {pageItems.map((s) => (
                  <React.Fragment key={s.id}>
                    <tr>
                      <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-700">{s.module || "General"}</td>
                      <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-700">{s.test_scenario_id || s.id}</td>
                      <td className="px-3 py-3 text-sm text-gray-700">{s.description || s.title || "No description available."}</td>
                      <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-700">{s.priority || "—"}</td>
                      <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-700">
                        <button
                          type="button"
                          onClick={() => toggleExpand(s.id)}
                          className="text-xs text-blue-600 hover:underline"
                        >
                          {expanded[s.id] ? "Hide details" : "Details"}
                        </button>
                      </td>
                    </tr>
                    {expanded[s.id] ? (
                      <tr>
                        <td colSpan={6} className="px-3 py-3 bg-gray-50 text-sm text-gray-700">
                          <div className="space-y-2">
                            <div>
                              <span className="font-medium">Description:</span> {s.description || s.title || "No description available."}
                            </div>
                            {s.mapping && Object.keys(s.mapping).length > 0 ? (
                              <div>
                                <span className="font-medium">Mapping:</span>
                                <pre className="mt-1 bg-white rounded border border-gray-200 p-2 text-xs overflow-x-auto">{JSON.stringify(s.mapping, null, 2)}</pre>
                              </div>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {!showAll && (
            <div className="mt-4 space-y-3">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-2">
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
                    className="w-20 border rounded px-2 py-1 text-sm"
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

export default ScenariosCard;
