import React from "react";
import { DemoInsight } from "../types/api";

interface Props {
  defect_possibilities?: DemoInsight[] | null;
  risk_areas?: Array<string | { area?: string; reason?: string }> | null;
  recommended_smoke_tests?: string[] | null;
}

const DemoInsightsCard: React.FC<Props> = ({
  defect_possibilities,
  risk_areas,
  recommended_smoke_tests,
}) => {
  return (
    <div className="bg-white shadow rounded-lg p-4">
      <h2 className="text-lg font-medium">Demo Insights (saucedemo)</h2>

      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="border rounded p-3">
          <h3 className="text-sm font-semibold">Defect Possibilities</h3>
          {!defect_possibilities || defect_possibilities.length === 0 ? (
            <p className="text-sm text-gray-500">No defects identified.</p>
          ) : (
            <ul className="text-sm text-gray-600 mt-2 space-y-2">
              {defect_possibilities.map((d, idx) => (
                <li key={idx}>
                  <strong>{d.id || `def-${idx + 1}`}</strong>: {d.description} <em>({d.likelihood})</em>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="border rounded p-3">
          <h3 className="text-sm font-semibold">Risk Areas</h3>
          {!risk_areas || risk_areas.length === 0 ? (
            <p className="text-sm text-gray-500">No risk areas identified.</p>
          ) : (
            <ul className="text-sm text-gray-600 mt-2 list-disc ml-5">
              {risk_areas.map((r, idx) => (
                <li key={idx}>{typeof r === "string" ? r : `${r.area || ""} - ${r.reason || ""}`}</li>
              ))}
            </ul>
          )}
        </div>

        <div className="border rounded p-3">
          <h3 className="text-sm font-semibold">Recommended Smoke Tests</h3>
          {!recommended_smoke_tests || recommended_smoke_tests.length === 0 ? (
            <p className="text-sm text-gray-500">No recommendations.</p>
          ) : (
            <ul className="text-sm text-gray-600 mt-2 list-disc ml-5">
              {recommended_smoke_tests.map((s, idx) => (
                <li key={idx}>{s}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};

export default DemoInsightsCard;
