from typing import Any, Dict, List

from app.core.groq_service import GroqService, GroqServiceError


def _extract_scenario_list(scenarios: Any) -> List[Dict[str, Any]]:
    if isinstance(scenarios, dict):
        candidate = scenarios.get("scenarios")
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    if isinstance(scenarios, list):
        return [item for item in scenarios if isinstance(item, dict)]
    return []


def _build_fallback_testcases(scenarios: Any) -> List[Dict[str, Any]]:
    scenario_items = _extract_scenario_list(scenarios)
    if not scenario_items:
        return [
            {
                "id": "fallback-t1",
                "title": "Verify page renders",
                "description": "Ensure the target page renders without errors.",
                "preconditions": [],
                "steps": [{"action": "open", "selector": "", "value": ""}],
                "expected_result": {"status": "loaded"},
            }
        ]

    fallback_cases = []
    for index, scenario in enumerate(scenario_items, start=1):
        title = str(scenario.get("title") or f"Scenario {index}").strip()
        description = str(scenario.get("description") or f"Validate {title}").strip()
        case_id = f"t{index}"
        steps = [{"action": "open", "selector": "url", "value": ""}]
        lowered = title.lower()
        if "form" in lowered:
            steps.append({"action": "enter valid data", "selector": "input", "value": "valid-value"})
            steps.append({"action": "submit form", "selector": "button", "value": "submit"})
        elif "login" in lowered:
            steps.append({"action": "enter valid credentials", "selector": "input", "value": "valid-user"})
            steps.append({"action": "submit login form", "selector": "button", "value": "login"})
        elif "button" in lowered or "click" in lowered or "action" in lowered:
            steps.append({"action": "click the primary action", "selector": "button", "value": "primary"})
        elif "link" in lowered:
            steps.append({"action": "click the link", "selector": "a", "value": "link"})
        elif "input" in lowered:
            steps.append({"action": "enter sample input", "selector": "input", "value": "sample"})
        else:
            steps.append({"action": "verify visible content", "selector": "content", "value": "expected"})

        fallback_cases.append(
            {
                "id": case_id,
                "title": title,
                "description": description,
                "preconditions": ["The application is available", "The user has access to the target page"],
                "steps": steps,
                "expected_result": {"status": "completed", "scenario": title},
            }
        )

    return fallback_cases


def _normalize_testcases(parsed: Any, scenarios: Any) -> List[Dict[str, Any]]:
    if isinstance(parsed, dict) and isinstance(parsed.get("testcases"), list):
        candidates = parsed["testcases"]
    elif isinstance(parsed, list):
        candidates = parsed
    else:
        candidates = []

    normalized = []
    seen_titles = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        if title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())
        normalized.append(
            {
                "id": item.get("id") or f"t{len(normalized) + 1}",
                "title": title,
                "description": item.get("description") or f"Validate {title}",
                "preconditions": item.get("preconditions") or [],
                "steps": item.get("steps") or [{"action": "observe", "selector": "", "value": ""}],
                "expected_result": item.get("expected_result") or {"status": "completed"},
            }
        )

    target_count = max(8, len(_extract_scenario_list(scenarios)))
    if len(normalized) < target_count:
        fallback_cases = _build_fallback_testcases(scenarios)
        for case in fallback_cases:
            case_title = str(case.get("title") or "").lower()
            if any(existing.get("title", "").lower() == case_title for existing in normalized):
                continue
            normalized.append(case)
            if len(normalized) >= target_count:
                break

    if len(normalized) < target_count:
        return _build_fallback_testcases(scenarios)

    return normalized


async def generate_testcases(scenarios: Any) -> Dict[str, Any]:
    """Generate detailed test cases from scenarios using GroqService.

    Args:
        scenarios: The scenarios data (list or dict) produced by the scenarios generator.

    Returns:
        Dict with key "testcases": [ ... ]

    Raises:
        GroqServiceError if the LLM fails or returns unexpected output.
    """
    groq = GroqService()
    try:
        parsed = await groq.generate_testcases(scenarios)
    except GroqServiceError:
        return {"testcases": _build_fallback_testcases(scenarios)}

    normalized = _normalize_testcases(parsed, scenarios)
    return {"testcases": normalized}
