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
        <p className="text-sm text-gray-500 mt-3">No test cases generated yet.</p>
      ) : (
        <>
          <div className="mt-3 space-y-3">
            {pageItems.map((t) => (
              <div key={t.id} className="border rounded p-3">
                <div className="flex justify-between items-start gap-4">
                  <div>
                    <h3 className="text-sm font-semibold">{t.title}</h3>
                    {t.description && <p className="text-xs text-gray-500">{t.description}</p>}
                  </div>
                  <div className="flex items-start gap-3">
                    <span className="text-xs bg-gray-100 px-2 py-1 rounded">{(t as any).priority || "—"}</span>
                    <button
                      onClick={() => toggleExpand(t.id)}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      {expanded[t.id] ? "Collapse" : "Details"}
                    </button>
                  </div>
                </div>

                {expanded[t.id] ? (
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
                      <ol className="text-sm text-gray-600 list-decimal ml-5">
                        {t.steps.map((s, idx) => (
                          <li key={idx}>{JSON.stringify(s)}</li>
                        ))}
                      </ol>
                    </div>

                    {t.expected_result && (
                      <div className="mt-2">
                        <h4 className="text-xs font-medium">Expected</h4>
                        <p className="text-sm text-gray-600">{JSON.stringify(t.expected_result)}</p>
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            ))}
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

export default TestCasesCard;
