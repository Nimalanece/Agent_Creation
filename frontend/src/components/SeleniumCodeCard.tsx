import React, { useState } from "react";
import { downloadSeleniumCode } from "../services/downloadService";

interface Props {
  code?: string | null;
}

const SeleniumCodeCard: React.FC<Props> = ({ code }) => {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async () => {
    if (!code) return;
    setError(null);
    setDownloading(true);
    try {
      const blob = await downloadSeleniumCode(code);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "test_generated.py";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Failed to download file");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="bg-white shadow rounded-lg p-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-medium">Selenium Code</h2>
        {code && (
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="ml-4 bg-green-600 text-white px-3 py-1 rounded hover:bg-green-700 disabled:opacity-50 text-sm"
          >
            {downloading ? "Downloading..." : "Download Script"}
          </button>
        )}
      </div>

      {!code ? (
        <p className="text-sm text-gray-500 mt-3">No selenium code generated yet.</p>
      ) : (
        <div className="mt-3">
          <pre className="bg-gray-900 text-white text-xs p-3 rounded overflow-x-auto whitespace-pre">
            {code}
          </pre>
        </div>
      )}

      {error && <p className="text-sm text-red-600 mt-2">{error}</p>}
    </div>
  );
};

export default SeleniumCodeCard;
