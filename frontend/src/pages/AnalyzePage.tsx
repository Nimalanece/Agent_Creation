import React from "react";
import Header from "../components/Header";
import AnalyzeForm from "../components/AnalyzeForm";
import ScenariosCard from "../components/ScenariosCard";
import TestCasesCard from "../components/TestCasesCard";
import TestDataCard from "../components/TestDataCard";
import SeleniumCodeCard from "../components/SeleniumCodeCard";
import DemoInsightsCard from "../components/DemoInsightsCard";
import { useFullAnalysis } from "../hooks/useFullAnalysis";

const AnalyzePage: React.FC = () => {
  const { data: result, loading, error, run: handleStart } = useFullAnalysis();

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-6">
        <section className="bg-white shadow rounded-lg p-4">
          <h2 className="text-lg font-medium">Analyze a URL</h2>
          <p className="text-sm text-gray-500 mt-1">Enter a URL to analyze the page and generate tests.</p>
          <div className="mt-4">
            <AnalyzeForm onStart={handleStart} />
            {loading && <p className="text-sm text-gray-600 mt-2">Running full pipeline...</p>}
            {error && <p className="text-sm text-red-600 mt-2">{error}</p>}
          </div>
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ScenariosCard scenarios={result?.scenarios} />
          <TestCasesCard testcases={result?.testcases} />
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <TestDataCard data={result?.testdata} />
          <SeleniumCodeCard code={result?.selenium_code || null} />
        </section>

        {result?.defect_possibilities || result?.risk_areas || result?.automation_coverage_percent || result?.recommended_smoke_tests ? (
          <section>
            <DemoInsightsCard
              defect_possibilities={result?.defect_possibilities}
              risk_areas={result?.risk_areas}
              automation_coverage_percent={result?.automation_coverage_percent}
              recommended_smoke_tests={result?.recommended_smoke_tests}
            />
          </section>
        ) : null}
      </main>
    </div>
  );
};

export default AnalyzePage;
