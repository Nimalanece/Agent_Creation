import React, { useMemo, useState } from "react";

interface Props {
  data?: Record<string, any> | null;
}

const PAGE_SIZES = [4, 8, 12];

const TestDataCard: React.FC<Props> = ({ data }) => {
  const entries = data ? Object.entries(data) : [];
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZES[0]);
  const [page, setPage] = useState<number>(1);
  const [seekPage, setSeekPage] = useState<number>(1);
  const [showAll, setShowAll] = useState(false);

  const total = entries.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const pageItems = useMemo(() => {
    if (showAll) {
      return entries;
    }
    const start = (page - 1) * pageSize;
    return entries.slice(start, start + pageSize);
  }, [entries, page, pageSize, showAll]);

  function goto(p: number) {
    const target = Math.min(Math.max(1, p), totalPages);
    setPage(target);
    setSeekPage(target);
  }

  function handleJump() {
    goto(seekPage);
  }

  return (
    <div className="bg-white shadow rounded-lg p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center">
        <div>
          <h2 className="text-lg font-medium">Test Data</h2>
          <div className="text-sm text-gray-600">{total} items</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setShowAll((prev) => !prev)}
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
        <p className="text-sm text-gray-500 mt-3">No test data available.</p>
      ) : (
        <>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
            {pageItems.map(([k, v]) => (
              <div key={k} className="border rounded p-3">
                <h3 className="text-sm font-semibold">{k}</h3>
                <pre className="text-xs text-gray-700 mt-2 whitespace-pre-wrap">{JSON.stringify(v, null, 2)}</pre>
              </div>
            ))}
          </div>

          {!showAll && (
            <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2">
                <button onClick={() => goto(page - 1)} disabled={page <= 1} className="px-3 py-1 bg-gray-100 rounded disabled:opacity-50">Prev</button>
                <span className="text-sm text-gray-600">Page {page} of {totalPages}</span>
                <button onClick={() => goto(page + 1)} disabled={page >= totalPages} className="px-3 py-1 bg-gray-100 rounded disabled:opacity-50">Next</button>
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
                <button onClick={handleJump} className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700">Go</button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default TestDataCard;
