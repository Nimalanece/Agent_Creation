import React from "react";
import { AnalysisResult } from "../types/api";

interface Props {
  data?: AnalysisResult | null;
}

const AnalysisCard: React.FC<Props> = ({ data }) => {
  if (!data) {
    return (
      <div className="bg-white shadow rounded-lg p-4">
        <h2 className="text-lg font-medium">Page Analysis</h2>
        <p className="text-sm text-gray-500">No analysis available yet.</p>
      </div>
    );
  }

  return (
    <div className="bg-white shadow rounded-lg p-4">
      <h2 className="text-lg font-medium">Page Analysis</h2>
      <p className="text-sm text-gray-600">{data.title}</p>
      <div className="mt-3 grid grid-cols-2 gap-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-700">Meta</h3>
          <p className="text-sm text-gray-500">{data.meta_description || "—"}</p>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gray-700">Counts</h3>
          <ul className="text-sm text-gray-500">
            {data.counts &&
              Object.entries(data.counts).map(([k, v]) => (
                <li key={k}>
                  {k}: {v}
                </li>
              ))}
          </ul>
        </div>
      </div>

      <div className="mt-4">
        <h3 className="text-sm font-semibold text-gray-700">Top IDs</h3>
        <div className="flex flex-wrap gap-2 mt-2">
          {(data.ids || []).slice(0, 10).map((id) => (
            <span key={id} className="text-xs bg-gray-100 px-2 py-1 rounded">
              {id}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};

export default AnalysisCard;
