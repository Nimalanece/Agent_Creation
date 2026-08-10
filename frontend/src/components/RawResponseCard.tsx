import React from "react";

interface Props {
  data?: any | null;
}

const RawResponseCard: React.FC<Props> = ({ data }) => {
  function downloadJson() {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "analysis_response.json";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  }

  return (
    <div className="bg-white shadow rounded-lg p-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-medium">Raw Analysis Response</h2>
        <button
          onClick={downloadJson}
          disabled={!data}
          className="ml-4 bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700 disabled:opacity-50 text-sm"
        >
          Download JSON
        </button>
      </div>

      {data ? (
        <pre className="mt-3 bg-gray-900 text-white text-xs p-3 rounded overflow-x-auto whitespace-pre">
          {JSON.stringify(data, null, 2)}
        </pre>
      ) : (
        <p className="text-sm text-gray-500 mt-3">No analysis result yet.</p>
      )}
    </div>
  );
};

export default RawResponseCard;
