from typing import Any, Dict, List

CATEGORIES = [
    "page_load",
    "navigation",
    "form_structure",
    "form_submission_positive",
    "form_submission_negative",
    "validation",
    "input_field",
    "button_action",
    "checkbox",
    "radio_button",
    "file_upload",
    "search",
    "update",
]


def _contains_any(text: str, tokens: List[str]) -> bool:
    t = (text or "").lower()
    return any(tok in t for tok in tokens)


def classify_scenario(description: str, test_type: str = None, mapping: Dict[str, Any] = None, analysis: Dict[str, Any] = None) -> str:
    """Classify a single scenario into one of the supported categories.

    Uses description, test_type, mapping (mapping.mode), and page analysis metadata.
    Falls back to 'input_field' when uncertain.
    """
    mapping = mapping or {}
    analysis = analysis or {}
    desc = (description or "").lower()
    tt = (test_type or "").lower()
    mode = str(mapping.get("mode") or "").lower()

    # Direct mapping from mode
    if mode == "submit-valid":
        return "form_submission_positive"
    if mode == "submit-invalid":
        return "form_submission_negative"

    # Page load
    if _contains_any(desc, ["page load", "page loads", "loads successfully", "page is visible", "renders correctly"]) or tt == "functional":
        # if page contains many inputs, it's likely form_structure
        forms = analysis.get("forms") or []
        if forms:
            return "form_structure"
        return "page_load"

    # Navigation
    if _contains_any(desc, ["navigate", "navigation", "redirect", "route", "link to", "click the link", "url contains"]) or tt == "navigation":
        return "navigation"

    # Form submission positive/negative
    if _contains_any(desc, ["submit", "submitted", "submission", "success", "success message"]) or tt in ("positive", "success"):
        if _contains_any(desc, ["invalid", "error", "validation", "reject", "cannot", "fails", "error message"]) or tt in ("negative", "validation"):
            return "form_submission_negative"
        return "form_submission_positive"

    # Validation
    if _contains_any(desc, ["validation", "required", "error message", "show validation", "validation feedback", "required field", "cannot be empty"]):
        return "validation"

    # Search
    if _contains_any(desc, ["search", "find", "query", "result list"]):
        return "search"

    # File upload
    if _contains_any(desc, ["upload", "file", "choose file", "drag and drop"]):
        return "file_upload"

    # Checkbox
    if _contains_any(desc, ["checkbox", "check", "checked", "unchecked"]) or (mapping and (mapping.get("type") == "checkbox" or mapping.get("element_type") == "checkbox")):
        return "checkbox"

    # Radio button
    if _contains_any(desc, ["radio", "select option", "choose option"]) or (mapping and (mapping.get("type") == "radio" or mapping.get("element_type") == "radio")):
        return "radio_button"

    # Button action
    if _contains_any(desc, ["button", "cta", "click", "click the", "trigger the action"]) or (mapping and (mapping.get("element_type") == "button" or mapping.get("tag_name") == "button")):
        return "button_action"

    # Input field
    if _contains_any(desc, ["field", "input", "enter", "accepts input", "accepts"]) or (mapping and (mapping.get("element_type") in ("input", "textarea") or mapping.get("type") in ("text", "email", "tel", "number"))):
        # Distinguish form_structure when mapping indicates a form
        if mapping and (mapping.get("form_name") or mapping.get("form_id") or mapping.get("form")):
            return "form_structure"
        return "input_field"

    # Update
    if _contains_any(desc, ["update", "modify", "edit", "save changes"]):
        return "update"

    # Fallback
    return "input_field"


def classify_analysis(analysis: Dict[str, Any]) -> Dict[str, str]:
    """Classify detected page elements and produce an intent map.

    Returns a dict mapping element identifiers (id/name/selector) to a best-guess category.
    """
    map_out: Dict[str, str] = {}
    if not isinstance(analysis, dict):
        return map_out

    # Forms
    for form in (analysis.get("forms") or []):
        key = form.get("id") or form.get("name") or form.get("selector") or f"form_{len(map_out)+1}"
        map_out[str(key)] = "form_structure"
        for field in form.get("inputs") or []:
            fk = field.get("id") or field.get("name") or field.get("selector") or f"field_{len(map_out)+1}"
            # classify by field type
            ftype = str(field.get("type") or "").lower()
            if ftype in ("email", "tel", "url"):
                map_out[str(fk)] = "input_field"
            elif ftype == "checkbox":
                map_out[str(fk)] = "checkbox"
            elif ftype == "radio":
                map_out[str(fk)] = "radio_button"
            elif ftype == "file":
                map_out[str(fk)] = "file_upload"
            else:
                map_out[str(fk)] = "input_field"

    # Inputs not in forms
    for inp in (analysis.get("inputs") or []):
        key = inp.get("id") or inp.get("name") or inp.get("selector") or f"input_{len(map_out)+1}"
        itype = str(inp.get("type") or "").lower()
        if itype == "search":
            map_out[str(key)] = "search"
        elif itype == "checkbox":
            map_out[str(key)] = "checkbox"
        elif itype == "radio":
            map_out[str(key)] = "radio_button"
        elif itype == "file":
            map_out[str(key)] = "file_upload"
        else:
            map_out[str(key)] = "input_field"

    # Buttons
    for btn in (analysis.get("buttons") or []):
        key = btn.get("id") or btn.get("name") or btn.get("selector") or f"button_{len(map_out)+1}"
        map_out[str(key)] = "button_action"

    # Links
    for lk in (analysis.get("links") or []):
        key = lk.get("href") or lk.get("selector") or lk.get("id") or lk.get("name") or f"link_{len(map_out)+1}"
        map_out[str(key)] = "navigation"

    # If nothing found, mark page_load
    if not map_out:
        map_out["page"] = "page_load"

    return map_out


# Utility: extract an element name from mapping or description
def extract_element_name(mapping: Dict[str, Any] = None, title: str = None, raw_text: str = None) -> str:
    mapping = mapping or {}
    # Priority: mapping.label, mapping.field_name, mapping.text, mapping.name, mapping.id
    for key in ("label", "field_name", "text", "name", "id"):
        val = mapping.get(key) if isinstance(mapping, dict) else None
        if isinstance(val, str) and val.strip():
            return val.strip()

    # Try to extract quoted name from title/description: e.g., Verify link 'Login' navigates
    if isinstance(title, str) and title:
        import re
        m = re.search(r"['\"]([^'\"]+)['\"]", title)
        if m:
            return m.group(1).strip()
        # fallback: look for patterns like Verify link Login
        m2 = re.search(r"verify\s+(?:link|button|field|input)\s+([A-Za-z0-9 _-]+)", title.lower())
        if m2:
            return m2.group(1).strip().title()

    # Try raw_text
    if isinstance(raw_text, str) and raw_text:
        import re
        m = re.search(r"['\"]([^'\"]+)['\"]", raw_text)
        if m:
            return m.group(1).strip()

    return None
