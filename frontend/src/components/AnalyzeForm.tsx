import React, { useState } from "react";
import api from "../services/apiClient";

interface Props {
  onStart: (url: string) => void;
}

const AnalyzeForm: React.FC<Props> = ({ onStart }) => {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async () => {
    setError(null);
    if (!url) {
      setError("Please enter a URL to analyze.");
      return;
    }
    setLoading(true);
    try {
      await onStart(url);
    } catch (err: any) {
      setError(err?.message || "Failed to start analysis");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleAnalyze();
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 items-start">
      <input
        type="url"
        placeholder="https://example.com"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        className="flex-1 px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />
      <button
        type="submit"
        disabled={loading}
        className="bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700 disabled:opacity-50"
      >
        {loading ? "Analyzing..." : "Analyze"}
      </button>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </form>
  );
};

export default AnalyzeForm;
