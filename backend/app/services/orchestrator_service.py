import logging
from typing import Any, Dict

from app.services.url_analysis_service import analyze_url, URLAnalysisError
from app.services.scenarios_service import generate_scenarios
from app.services.testcases_service import generate_testcases
from app.services.testdata_service import generate_testdata
from app.services.selenium_service import generate_selenium_bundle
from app.core.groq_service import GroqServiceError, GroqService

LOGGER = logging.getLogger(__name__)


def _extract_discovered_locators(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Return the exact DOM-derived selectors that were used to build the generated tests."""
    def normalize_item(item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        selector = item.get("selector") or item.get("css") or item.get("id") or item.get("name")
        return {
            "tag": item.get("tag") or item.get("kind") or item.get("type") or "",
            "id": item.get("id") or "",
            "name": item.get("name") or "",
            "type": item.get("type") or "",
            "text": item.get("text") or "",
            "placeholder": item.get("placeholder") or "",
            "href": item.get("href") or "",
            "selector": selector or "",
        }

    inputs = [normalize_item(item) for item in (analysis.get("inputs") or [])]
    buttons = [normalize_item(item) for item in (analysis.get("buttons") or [])]
    links = [normalize_item(item) for item in (analysis.get("links") or [])]
    forms = []
    for form in analysis.get("forms") or []:
        if not isinstance(form, dict):
            continue
        fields = [normalize_item(field) for field in (form.get("inputs") or [])]
        forms.append({
            "id": form.get("id") or "",
            "name": form.get("name") or "",
            "selector": form.get("selector") or form.get("id") or form.get("name") or "form",
            "fields": fields,
        })
    headings = []
    for heading in analysis.get("headings") or []:
        if isinstance(heading, dict):
            headings.append(normalize_item(heading))
    return {
        "forms": forms,
        "inputs": inputs,
        "buttons": buttons,
        "links": links,
        "headings": headings,
    }


async def run_full_pipeline(url: str, render_js: bool = False) -> Dict[str, Any]:
    """Run the full analysis and generation pipeline.

    Steps:
      1. Analyze URL -> analysis JSON
      2. Generate scenarios from analysis -> scenarios list
      3. Generate testcases from scenarios -> testcases list
      4. Generate testdata from testcases -> testdata dict
      5. Generate selenium code bundle from artifacts -> files dict

    Returns a dict matching the required response shape.
    """
    # 1. Analyze
    try:
        analysis = await analyze_url(url, render_js=render_js)
    except URLAnalysisError as e:
        LOGGER.exception("URL analysis failed: %s", e)
        raise

    # 2. Scenarios
    try:
        scenarios_resp = await generate_scenarios(analysis)
        scenarios = scenarios_resp.get("scenarios") if isinstance(scenarios_resp, dict) else scenarios_resp
    except GroqServiceError as e:
        LOGGER.exception("Scenario generation failed: %s", e)
        raise

    # 3. Testcases
    try:
        testcases_resp = await generate_testcases(scenarios)
        testcases = testcases_resp.get("testcases") if isinstance(testcases_resp, dict) else testcases_resp
    except GroqServiceError as e:
        LOGGER.exception("Testcase generation failed: %s", e)
        raise

    # 4. Test data
    try:
        testdata = await generate_testdata(testcases, analysis=analysis)
    except GroqServiceError as e:
        LOGGER.exception("Testdata generation failed: %s", e)
        raise

    # 5. Selenium code
    try:
        selenium_bundle = await generate_selenium_bundle(
            testcases,
            testdata=testdata,
            scenarios=scenarios,
            analysis=analysis,
        )
        files = selenium_bundle.get("files") if isinstance(selenium_bundle, dict) else {}
        if not isinstance(files, dict):
            LOGGER.warning("Selenium bundle files payload is invalid or missing; using empty fallback.")
            files = {}
    except GroqServiceError as e:
        LOGGER.exception("Selenium generation failed: %s", e)
        raise

    # Combine code files into a single string for convenience.
    # If the bundle is unexpectedly empty, build a deterministic fallback so the UI
    # still receives actual Selenium pytest code instead of an empty string.
    combined_code_parts = []
    for path, content in files.items():
        if not isinstance(content, str):
            continue
        combined_code_parts.append(f"# ---- FILE: {path} ----\n")
        combined_code_parts.append(content)
        combined_code_parts.append("\n\n")
    combined_code = "".join(combined_code_parts).strip()

    if not combined_code:
        try:
            fallback_code = selenium_bundle.get("files", {}).get("tests/test_generated.py") or selenium_bundle.get("files", {}).get("generated_selenium.py")
            if not fallback_code:
                from app.services.selenium_service import _build_selenium_code_from_analysis
                fallback_code = _build_selenium_code_from_analysis(testcases, testdata=testdata, analysis=analysis, scenarios=scenarios)
            if fallback_code:
                combined_code = fallback_code
                files = {"tests/test_generated.py": fallback_code}
        except Exception:
            LOGGER.exception("Failed to synthesize fallback Selenium code for UI output")

    result: Dict[str, Any] = {
        "analysis": analysis,
        "scenarios": scenarios,
        "testcases": testcases,
        "testdata": testdata,
        "discovered_locators": _extract_discovered_locators(analysis),
        "selenium_code": combined_code,
        "selenium_files": files,
    }

    # Demo Mode: for known demo domains like saucedemo.com, generate additional insights
    try:
        if "saucedemo.com" in (url or ""):
            groq = GroqService()
            artifacts = {"analysis": analysis, "scenarios": scenarios, "testcases": testcases, "testdata": testdata}
            demo_insights = await groq.generate_demo_insights(artifacts)
            # Expect keys: defect_possibilities, risk_areas, automation_coverage_percent, recommended_smoke_tests
            if isinstance(demo_insights, dict):
                result.update(demo_insights)
                result["demo_insights"] = demo_insights
    except GroqServiceError as e:
        # Log and continue without failing the whole pipeline
        LOGGER.exception("Demo insights generation failed: %s", e)

    return result
