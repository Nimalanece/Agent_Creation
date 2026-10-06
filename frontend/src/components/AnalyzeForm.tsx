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
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-start">
      <input
        type="url"
        placeholder="https://example.com"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        className="min-h-12 flex-1 rounded-xl border border-slate-600/70 bg-slate-950/60 px-4 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-blue-400 focus:ring-4 focus:ring-blue-500/10"
      />
      <button
        type="submit"
        disabled={loading}
        className="min-h-12 rounded-xl bg-gradient-to-r from-blue-500 to-violet-500 px-6 text-sm font-semibold text-white shadow-lg shadow-blue-500/20 hover:from-blue-400 hover:to-violet-400 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "Analyzing..." : "Analyze"}
      </button>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </form>
  );
};

export default AnalyzeForm;
