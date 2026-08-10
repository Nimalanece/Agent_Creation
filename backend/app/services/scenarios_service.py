import os
from typing import Dict, Any, List

from app.core.groq_service import GroqService, GroqServiceError

USE_AI_SCENARIOS = os.getenv("USE_AI_SCENARIOS", "false").lower() in ("1", "true", "yes")


def _build_fallback_scenarios(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Conservative, analysis-driven generator.

    Only create scenarios that are directly supported by elements present in the analysis JSON.
    Do NOT add generic or speculative scenarios. If the analysis does not contain evidence for a
    feature, do not generate scenarios for it.
    """
    forms = analysis.get("forms") or []
    inputs = analysis.get("inputs") or []
    buttons = analysis.get("buttons") or []
    links = analysis.get("links") or []
    selects = analysis.get("selects") or []
    title = (analysis.get("title") or "").strip()
    url = (analysis.get("url") or "")

    # Prefer a meaningful module name: page title > host
    module_name = ""
    if title:
        module_name = title
    elif url:
        try:
            module_name = url.split("/")[2]
        except Exception:
            module_name = url
    module_name = module_name or "Page"

    def build(idx: int, description: str, priority: str, mapping: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": f"s{idx}",
            "module": module_name,
            "test_scenario_id": f"TS_{idx:02d}",
            "title": description,
            "description": description,
            "priority": priority,
            "mapping": mapping,
        }

    def narrow_label(item: Dict[str, Any], fallback: str) -> str:
        label = str(item.get("label") or "").strip()
        if label:
            return label
        placeholder = str(item.get("placeholder") or "").strip()
        if placeholder:
            return placeholder
        value = str(item.get("name") or item.get("id") or item.get("text") or "").strip()
        return value or fallback

    def is_required(item: Dict[str, Any]) -> bool:
        return bool(item.get("required") or item.get("attrs", {}).get("required"))

    scenarios: List[Dict[str, Any]] = []
    seen = set()
    next_id = 1

    def add_scenario(description: str, priority: str, mapping: Dict[str, Any]):
        nonlocal next_id
        key = description.strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        scenarios.append(build(next_id, description, priority, mapping))
        next_id += 1

    if title or analysis.get("counts", {}).get("content_blocks", 0) > 0:
        desc = f"Verify the page loads and primary content (title: '{title}') is visible." if title else "Verify the page loads and primary content is visible."
        add_scenario(desc, "high", {"page": "load", "expected_title": title} if title else {"page": "load"})

    if len(forms) > 0:
        for i, form in enumerate(forms, start=1):
            form_id = form.get("id") or form.get("name") or f"form{i}"
            field_count = len(form.get("inputs", [])) if isinstance(form.get("inputs"), list) else 0
            add_scenario(
                f"Verify form '{form_id}' is present and contains {field_count} expected fields.",
                "high",
                {"form_id": form_id, "field_count": field_count},
            )

            if field_count > 0:
                add_scenario(
                    f"Verify form '{form_id}' can be submitted successfully with valid data.",
                    "high",
                    {"form_id": form_id, "mode": "submit-valid"},
                )

                if any(is_required(field) for field in form.get("inputs", [])) or any(field.get("type") in ("email", "tel", "url", "number") for field in form.get("inputs", [])):
                    add_scenario(
                        f"Verify form '{form_id}' shows validation feedback when required or invalid fields are submitted.",
                        "high",
                        {"form_id": form_id, "mode": "submit-invalid"},
                    )

    for i, inp in enumerate(inputs, start=1):
        label = narrow_label(inp, f"input{i}")
        itype = str(inp.get("type") or "text").strip().lower()
        mapping = {
            "name": inp.get("name"),
            "id": inp.get("id"),
            "type": itype,
            "selector": inp.get("selector"),
        }
        add_scenario(
            f"Verify input field '{label}' of type '{itype}' is present and accepts input.",
            "medium",
            mapping,
        )
        if is_required(inp):
            add_scenario(
                f"Verify required input field '{label}' shows an error when left blank.",
                "high",
                mapping,
            )
        if itype in ("email", "tel", "url", "number"):
            add_scenario(
                f"Verify input field '{label}' rejects invalid {itype} values.",
                "high",
                mapping,
            )
        if inp.get("pattern") or inp.get("format"):
            add_scenario(
                f"Verify input field '{label}' enforces the expected pattern or format.",
                "high",
                mapping,
            )

    for i, sel in enumerate(selects, start=1):
        label = narrow_label(sel, f"select{i}")
        options = sel.get("options") or []
        mapping = {
            "select_id": sel.get("id") or sel.get("name"),
            "selector": sel.get("selector"),
            "option_count": len(options),
        }
        add_scenario(
            f"Verify dropdown '{label}' allows selecting from {len(options)} available options.",
            "medium",
            mapping,
        )
        if sel.get("multiple"):
            add_scenario(
                f"Verify multi-select dropdown '{label}' allows selecting multiple options.",
                "medium",
                mapping,
            )

    for i, btn in enumerate(buttons, start=1):
        text = narrow_label(btn, f"button{i}")
        mapping = {
            "id": btn.get("id"),
            "text": btn.get("text"),
            "selector": btn.get("selector"),
        }
        add_scenario(
            f"Verify button/CTA '{text}' is visible and triggers the expected action.",
            "high",
            mapping,
        )

    for i, lk in enumerate(links, start=1):
        href = lk.get("href")
        if not href:
            continue
        text = narrow_label(lk, f"link{i}")
        add_scenario(
            f"Verify link '{text}' navigates to '{href}'.",
            "medium",
            {"href": href, "selector": lk.get("selector")},
        )

    if len(selects) == 0 and len(inputs) == 0 and len(buttons) == 0 and len(links) == 0 and len(forms) == 0:
        add_scenario(
            "Verify the page loads and visible content renders correctly.",
            "high",
            {"page": "load"},
        )

    has_password = any(isinstance(inp, dict) and inp.get("type") == "password" for inp in inputs)
    if has_password or ("login" in (url or "").lower()):
        add_scenario(
            "Verify authentication flow handles invalid credentials with an appropriate error message.",
            "high",
            {"page": "auth"},
        )

    return scenarios


def _normalize_scenarios(parsed: Any, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(parsed, dict) and isinstance(parsed.get("scenarios"), list):
        scenarios = parsed["scenarios"]
    elif isinstance(parsed, list):
        scenarios = parsed
    else:
        scenarios = []

    normalized = []
    seen_ids = set()
    seen_descriptions = set()

    def normalize_item(item: Dict[str, Any], index: int) -> Dict[str, Any]:
        description = str(item.get("description") or item.get("title") or "").strip()
        module = str(item.get("module") or item.get("Module") or "General").strip() or "General"
        test_scenario_id = str(item.get("test_scenario_id") or item.get("TestScenarioId") or item.get("id") or f"TS_{index:02d}").strip() or f"TS_{index:02d}"
        return {
            "id": item.get("id") or f"s{index}",
            "module": module,
            "test_scenario_id": test_scenario_id,
            "title": description,
            "description": description or f"Scenario {test_scenario_id}",
            "priority": item.get("priority") or "medium",
            "mapping": item.get("mapping") or {},
        }

    for idx, item in enumerate(scenarios, start=1):
        if not isinstance(item, dict):
            continue
        description = str(item.get("description") or item.get("title") or "").strip()
        if not description:
            continue
        normalized_item = normalize_item(item, idx)
        lower_desc = normalized_item["description"].lower()
        if lower_desc in seen_descriptions:
            continue
        seen_descriptions.add(lower_desc)
        normalized.append(normalized_item)

    # If the model produced no usable scenarios, fall back to conservative, analysis-driven generation.
    if not normalized:
        normalized = _build_fallback_scenarios(analysis)

    return normalized

    return normalized


async def generate_scenarios(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Generate scenarios from analysis JSON.

    By default, this uses a deterministic, analysis-driven generator to avoid
    hallucinated scenarios and keep results grounded in observed page elements.
    If USE_AI_SCENARIOS is enabled, it may attempt an optional Groq call as a
    secondary step, but it will fall back to the deterministic generator for
    reliable results.
    """
    if USE_AI_SCENARIOS:
        groq = GroqService()
        try:
            parsed = await groq.generate_scenarios(analysis)
            normalized = _normalize_scenarios(parsed, analysis)
            if normalized:
                return {"scenarios": normalized}
        except GroqServiceError:
            pass

    return {"scenarios": _build_fallback_scenarios(analysis)}
