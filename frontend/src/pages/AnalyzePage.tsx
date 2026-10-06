import React from "react";
import Header from "../components/Header";
import AnalyzeForm from "../components/AnalyzeForm";
import ScenariosCard from "../components/ScenariosCard";
import TestCasesCard from "../components/TestCasesCard";
import TestDataCard from "../components/TestDataCard";
import DemoInsightsCard from "../components/DemoInsightsCard";
import SeleniumCodeCard from "../components/SeleniumCodeCard";
import { useFullAnalysis } from "../hooks/useFullAnalysis";

const AnalyzePage: React.FC = () => {
  const { data: result, loading, error, run: handleStart } = useFullAnalysis();
  const scenarioCount = result?.scenarios?.length || 0;
  const testCaseCount = result?.testcases?.length || 0;
  const hasResult = Boolean(result);
  const pipeline = [
    { label: "Upload", detail: "Target URL", icon: "01", status: "Ready" },
    { label: "Agent 1", detail: "Scenario analysis", icon: "02", status: hasResult ? "Complete" : "Waiting" },
    { label: "Agent 2", detail: "Test data generation", icon: "03", status: hasResult ? "Complete" : "Waiting" },
    { label: "Agent 3", detail: "Selenium generation", icon: "04", status: "Ready" },
    { label: "Results", detail: "Review and export", icon: "05", status: hasResult ? "Available" : "Waiting" },
  ];

  return (
    <div className="app-shell">
      <Header />
      <main className="app-main mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        <section className="surface-card overflow-hidden p-6 sm:p-8">
          <div className="max-w-3xl">
            <div className="dashboard-kicker">AI test workspace</div>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-white sm:text-4xl">Turn any web experience into test intelligence.</h2>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">Analyze a target URL, map its behaviors, synthesize test data, and generate production-ready Selenium coverage.</p>
          </div>
          <div className="mt-7 rounded-2xl border border-slate-700/50 bg-slate-950/30 p-3 sm:p-4">
            <AnalyzeForm onStart={handleStart} />
            {loading && <p className="mt-3 text-sm text-blue-300">Running full pipeline...</p>}
            {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
          </div>
        </section>

        <section className="surface-card p-5 sm:p-6">
          <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-end">
            <div><div className="dashboard-kicker">Execution graph</div><h2 className="mt-1 text-xl font-semibold text-white">Agent pipeline</h2></div>
            <span className="text-xs text-slate-500">Live workflow status</span>
          </div>
          <div className="pipeline-track mt-6 grid grid-cols-5 gap-2 sm:gap-4">
            {pipeline.map((step) => (
              <div className="pipeline-node text-center" key={step.label}>
                <div className="pipeline-icon text-xs font-bold">{step.icon}</div>
                <div className="truncate text-xs font-semibold text-slate-200 sm:text-sm">{step.label}</div>
                <div className="mt-1 hidden text-[11px] text-slate-500 sm:block">{step.detail}</div>
                <div className={`mt-2 text-[10px] font-semibold uppercase tracking-wide ${step.status === "Waiting" ? "text-slate-500" : "text-green-400"}`}>{step.status}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            ["Scenarios", scenarioCount, "Mapped behaviors", "text-blue-300"],
            ["Test cases", testCaseCount, "Executable contracts", "text-violet-300"],
            ["Pipeline", hasResult ? "Ready" : "Idle", "System status", "text-amber-300"],
          ].map(([label, value, detail, color]) => (
            <div className="surface-card p-4" key={String(label)}><div className="text-xs text-slate-500">{label}</div><div className={`mt-2 text-2xl font-semibold ${color}`}>{value}</div><div className="mt-1 text-[11px] text-slate-500">{detail}</div></div>
          ))}
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ScenariosCard scenarios={result?.scenarios} />
          <TestCasesCard testcases={result?.testcases} />
        </section>

        <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <TestDataCard contract={result?.agent_2_contract} loading={loading} />
          <SeleniumCodeCard
            contract={result?.agent_1_contract}
            testData={result?.agent_2_contract}
            testcases={result?.testcases}
          />
        </section>

        {result?.defect_possibilities || result?.risk_areas || result?.recommended_smoke_tests ? (
          <section>
            <DemoInsightsCard
              defect_possibilities={result?.defect_possibilities}
              risk_areas={result?.risk_areas}
              recommended_smoke_tests={result?.recommended_smoke_tests}
            />
          </section>
        ) : null}
      </main>
    </div>
  );
};

export default AnalyzePage;
