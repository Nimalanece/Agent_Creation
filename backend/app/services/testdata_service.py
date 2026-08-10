import os
import re
from typing import Any, Dict, Iterable, List, Optional

USE_AI_TESTDATA = os.getenv("USE_AI_TESTDATA", "false").lower() in ("1", "true", "yes")


def _normalize_field_key(value: Optional[str]) -> str:
    if not value:
        return "field"
    raw = str(value).strip().lower()
    # Prefer the meaningful part of common selectors like input#username or [name="email"].
    if "#" in raw:
        raw = raw.split("#", 1)[1]
    elif re.search(r"\b(name|id)\s*=\s*['\"]?[^'\"]+['\"]?", raw):
        match = re.search(r"\b(name|id)\s*=\s*['\"]?([^'\"]+)['\"]?", raw)
        if match:
            raw = match.group(2)
    elif "." in raw:
        raw = raw.split(".", 1)[1]
    raw = re.sub(r"^(input|button|select|textarea|a|form)\b", "", raw).strip("_ ")
    key = re.sub(r"[^0-9a-zA-Z]+", "_", raw)
    key = re.sub(r"_+", "_", key).strip("_")
    return key or "field"


def _guess_input_value(field: Dict[str, Any]) -> Any:
    field_type = str(field.get("type") or field.get("kind") or "").lower()
    placeholder = str(field.get("placeholder") or "").lower()
    label = str(field.get("label") or "").lower()
    name = str(field.get("name") or "").lower()
    identifier = " ".join([field_type, placeholder, label, name])

    if "email" in identifier:
        return "test@example.com"
    if "username" in identifier or "login" in identifier or ("user" in identifier and "email" not in identifier and "username" not in identifier):
        return "standard_user"
    if "password" in identifier:
        return "Password123!"
    if any(keyword in identifier for keyword in ("first name", "firstname", "given name", "given_name", "givenname")):
        return "John"
    if any(keyword in identifier for keyword in ("last name", "lastname", "surname", "family name", "familyname", "sn")):
        return "Doe"
    if any(keyword in identifier for keyword in ("full name", "fullname", "name", "display name", "displayname", "yourname")):
        return "John Doe"
    if any(keyword in identifier for keyword in ("company", "organization", "organisation", "org")):
        return "Acme Corp"
    if any(keyword in identifier for keyword in ("address", "street", "line1", "line_1")):
        return "123 Main St"
    if any(keyword in identifier for keyword in ("city", "town")):
        return "Springfield"
    if any(keyword in identifier for keyword in ("state", "region", "province")):
        return "California"
    if any(keyword in identifier for keyword in ("zip", "postal", "postcode", "zip_code", "postalcode")):
        return "12345"
    if any(keyword in identifier for keyword in ("country", "nation")):
        return "United States"
    if any(keyword in identifier for keyword in ("phone", "mobile", "tel", "telephone", "cell")):
        return "1234567890"
    if any(keyword in identifier for keyword in ("card number", "cardnumber", "credit card", "ccnum", "cc_number")):
        return "4111111111111111"
    if any(keyword in identifier for keyword in ("cvv", "cvc", "security code", "security_code")):
        return "123"
    if any(keyword in identifier for keyword in ("expiry", "exp", "expiration", "expiration_date")):
        return "12/34"
    if any(keyword in identifier for keyword in ("dob", "date of birth", "birthdate", "birth date")):
        return "1990-01-01"
    if any(keyword in identifier for keyword in ("website", "url", "homepage", "link")) and field_type != "search":
        return "https://example.com"
    if any(keyword in identifier for keyword in ("search", "query", "find", "lookup")):
        return "test search"
    if any(keyword in identifier for keyword in ("subject", "title")):
        return "Test Subject"
    if any(keyword in identifier for keyword in ("message", "comment", "notes", "description", "textarea")):
        return "This is a sample message for automated testing."
    if any(keyword in identifier for keyword in ("amount", "price", "total", "cost", "quantity", "qty")):
        return "100"
    if any(keyword in identifier for keyword in ("promo", "coupon", "discount", "code")):
        return "PROMO10"
    if field_type in ("number",):
        return "42"
    if field_type in ("tel",):
        return "1234567890"
    if field_type in ("date",):
        return "2025-12-31"
    if field_type == "url":
        return "https://example.com"
    if field_type in ("search",):
        return "test search"
    if field_type in ("checkbox", "radio"):
        return True
    if field_type == "textarea":
        return "This is a sample message for automated testing."
    if field_type == "select":
        options = field.get("options") or []
        if isinstance(options, list) and options:
            first_option = options[0]
            return first_option.get("value") or first_option.get("text") or "option1"
        return "option1"
    return "sample text"


def _build_testdata_from_analysis(analysis: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if not isinstance(analysis, dict):
        return data

    for inp in (analysis.get("inputs") or []):
        if not isinstance(inp, dict):
            continue
        field_type = str(inp.get("type") or inp.get("kind") or "").lower()
        if field_type in ("hidden", "submit", "button", "reset", "image", "file"):
            continue
        if isinstance(inp.get("name"), str) and inp["name"].startswith("_"):
            continue
        key = _normalize_field_key(inp.get("name") or inp.get("id") or inp.get("label") or inp.get("placeholder"))
        if not key:
            continue
        if key in data:
            continue
        data[key] = _guess_input_value(inp)

    for sel in (analysis.get("selects") or []):
        if not isinstance(sel, dict):
            continue
        key = _normalize_field_key(sel.get("name") or sel.get("id") or sel.get("label") or sel.get("selector"))
        if not key:
            continue
        if key in data:
            continue
        data[key] = _guess_input_value({"type": "select", "options": sel.get("options")})

    return data


def _build_testdata_from_testcases(testcases: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if isinstance(testcases, dict) and isinstance(testcases.get("testcases"), list):
        cases = testcases["testcases"]
    elif isinstance(testcases, list):
        cases = testcases
    else:
        cases = []

    generic_selectors = {"input", "button", "a", "link", "form", "content", "field", "selector"}
    generic_values = {"sample", "valid-value", "login", "submit", "primary", "expected", "link", "valid-user", "test"}

    fallback_default_values = {
        "standard_user",
        "secret_sauce",
        "test@example.com",
        "test search",
        "sauce labs backpack",
        "4111111111111111",
    }

    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("steps"), list):
            continue
        for step in case["steps"]:
            if not isinstance(step, dict):
                continue
            action = str(step.get("action") or "").lower()
            selector = str(step.get("selector") or "").lower()
            value = step.get("value")
            if "username" in action or "username" in selector or ("user" in action and "password" not in action):
                data.setdefault("username", "standard_user")
            if "password" in action or "password" in selector:
                data.setdefault("password", "secret_sauce")
            if "email" in action or "email" in selector:
                data.setdefault("email", "test@example.com")
            if "search" in action or "search" in selector:
                data.setdefault("search", "test search")
            if "product" in action or "product" in selector:
                data.setdefault("product", "Sauce Labs Backpack")
            if "card" in action or "card" in selector or "credit" in action:
                data.setdefault("credit_card", "4111111111111111")

            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue
                if value.lower() in generic_values:
                    continue
                if selector in generic_selectors and "username" not in action and "password" not in action and "email" not in action and "search" not in action and "product" not in action:
                    continue
                key = _normalize_field_key(selector if selector and selector not in generic_selectors else action)
                if not key:
                    continue
                if key in data and isinstance(data[key], str) and data[key].lower() in fallback_default_values:
                    data[key] = value
                elif key not in data:
                    data[key] = value
    return data


def _build_fallback_testdata(testcases: Any, analysis: Any = None) -> Dict[str, Any]:
    data = _build_testdata_from_analysis(analysis)
    fallback = _build_testdata_from_testcases(testcases)
    for key, value in fallback.items():
        if key not in data:
            data[key] = value

    if not data:
        # If no explicit fields can be derived from page analysis or test steps,
        # avoid returning a generic default payload that looks like a login form.
        return {}

    return data


async def generate_testdata(testcases: Any, analysis: Any = None) -> Dict[str, Any]:
    """Generate realistic test data for provided test cases.

    Args:
        testcases: The testcases data produced by the test case generator.
        analysis: Optional page analysis JSON to ground test data in actual form fields.

    Returns:
        A JSON-compatible dict containing test data values.

    Raises:
        GroqServiceError if the LLM fails or returns unexpected output.
    """
    if USE_AI_TESTDATA:
        try:
            from app.core.groq_service import GroqService, GroqServiceError
            groq = GroqService()
            parsed = await groq.generate_testdata(testcases)
        except Exception:
            parsed = None
        if isinstance(parsed, dict) and "cases" in parsed and len(parsed) == 1:
            return parsed["cases"]
        if isinstance(parsed, dict) and parsed:
            return parsed

    return _build_fallback_testdata(testcases, analysis=analysis)
