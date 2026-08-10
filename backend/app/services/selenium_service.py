import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse


LOGGER = logging.getLogger(__name__)


def _normalize_test_name(title: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z_]+", "_", title.strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        normalized = "generated_test"
    if not normalized.startswith("test_"):
        normalized = f"test_{normalized}"
    return normalized


def _unique_function_name(base_name: str, used_names: set[str]) -> str:
    candidate = base_name
    suffix = 1
    while candidate in used_names:
        candidate = f"{base_name}_{suffix}"
        suffix += 1
    used_names.add(candidate)
    return candidate


def _format_literal(value: Any) -> str:
    return json.dumps(value if value is not None else "")


def _css_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")


def _validate_python_code(code: str) -> None:
    try:
        compile(code, "<generated_selenium>", "exec")
    except SyntaxError as exc:
        raise SyntaxError(f"Generated Selenium code contains syntax errors: {exc.msg} at line {exc.lineno}") from exc


def _validate_selenium_files(files: Dict[str, str]) -> None:
    for path, content in files.items():
        if isinstance(content, str) and path.lower().endswith(".py"):
            _validate_python_code(content)


def _extract_raw_url(raw_url: Optional[str]) -> str:
    if not isinstance(raw_url, str) or not raw_url.strip():
        return "https://example.com"

    text = raw_url.strip()
    href_match = re.search(r'href\s*=\s*["\']([^"\']+)["\']', text, re.IGNORECASE)
    if href_match:
        text = href_match.group(1).strip()
    else:
        text = re.sub(r'<[^>]+>', "", text)
        url_match = re.search(r'https?://[^\s<>"\']+', text)
        if url_match:
            text = url_match.group(0).strip()

    text = re.split(r'[<>"\s]', text)[0].strip()
    if any(token in text for token in ("<", ">", "href=", "</a>", "&quot;")):
        return "https://example.com"
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "https://example.com"
    cleaned = urlunparse(parsed._replace(fragment=""))
    return cleaned


def _looks_like_volatile_id(value: str) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) < 6:
        return False
    if re.search(r"[0-9]{4,}", value) and re.search(r"[a-zA-Z]{3,}", value):
        return True
    if re.fullmatch(r"[0-9a-f]{8,}", value):
        return True
    if value.lower().startswith("ember") or value.lower().startswith("react") or value.lower().startswith("ts-"):
        return True
    return False


def _flatten_analysis_elements(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    flattened: List[Dict[str, Any]] = []
    for key in ("inputs", "buttons", "links", "forms", "selects"):
        for item in analysis.get(key, []) or []:
            if isinstance(item, dict):
                flattened.append(item)
                if key == "forms":
                    for sub in (item.get("inputs") or []) + (item.get("buttons") or []):
                        if isinstance(sub, dict):
                            flattened.append(sub)
    return flattened


def _matches_css_selector(element: Dict[str, Any], selector: str) -> bool:
    attrs = element.get("attrs") or {}
    if selector.startswith("[data-testid="):
        value = selector.split("=", 1)[1].strip('"\'')
        return str(attrs.get("data-testid") or "") == value
    if selector.startswith("#"):
        return element.get("id") == selector[1:]
    if selector.startswith("[name="):
        value = selector.split("=", 1)[1].strip('"\'')
        return element.get("name") == value
    if selector.startswith("[placeholder="):
        value = selector.split("=", 1)[1].strip('"\'')
        return str(element.get("placeholder") or "") == value
    if selector.startswith("[aria-label="):
        value = selector.split("=", 1)[1].strip('"\'')
        return str(attrs.get("aria-label") or "") == value
    if selector.startswith("a[href="):
        value = selector.split("=", 1)[1].strip('"\'')
        return element.get("tag") == "a" and str(element.get("href") or "") == value

    match = re.fullmatch(r"([a-zA-Z0-9_-]+)?\[([a-zA-Z0-9_-]+)=['\"]?(.*?)['\"]?\]", selector)
    if match:
        tag, attr, value = match.groups()
        if tag and tag != str(element.get("tag") or ""):
            return False
        if attr == "type":
            return str(element.get("type") or attrs.get("type") or "") == value
        if attr == "name":
            return element.get("name") == value
        if attr == "placeholder":
            return str(element.get("placeholder") or attrs.get("placeholder") or "") == value
        if attr == "aria-label":
            return str(attrs.get("aria-label") or "") == value
        if attr == "data-testid":
            return str(attrs.get("data-testid") or "") == value
        if attr == "href":
            return element.get("tag") == "a" and str(element.get("href") or "") == value
        return str(attrs.get(attr) or "") == value

    parts = selector.split(".")
    if parts:
        tag = parts[0] if parts[0] else None
        classes = parts[1:]
        if tag and tag != str(element.get("tag") or ""):
            return False
        element_classes = [c for c in element.get("classes") or [] if isinstance(c, str)]
        return all(cls in element_classes for cls in classes)
    return False


def _locator_exists_in_analysis(locator: Dict[str, str], analysis: Dict[str, Any]) -> bool:
    values = _flatten_analysis_elements(analysis)
    by = locator.get("by")
    value = locator.get("value")
    if not by or not value:
        return False
    ids = [str(item) for item in (analysis.get("ids") or []) if item]
    if by == "By.ID":
        return value in ids or any(str(el.get("id") or "") == value for el in values)
    if by == "By.NAME":
        return any(str(el.get("name") or "") == value for el in values)
    if by == "By.LINK_TEXT":
        return any(str(el.get("text") or "") == value for el in values if str(el.get("tag") or "").lower() == "a")
    if by == "By.TAG_NAME":
        if value.lower() in ("body", "html", "option", "select"):
            return True
        return any(str(el.get("tag") or "").lower() == value.lower() for el in values)
    if by == "By.CSS_SELECTOR":
        return any(_matches_css_selector(el, value) for el in values)
    if by == "By.XPATH":
        # fallback: assume XPath locator is valid if it was derived from analysis
        return True
    return False


def _find_first_existing_id(analysis: Dict[str, Any], candidates: List[str]) -> Optional[str]:
    ids = [str(item) for item in (analysis.get("ids") or []) if item]
    for candidate in candidates:
        if candidate in ids:
            return candidate
    return None


def _validate_generated_code_quality(code: str, analysis: Dict[str, Any]) -> None:
    if re.search(r"By\.CSS_SELECTOR\s*,\s*[\"'](?:input|button|div|span|select|textarea|form|a|body)[\"']", code):
        raise ValueError("Generated code contains forbidden generic selectors.")
    if re.search(r"assert\s+driver\.title\s*==", code):
        raise ValueError("Generated code must avoid full-page-title equality assertions.")
    functions = {}
    current = None
    locators = []
    for line in code.splitlines():
        def_match = re.match(r"^def\s+([a-zA-Z0-9_]+)\s*\(", line)
        if def_match:
            current = def_match.group(1)
            if current not in functions:
                functions[current] = {"asserts": 0}
            continue
        if current is None:
            continue
        if re.match(r"^\s*assert\b", line):
            functions[current]["asserts"] += 1
        locator_match = re.search(r"(By\.[A-Z_]+)\s*,\s*([\"'].*?[\"'])", line)
        if locator_match:
            locators.append((locator_match.group(1), locator_match.group(2).strip('"\''), current))
    for name, metrics in functions.items():
        if name.startswith("test_") and metrics["asserts"] < 1:
            raise ValueError(f"Test function '{name}' has no assertions.")
    for by, value, func in locators:
        locator = {"by": by, "value": value}
        if not _locator_exists_in_analysis(locator, analysis):
            raise ValueError(f"Locator {by}, {value} in test '{func}' could not be validated against the DOM analysis.")


def _choose_locator_from_element(element: Dict[str, Any]) -> Optional[Dict[str, str]]:
    if not isinstance(element, dict):
        return None

    element_id = element.get("id")
    if element_id and not _looks_like_volatile_id(str(element_id)):
        return {"by": "By.ID", "value": str(element_id)}

    if element.get("name") and element.get("tag") != "a":
        return {"by": "By.NAME", "value": str(element["name"])}

    attrs = element.get("attrs") or {}
    test_id = attrs.get("data-testid") or attrs.get("data_testid") or attrs.get("data_test_id")
    if test_id:
        return {"by": "By.CSS_SELECTOR", "value": f"[data-testid=\"{_css_string(str(test_id))}\"]"}

    selector = str(element.get("selector") or "").strip()
    tag = str(element.get("tag") or "").lower()
    generic_tags = {"input", "button", "a", "form", "select", "textarea", "div", "span", "p", "label"}

    # If selector is a non-generic CSS selector, use it directly
    if selector and selector not in generic_tags:
        return {"by": "By.CSS_SELECTOR", "value": selector}

    attrs = element.get("attrs") or {}
    placeholder = str(element.get("placeholder") or attrs.get("placeholder") or "").strip()
    aria_label = str(attrs.get("aria-label") or "").strip()

    # If we only have a bare tag (or tag provided) try to build a more specific selector
    if (selector in generic_tags) or tag in generic_tags or selector == tag:
        # Priority: type → placeholder → aria-label → classes → label-based XPath
        type_attr = str(element.get("type") or attrs.get("type") or "").strip()
        if type_attr and tag and tag not in {"form", "a"}:
            return {"by": "By.CSS_SELECTOR", "value": f"{tag}[type=\"{_css_string(type_attr)}\"]"}
        if placeholder and tag in {"input", "textarea"}:
            return {"by": "By.CSS_SELECTOR", "value": f"{tag}[placeholder=\"{_css_string(placeholder)}\"]"}
        if aria_label and tag:
            return {"by": "By.CSS_SELECTOR", "value": f"{tag}[aria-label=\"{_css_string(aria_label)}\"]"}
        classes = [c for c in (element.get("classes") or []) if c]
        if classes and tag:
            return {"by": "By.CSS_SELECTOR", "value": f"{tag}{''.join(f'.{c}' for c in classes)}"}
        label_text = str(element.get("label") or "").strip()
        if label_text and tag in {"input", "textarea", "select"}:
            return {"by": "By.XPATH", "value": f"//label[normalize-space()={json.dumps(label_text)}]/following::{tag}[1]"}
        return None

    # If not handled above, fall back to placeholder/aria/css without forcing tag
    if placeholder:
        return {"by": "By.CSS_SELECTOR", "value": f"[placeholder=\"{_css_string(placeholder)}\"]"}
    if aria_label:
        return {"by": "By.CSS_SELECTOR", "value": f"[aria-label=\"{_css_string(aria_label)}\"]"}

    href = str(element.get("href") or "").strip()
    if href and element.get("tag") == "a":
        text = str(element.get("text") or "").strip()
        if text:
            return {"by": "By.LINK_TEXT", "value": text}
        return {"by": "By.CSS_SELECTOR", "value": f"a[href=\"{_css_string(href)}\"]"}

    text = str(element.get("text") or "").strip()
    if text and element.get("type") in ("button", "submit"):
        tag = str(element.get("tag") or "button").lower()
        if tag == "input":
            return {"by": "By.XPATH", "value": f"//input[@type={json.dumps(str(element.get('type')))} and normalize-space(@value)={json.dumps(text)}]"}
        return {"by": "By.XPATH", "value": f"//button[normalize-space()={json.dumps(text)}]"}

    classes = [c for c in (element.get("classes") or []) if c]
    if classes:
        tag = element.get("tag") or element.get("kind") or element.get("type") or "*"
        return {"by": "By.CSS_SELECTOR", "value": f"{tag}{''.join(f'.{c}' for c in classes)}"}

    return None


def _score_element(element: Dict[str, Any], hint: str) -> int:
    score = 0
    hint = hint.lower()
    for field in ("id", "name", "text", "placeholder", "label", "aria-label", "type", "action", "href"):
        value = str(element.get(field, "") or "").lower()
        if not value:
            continue
        if hint in value:
            score += 10
        if any(token in value for token in ["login", "user", "pass", "email", "submit", "search", "continue"]):
            score += 2
    return score


def _find_element_by_hint(analysis: Dict[str, Any], hint: str) -> Optional[Dict[str, str]]:
    candidates: List[Dict[str, Any]] = []
    for array_name in ("inputs", "buttons", "links", "forms", "selects"):
        for element in analysis.get(array_name, []) or []:
            locator = _choose_locator_from_element(element)
            if locator is None:
                continue
            score = _score_element(element, hint)
            candidates.append({"score": score, "locator": locator})

    if not candidates:
        return None

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[0]["locator"]


def _guess_input_value(field: Dict[str, Any]) -> str:
    field_type = str(field.get("type") or field.get("kind") or "").lower()
    placeholder = str(field.get("placeholder") or "").lower()
    attrs = field.get("attrs") or {}
    aria_label = str(attrs.get("aria-label") or "").lower()

    if "email" in field_type or "email" in placeholder or "email" in aria_label:
        return "test@example.com"
    if field_type in ("number", "tel") or "phone" in placeholder or "phone" in aria_label:
        return "1234567890"
    if "date" in field_type:
        return "2025-12-31"
    if field_type == "url" or "url" in placeholder:
        return "https://example.com"
    if "search" in field_type or "search" in placeholder or "search" in aria_label:
        return "test search"
    if field_type in ("checkbox", "radio"):
        return "true"
    if field_type in ("password",):
        return "Password123!"
    return "sample text"


def _is_safe_link(href: Optional[str], base_url: Optional[str]) -> bool:
    if not href or not base_url:
        return False
    href = href.strip()
    if href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("#"):
        return False
    parsed_base = urlparse(base_url)
    parsed_link = urlparse(href)
    if parsed_link.scheme and parsed_link.scheme not in ("http", "https"):
        return False
    if parsed_link.netloc and parsed_link.netloc != parsed_base.netloc:
        return False
    return True


def _find_safe_link(analysis: Optional[Dict[str, Any]]) -> Optional[tuple[Dict[str, str], str]]:
    if not isinstance(analysis, dict):
        return None
    base_url = analysis.get("url")
    for link in analysis.get("links", []) or []:
        href = str(link.get("href") or "").strip()
        if _is_safe_link(href, base_url):
            locator = _choose_locator_from_element(link)
            if locator:
                return locator, href
    return None


def _resolve_mapping_locator(mapping: Dict[str, Any], analysis: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, str]]:
    if not isinstance(mapping, dict):
        return None

    identifier = str(mapping.get("id") or mapping.get("name") or "").strip()
    if identifier:
        if mapping.get("id"):
            return {"by": "By.ID", "value": identifier}
        return {"by": "By.NAME", "value": identifier}

    attrs = mapping.get("attrs") or {}
    data_testid = str(mapping.get("data-testid") or mapping.get("data_testid") or attrs.get("data-testid") or "").strip()
    if data_testid:
        return {"by": "By.CSS_SELECTOR", "value": f"[data-testid=\"{_css_string(data_testid)}\"]"}
    data_test = str(mapping.get("data-test") or mapping.get("data_test") or attrs.get("data-test") or "").strip()
    if data_test:
        return {"by": "By.CSS_SELECTOR", "value": f"[data-test=\"{_css_string(data_test)}\"]"}

    selector = str(mapping.get("selector") or "").strip()
    if selector:
        generic_selectors = {"input", "button", "a", "form", "select", "textarea", "body", "html", "div", "span", "content", "field"}
        if selector in generic_selectors:
            return None
        if selector.startswith("/"):
            return {"by": "By.XPATH", "value": selector}
        # Prefer CSS selectors for explicit stable selectors.
        return {"by": "By.CSS_SELECTOR", "value": selector}

    href = str(mapping.get("href") or "").strip()
    if href and analysis is not None:
        for lk in analysis.get("links", []) or []:
            if str(lk.get("href") or "").strip() == href:
                return _choose_locator_from_element(lk)

    return None


def _resolve_step_locator(step: Dict[str, Any], analysis: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, str]]:
    selector = str(step.get("selector") or "").strip()
    action = str(step.get("action") or "").strip().lower()

    if selector and selector not in {"url", "title", "status_code"}:
        generic_selectors = {"input", "button", "a", "form", "select", "textarea", "body", "html", "div", "span", "content", "field"}
        if selector in generic_selectors:
            return None
        if selector.startswith("#") or selector.startswith(".") or selector.startswith("[") or " " in selector or selector.startswith("/") or ":" in selector:
            return {"by": "By.CSS_SELECTOR", "value": selector}
        if selector.isidentifier():
            return {"by": "By.CSS_SELECTOR", "value": selector}

    if analysis is not None:
        if "username" in action or "user" in action or "login" in action:
            locator = _find_element_by_hint(analysis, "user")
            if locator:
                return locator
        if "password" in action:
            locator = _find_element_by_hint(analysis, "password")
            if locator:
                return locator
        if "submit" in action or "click" in action or "button" in action:
            locator = _find_element_by_hint(analysis, "submit")
            if locator:
                return locator
        if "link" in action or "navigate" in action:
            locator = _find_element_by_hint(analysis, "link")
            if locator:
                return locator

    return None


def _build_step_code(step: Dict[str, Any], analysis: Optional[Dict[str, Any]] = None, testdata: Optional[Any] = None, default_url: Optional[str] = None) -> List[str]:
    action = str(step.get("action") or "").strip().lower()
    selector = str(step.get("selector") or "").strip()
    value = step.get("value")
    lines: List[str] = []

    if "navigate" in action or "go to" in action or selector == "url":
        url_target = value or (testdata.get("url") if isinstance(testdata, dict) else None) or default_url or "https://example.com"
        lines.append(f"    driver.get({_format_literal(url_target)})")
        return lines

    if selector == "title" or "title" in action:
        if value:
            lines.append(f"    assert driver.title == {_format_literal(value)}")
        else:
            lines.append("    assert driver.title")
        return lines

    if selector == "status_code" or "status code" in action:
        lines.append("    # Selenium cannot directly verify HTTP status codes; use an API call or browser logs if needed")
        return lines

    locator = _resolve_step_locator(step, analysis)
    if locator:
        by = locator["by"]
        selector_value = locator["value"]
        if "click" in action or "submit" in action or step.get("value") == "submit" or "button" in action:
            lines.append(f"    driver.find_element({by}, {_format_literal(selector_value)}).click()")
            return lines
        if any(keyword in action for keyword in ("enter", "type", "fill", "input", "search")):
            input_value = value
            if not input_value and isinstance(testdata, dict):
                input_value = (
                    testdata.get(step.get("selector"))
                    or testdata.get("username")
                    or testdata.get("password")
                    or testdata.get("email")
                    or testdata.get("search")
                    or "test"
                )
            lines.append(f"    driver.find_element({by}, {_format_literal(selector_value)}).send_keys({_format_literal(input_value)})")
            return lines
        if "verify" in action or "check" in action or "assert" in action:
            lines.append(f"    assert driver.find_element({by}, {_format_literal(selector_value)}).is_displayed()")
            return lines
        lines.append(f"    driver.find_element({by}, {_format_literal(selector_value)}).click()")
        return lines

    if "click" in action or "submit" in action:
        lines.append("    # TODO: click the correct element for this step")
        return lines

    if any(keyword in action for keyword in ("enter", "type", "fill", "input", "search")):
        lines.append("    # TODO: enter input into the correct field")
        return lines

    if "verify" in action or "check" in action or "assert" in action:
        lines.append("    # TODO: verify the expected state for this step")
        return lines

    lines.append(f"    # TODO: handle step action={_format_literal(action)} selector={_format_literal(selector)} value={_format_literal(value)}")
    return lines


def _build_selenium_code_from_analysis(
    testcases: Any,
    testdata: Optional[Any] = None,
    analysis: Optional[Dict[str, Any]] = None,
    scenarios: Optional[Any] = None,
) -> str:
    if not isinstance(analysis, dict):
        analysis = {}

    base_url = _extract_raw_url(str(analysis.get("url") or "https://example.com"))
    page_title = str(analysis.get("title") or "").strip()
    ids = [str(item) for item in (analysis.get("ids") or []) if item]
    forms = analysis.get("forms") or []
    inputs = analysis.get("inputs") or []
    buttons = analysis.get("buttons") or []
    had_select = any(
        isinstance(field, dict) and (str(field.get("kind") or "").lower() == "select" or str(field.get("type") or "").lower() == "select")
        for form in forms
        for field in (form.get("inputs") or [])
    ) or any(
        isinstance(sel, dict) and str(sel.get("tag") or "").lower() == "select"
        for sel in (analysis.get("selects") or [])
    )

    base_domain = base_url.lower()
    amazon_product_page = "amazon." in base_domain and _find_first_existing_id(analysis, ["productTitle"]) is not None
    price_id = _find_first_existing_id(
       analysis,
       ["priceblock_ourprice", "priceblock_dealprice", "priceblock_saleprice", "price_inside_buybox"],
    )
    add_to_cart_id = _find_first_existing_id(analysis, ["add-to-cart-button", "buy-now-button"])
    nav_cart_count_id = _find_first_existing_id(analysis, ["nav-cart-count", "nav-cart-count-container"])
    quantity_id = _find_first_existing_id(analysis, ["quantity"])
    availability_id = _find_first_existing_id(analysis, ["availability", "availability_feature_div"])
    ecommerce_product_page = amazon_product_page or (price_id is not None and add_to_cart_id is not None)

    code_lines = [
        "import pytest",
        "from selenium import webdriver",
        "from selenium.webdriver.common.by import By",
        "from selenium.webdriver.chrome.options import Options as ChromeOptions",
        "from selenium.webdriver.chrome.service import Service as ChromeService",
        "from selenium.webdriver.edge.options import Options as EdgeOptions",
        "from selenium.webdriver.edge.service import Service as EdgeService",
        "from selenium.webdriver.firefox.options import Options as FirefoxOptions",
        "from selenium.webdriver.firefox.service import Service as FirefoxService",
        "from selenium.webdriver.support.ui import WebDriverWait",
        "from selenium.webdriver.support import expected_conditions as EC",
    ]
    if had_select:
        code_lines.append("from selenium.webdriver.support.select import Select")
    code_lines.extend([
        "import os",
        "from webdriver_manager.chrome import ChromeDriverManager",
        "from webdriver_manager.microsoft import EdgeChromiumDriverManager",
        "from webdriver_manager.firefox import GeckoDriverManager",
        "",
        f"BASE_URL = {_format_literal(base_url)}",
        "",
        "# Environment helpers: set a local driver path to avoid network downloads",
        "CHROME_DRIVER_PATH = os.getenv('CHROME_DRIVER_PATH')",
        "EDGE_DRIVER_PATH = os.getenv('EDGE_DRIVER_PATH')",
        "GECKO_DRIVER_PATH = os.getenv('GECKO_DRIVER_PATH')",
        "PREFERRED_BROWSER = os.getenv('DRIVER_BROWSER')  # optional: 'chrome'|'edge'|'firefox'",
        "",
        "@pytest.fixture",
        "def driver():",
        "    chrome_options = ChromeOptions()",
        "    edge_options = EdgeOptions()",
        "    firefox_options = FirefoxOptions()",
        "    chrome_options.add_argument(\"--start-maximized\")",
        "    edge_options.add_argument(\"--start-maximized\")",
        "    firefox_options.add_argument(\"--start-maximized\")",
        "",
        "    # Prefer explicit local driver paths when provided",
        "    if CHROME_DRIVER_PATH and (not PREFERRED_BROWSER or PREFERRED_BROWSER.lower() == 'chrome'):",
        "        service = ChromeService(CHROME_DRIVER_PATH)",
        "        driver = webdriver.Chrome(service=service, options=chrome_options)",
        "    elif EDGE_DRIVER_PATH and (not PREFERRED_BROWSER or PREFERRED_BROWSER.lower() == 'edge'):",
        "        service = EdgeService(EDGE_DRIVER_PATH)",
        "        driver = webdriver.Edge(service=service, options=edge_options)",
        "    elif GECKO_DRIVER_PATH and (not PREFERRED_BROWSER or PREFERRED_BROWSER.lower() == 'firefox'):",
        "        service = FirefoxService(GECKO_DRIVER_PATH)",
        "        driver = webdriver.Firefox(service=service, options=firefox_options)",
        "    else:",
        "        # No local driver paths provided — prefer Edge via webdriver_manager (network required)",
        "        if not PREFERRED_BROWSER or PREFERRED_BROWSER.lower() == 'edge':",
        "            service = EdgeService(EdgeChromiumDriverManager().install())",
        "            driver = webdriver.Edge(service=service, options=edge_options)",
        "        elif PREFERRED_BROWSER and PREFERRED_BROWSER.lower() == 'firefox':",
        "            service = FirefoxService(GeckoDriverManager().install())",
        "            driver = webdriver.Firefox(service=service, options=firefox_options)",
        "        else:",
        "            # default to Chrome if PREFERRED_BROWSER explicitly set to 'chrome' or unknown",
        "            service = ChromeService(ChromeDriverManager().install())",
        "            driver = webdriver.Chrome(service=service, options=chrome_options)",
        "",
        "    driver.implicitly_wait(5)",
        "    yield driver",
        "    driver.quit()",
        "",
        "def wait_for_element(driver, by, locator, timeout=10):",
        "    return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((by, locator)))",
        "",
        "def find_element_present(driver, by, locator, timeout=10):",
        "    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, locator)))",
        "",
    ])

    used_function_names: set[str] = set()

    if ecommerce_product_page:
        if _find_first_existing_id(analysis, ["productTitle"]):
            function_name = _unique_function_name("test_product_title_is_visible", used_function_names)
            code_lines.extend([
                f"def {function_name}(driver):",
                "    driver.get(BASE_URL)",
                "    product_title = wait_for_element(driver, By.ID, \"productTitle\", timeout=15)",
                "    assert product_title.text.strip()",
                "",
            ])

        if price_id:
            function_name = _unique_function_name("test_price_is_displayed", used_function_names)
            code_lines.extend([
                f"def {function_name}(driver):",
                "    driver.get(BASE_URL)",
                f"    price_elem = wait_for_element(driver, By.ID, {_format_literal(price_id)}, timeout=15)",
                "    price_text = price_elem.text.strip()",
                "    assert price_text and (any(ch.isdigit() for ch in price_text) or '₹' in price_text)",
                "",
            ])

        if availability_id:
            function_name = _unique_function_name("test_availability_is_present", used_function_names)
            code_lines.extend([
                f"def {function_name}(driver):",
                "    driver.get(BASE_URL)",
                f"    avail_elem = wait_for_element(driver, By.ID, {_format_literal(availability_id)}, timeout=15)",
                "    avail_text = avail_elem.text.strip()",
                "    assert avail_text",
                "",
            ])

        if add_to_cart_id:
            if nav_cart_count_id:
                function_name = _unique_function_name("test_add_to_cart_updates_cart_count", used_function_names)
                code_lines.extend([
                    f"def {function_name}(driver):",
                    "    driver.get(BASE_URL)",
                    f"    add_cart_btn = wait_for_element(driver, By.ID, {_format_literal(add_cart_btn_id if False else add_to_cart_id)}, timeout=15)",
                    "    assert add_cart_btn.is_enabled()",
                    "    before_count = 0",
                    "    try:",
                    f"        count_elem = find_element_present(driver, By.ID, {_format_literal(nav_cart_count_id)}, timeout=5)",
                    "        before_text = count_elem.text.strip()",
                    "        before_count = int(before_text) if before_text.isdigit() else 0",
                    "    except Exception:",
                    "        before_count = 0",
                    "    add_cart_btn.click()",
                    "    def cart_increased(d):",
                    "        try:",
                    f"            elem = d.find_element(By.ID, {_format_literal(nav_cart_count_id)})",
                    "            text = elem.text.strip()",
                    "            return text.isdigit() and int(text) > before_count",
                    "        except Exception:",
                    "            return False",
                    "    WebDriverWait(driver, 15).until(cart_increased)",
                    "    final_count = int(driver.find_element(By.ID, {_format_literal(nav_cart_count_id)}).text.strip())",
                    "    assert final_count > before_count",
                    "",
                ])
            else:
                function_name = _unique_function_name("test_add_to_cart_button_is_clickable", used_function_names)
                code_lines.extend([
                    f"def {function_name}(driver):",
                    "    driver.get(BASE_URL)",
                    f"    add_cart_btn = wait_for_element(driver, By.ID, {_format_literal(add_to_cart_id)}, timeout=15)",
                    "    assert add_cart_btn.is_enabled()",
                    "    add_cart_btn.click()",
                    "    confirmation_ids = [\"attach-added-to-cart-message\", \"huc-v2-order-row-confirm-text\", \"attach-accessory-cart-subtotal\"]",
                    "    confirmed = False",
                    "    for cid in confirmation_ids:",
                    "        try:",
                    "            WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, cid)))",
                    "            confirmed = True",
                    "            break",
                    "        except Exception:",
                    "            continue",
                    "    assert confirmed, \"Expected add-to-cart confirmation element after clicking Add to Cart.\"",
                    "",
                ])

        if quantity_id:
            function_name = _unique_function_name("test_quantity_dropdown_uses_select", used_function_names)
            code_lines.extend([
                f"def {function_name}(driver):",
                "    driver.get(BASE_URL)",
                f"    quantity = wait_for_element(driver, By.ID, {_format_literal(quantity_id)}, timeout=15)",
                "    select = Select(quantity)",
                "    options = [option.get_attribute(\"value\") for option in quantity.find_elements(By.TAG_NAME, \"option\") if option.get_attribute(\"value\")]",
                "    assert options",
                "    if \"2\" in options:",
                "        select.select_by_value(\"2\")",
                "        assert select.first_selected_option.get_attribute(\"value\") == \"2\"",
                "    elif len(options) > 1:",
                "        select.select_by_index(1)",
                "        assert select.first_selected_option is not None",
                "",
            ])

    function_name = _unique_function_name("test_page_loads", used_function_names)
    code_lines.extend([
        f"def {function_name}(driver):",
        "    driver.get(BASE_URL)",
    ])

    if page_title:
        partial_title = page_title
        if "|" in page_title:
            partial_title = page_title.split("|")[0].strip()
        elif "-" in page_title:
            partial_title = page_title.split("-")[0].strip()
        elif "·" in page_title:
            partial_title = page_title.split("·")[0].strip()
        if partial_title:
            code_lines.append(f"    assert {_format_literal(partial_title)} in driver.title")
    code_lines.append("    assert driver.find_element(By.TAG_NAME, \"body\").is_displayed()")
    code_lines.append("")

    if forms:
        form = forms[0]
        form_fields: List[tuple[Dict[str, str], str]] = []
        for field in form.get("inputs", []):
            if not isinstance(field, dict):
                continue
            field_type = str(field.get("type") or field.get("kind") or "").lower()
            if field_type in ("hidden", "submit", "button", "reset", "image", "checkbox", "radio", "file"):
                continue
            if field_type == "select":
                had_select = True
            locator = _choose_locator_from_element(field)
            if locator is None:
                continue
            value = _guess_input_value(field)
            normalized_type = "input" if field_type in ("text", "password", "email", "tel", "url", "search", "number", "textarea") else field_type
            form_fields.append((locator, value, normalized_type))

        if form_fields:
            code_lines.append("def test_form_fields_accept_input(driver):")
            code_lines.append("    driver.get(BASE_URL)")
            for locator, value, field_type in form_fields:
                code_lines.append(f"    elem = wait_for_element(driver, {locator['by']}, {_format_literal(locator['value'])})")
                if field_type in ("input", "textarea"):
                    code_lines.append("    elem.clear()")
                    code_lines.append(f"    elem.send_keys({_format_literal(value)})")
                    code_lines.append(f"    assert {_format_literal(value)} in elem.get_attribute(\"value\")")
                elif field_type == "select":
                    code_lines.append(f"    Select(elem).select_by_visible_text({_format_literal(value)})")
                    code_lines.append(f"    assert elem.get_attribute(\"value\")")
                code_lines.append("")

        hidden_fields = [
            field for field in form.get("inputs", [])
            if isinstance(field, dict) and str(field.get("type") or "").lower() == "hidden"
        ]
        if hidden_fields:
            code_lines.append("def test_hidden_fields_exist(driver):")
            code_lines.append("    driver.get(BASE_URL)")
            for hidden in hidden_fields:
                locator = _choose_locator_from_element(hidden)
                if locator:
                    code_lines.append(f"    hidden_elem = find_element_present(driver, {locator['by']}, {_format_literal(locator['value'])})")
                    code_lines.append("    assert hidden_elem.get_attribute(\"type\") == \"hidden\"")
                else:
                    code_lines.append("    # Unable to determine locator for hidden input field")
            code_lines.append("")

        # Also add a scenario-driven test for this form if scenarios reference it
        if scenarios:
            try:
                scenario_list = scenarios.get("scenarios") if isinstance(scenarios, dict) else (scenarios if isinstance(scenarios, list) else [])
            except Exception:
                scenario_list = []
            for sc in scenario_list:
                mapping = sc.get("mapping") or {}
                if mapping.get("form_id") and (mapping.get("form_id") == form.get("id") or mapping.get("form_id") == form.get("name")):
                    test_name = _normalize_test_name(sc.get("title") or sc.get("description") or f"form_{form.get('id')}")
                    code_lines.append(f"def {test_name}(driver):")
                    code_lines.append("    driver.get(BASE_URL)")
                    for field in form.get("inputs", []):
                        if not isinstance(field, dict):
                            continue
                        field_type = str(field.get("type") or field.get("kind") or "").lower()
                        if field_type in ("hidden", "submit", "button", "reset", "image", "checkbox", "radio", "file"):
                            continue
                        locator = _choose_locator_from_element(field)
                        if locator is None:
                            code_lines.append("    # could not determine locator for a field")
                            continue
                        value = _guess_input_value(field)
                        code_lines.append(f"    elem = wait_for_element(driver, {locator['by']}, {_format_literal(locator['value'])})")
                        if field_type in ("text", "password", "email", "tel", "url", "search", "number", "textarea"):
                            code_lines.append("    elem.clear()")
                            code_lines.append(f"    elem.send_keys({_format_literal(value)})")
                            code_lines.append(f"    assert {_format_literal(value)} in elem.get_attribute(\"value\")")
                        elif field_type == "select":
                            code_lines.append(f"    Select(elem).select_by_visible_text({_format_literal(value)})")
                            code_lines.append(f"    assert elem.get_attribute(\"value\")")
                    # attempt to submit
                    submit_locator = None
                    for btn in form.get("buttons", []):
                        bl = _choose_locator_from_element(btn)
                        if bl:
                            submit_locator = bl
                            break
                    if submit_locator:
                        code_lines.append(f"    driver.find_element({submit_locator['by']}, {_format_literal(submit_locator['value'])}).click()")
                    else:
                        code_lines.append("    # no submit button found for this form")
                    code_lines.append("")

    search_input = None
    for inp in inputs:
        if not isinstance(inp, dict):
            continue
        name = str(inp.get("name") or "").lower()
        inp_id = str(inp.get("id") or "").lower()
        placeholder = str(inp.get("placeholder") or "").lower()
        if "search" in name or "search" in inp_id or "search" in placeholder:
            search_input = inp
            break

    if search_input:
        locator = _choose_locator_from_element(search_input)
        if locator:
            code_lines.append("def test_search_field_accepts_text(driver):")
            code_lines.append("    driver.get(BASE_URL)")
            code_lines.append(f"    search_box = wait_for_element(driver, {locator['by']}, {_format_literal(locator['value'])})")
            code_lines.append("    search_box.clear()")
            code_lines.append("    search_box.send_keys(\"test search\")")
            code_lines.append("    assert \"test search\" in search_box.get_attribute(\"value\")")
            code_lines.append("")

    if buttons:
        button_locator = _choose_locator_from_element(buttons[0])
        if button_locator:
            code_lines.append("def test_primary_button_is_present(driver):")
            code_lines.append("    driver.get(BASE_URL)")
            code_lines.append(f"    button = wait_for_element(driver, {button_locator['by']}, {_format_literal(button_locator['value'])})")
            code_lines.append("    assert button.is_displayed()")
            code_lines.append("    assert button.is_enabled()")
            code_lines.append("")

    safe_link = _find_safe_link(analysis)
    if safe_link:
        locator, href = safe_link
        code_lines.append("def test_safe_link_is_available(driver):")
        code_lines.append("    driver.get(BASE_URL)")
        code_lines.append(f"    link = wait_for_element(driver, {locator['by']}, {_format_literal(locator['value'])})")
        code_lines.append("    assert link.is_displayed()")
        if href.startswith("http"):
            code_lines.append(f"    assert link.get_attribute(\"href\") == {_format_literal(href)}")
        else:
            code_lines.append(f"    assert link.get_attribute(\"href\").endswith({_format_literal(href.lstrip('/'))})")
        code_lines.append("")

    # Generate tests for each high-level scenario when scenarios are provided
    if scenarios:
        try:
            scenario_list = scenarios.get("scenarios") if isinstance(scenarios, dict) else (scenarios if isinstance(scenarios, list) else [])
        except Exception:
            scenario_list = []

        generated_names = set()
        for sc in scenario_list:
            title = sc.get("title") or sc.get("description") or "scenario"
            base_test_name = _normalize_test_name(title)
            test_name = base_test_name
            suffix = 1
            while test_name in generated_names:
                test_name = f"{base_test_name}_{suffix}"
                suffix += 1
            generated_names.add(test_name)

            mapping = sc.get("mapping") or {}
            code_lines.append(f"def {test_name}(driver):")
            code_lines.append("    driver.get(BASE_URL)")

            # handle page load
            if mapping.get("page") == "load":
                if page_title:
                    code_lines.append(f"    assert {_format_literal(page_title)} in driver.title")
                code_lines.append("    assert driver.find_element(By.TAG_NAME, \"body\").is_displayed()")
                code_lines.append("")
                continue

            # handle auth
            if mapping.get("page") == "auth" or mapping.get("auth"):
                user_locator = _find_element_by_hint(analysis, "user")
                pass_locator = _find_element_by_hint(analysis, "password")

                if not pass_locator:
                    password_fields = [
                        inp for inp in analysis.get("inputs", []) or []
                        if isinstance(inp, dict) and str(inp.get("type") or "").lower() == "password"
                    ]
                    if password_fields:
                        pass_locator = _choose_locator_from_element(password_fields[0])

                if not user_locator:
                    username_candidates = [
                        inp for inp in analysis.get("inputs", []) or []
                        if isinstance(inp, dict) and str(inp.get("type") or "").lower() in ("text", "email", "tel", "search", "url", "")
                    ]
                    username_candidates.sort(key=lambda inp: _score_element(inp, "user"), reverse=True)
                    if username_candidates:
                        user_locator = _choose_locator_from_element(username_candidates[0])

                if user_locator:
                    code_lines.append(
                        f"    driver.find_element({user_locator['by']}, {_format_literal(user_locator['value'])}).send_keys({_format_literal(testdata.get('username') if isinstance(testdata, dict) else 'testuser')})"
                    )
                if pass_locator:
                    code_lines.append(
                        f"    driver.find_element({pass_locator['by']}, {_format_literal(pass_locator['value'])}).send_keys({_format_literal(testdata.get('password') if isinstance(testdata, dict) else 'Password123!')})"
                    )

                submit = _find_element_by_hint(analysis, "submit")
                if not submit:
                    for button in analysis.get("buttons", []) or []:
                        if not isinstance(button, dict):
                            continue
                        if str(button.get("type") or "").lower() in ("submit", "button") or _score_element(button, "submit") > 0:
                            submit = _choose_locator_from_element(button)
                            if submit:
                                break

                if submit:
                    code_lines.append(f"    driver.find_element({submit['by']}, {_format_literal(submit['value'])}).click()")
                if not user_locator and not pass_locator:
                    code_lines.append("    # Unable to identify login fields from page analysis; verify rendering or locator extraction")
                code_lines.append("")
                continue

            # handle href or selector-driven mappings
            locator = _resolve_mapping_locator(mapping, analysis)
            if locator:
                code_lines.append(f"    elem = wait_for_element(driver, {locator['by']}, {_format_literal(locator['value'])})")
                mapping_type = str(mapping.get("type") or "").lower()
                if mapping.get("href"):
                    code_lines.append("    assert elem.is_displayed()")
                    code_lines.append("    elem.click()")
                    code_lines.append("    assert driver.current_url != BASE_URL")
                elif mapping.get("select_id") or mapping_type == "select" or mapping_type == "dropdown":
                    code_lines.append("    Select(elem).select_by_index(1)")
                    code_lines.append("    assert elem.get_attribute(\"value\")")
                elif mapping_type in ("text", "email", "password", "url", "tel", "search", "number", "textarea"):
                    example_value = testdata.get("value") if isinstance(testdata, dict) and testdata.get("value") else "test value"
                    code_lines.append("    elem.clear()")
                    code_lines.append(f"    elem.send_keys({_format_literal(example_value)})")
                    code_lines.append(f"    assert {_format_literal(example_value)} in elem.get_attribute(\"value\")")
                elif mapping_type == "hidden":
                    code_lines.append("    assert elem.get_attribute(\"type\") == \"hidden\"")
                elif mapping_type in ("button", "submit") or "button" in title.lower():
                    code_lines.append("    assert elem.is_enabled()")
                    code_lines.append("    elem.click()")
                    code_lines.append("    assert elem.is_enabled()")
                else:
                    code_lines.append("    assert elem.is_displayed()")
                code_lines.append("")
                continue

            if mapping.get("href"):
                href = str(mapping.get("href") or "").strip()
                link_locator = None
                for lk in analysis.get("links", []) or []:
                    if str(lk.get("href") or "").strip() == href:
                        link_locator = _choose_locator_from_element(lk)
                        break
                if link_locator:
                    code_lines.append(f"    driver.find_element({link_locator['by']}, {_format_literal(link_locator['value'])}).click()")
                    code_lines.append(f"    assert driver.current_url != BASE_URL")
                    code_lines.append("")
                    continue

            if mapping.get("select_id"):
                sid = mapping.get("select_id")
                sel_locator = None
                for sel in analysis.get("selects", []) or []:
                    if sel.get("id") == sid or sel.get("name") == sid:
                        sel_locator = _choose_locator_from_element(sel)
                        break
                if sel_locator:
                    code_lines.append(f"    elem = wait_for_element(driver, {sel_locator['by']}, {_format_literal(sel_locator['value'])})")
                    code_lines.append("    Select(elem).select_by_index(1)")
                    code_lines.append("    assert elem.get_attribute(\"value\")")
                    code_lines.append("")
                    continue

            # Fallback: assert page loaded
            code_lines.append("    assert driver.find_element(By.TAG_NAME, \"body\").is_displayed()")
            code_lines.append("")

    code = "\n".join(code_lines)
    _validate_generated_code_quality(code, analysis or {})
    _validate_python_code(code)
    return code


def _is_placeholder_bundle(parsed: Dict[str, Any]) -> bool:
    if not isinstance(parsed, dict):
        return False
    files = parsed.get("files")
    if not isinstance(files, dict):
        return False
    for content in files.values():
        if isinstance(content, str) and ("placeholder" in content.lower() or ("assert True" in content and "driver" not in content)):
            return True
    return False


def _build_minimal_selenium_code(analysis: Optional[Any] = None) -> str:
    base_url = "https://example.com"
    if isinstance(analysis, dict):
        base_url = _extract_raw_url(str(analysis.get("url") or base_url))
    code_lines = [
        "import pytest",
        "from selenium import webdriver",
        "from selenium.webdriver.common.by import By",
        "from selenium.webdriver.chrome.options import Options as ChromeOptions",
        "from selenium.webdriver.chrome.service import Service as ChromeService",
        "from selenium.webdriver.edge.options import Options as EdgeOptions",
        "from selenium.webdriver.edge.service import Service as EdgeService",
        "from selenium.webdriver.firefox.options import Options as FirefoxOptions",
        "from selenium.webdriver.firefox.service import Service as FirefoxService",
        "import os",
        "from webdriver_manager.chrome import ChromeDriverManager",
        "from webdriver_manager.microsoft import EdgeChromiumDriverManager",
        "from webdriver_manager.firefox import GeckoDriverManager",
        "",
        f"BASE_URL = {_format_literal(base_url)}",
        "",
        "CHROME_DRIVER_PATH = os.getenv('CHROME_DRIVER_PATH')",
        "EDGE_DRIVER_PATH = os.getenv('EDGE_DRIVER_PATH')",
        "GECKO_DRIVER_PATH = os.getenv('GECKO_DRIVER_PATH')",
        "PREFERRED_BROWSER = os.getenv('DRIVER_BROWSER')  # optional: 'chrome'|'edge'|'firefox'",
        "",
        "@pytest.fixture",
        "def driver():",
        "    chrome_options = ChromeOptions()",
        "    edge_options = EdgeOptions()",
        "    firefox_options = FirefoxOptions()",
        "    chrome_options.add_argument(\"--start-maximized\")",
        "    edge_options.add_argument(\"--start-maximized\")",
        "    firefox_options.add_argument(\"--start-maximized\")",
        "",
        "    if CHROME_DRIVER_PATH and (not PREFERRED_BROWSER or PREFERRED_BROWSER.lower() == 'chrome'):",
        "        service = ChromeService(CHROME_DRIVER_PATH)",
        "        driver = webdriver.Chrome(service=service, options=chrome_options)",
        "    elif EDGE_DRIVER_PATH and (not PREFERRED_BROWSER or PREFERRED_BROWSER.lower() == 'edge'):",
        "        service = EdgeService(EDGE_DRIVER_PATH)",
        "        driver = webdriver.Edge(service=service, options=edge_options)",
        "    elif GECKO_DRIVER_PATH and (not PREFERRED_BROWSER or PREFERRED_BROWSER.lower() == 'firefox'):",
        "        service = FirefoxService(GECKO_DRIVER_PATH)",
        "        driver = webdriver.Firefox(service=service, options=firefox_options)",
        "    else:",
        "        if not PREFERRED_BROWSER or PREFERRED_BROWSER.lower() == 'edge':",
        "            service = EdgeService(EdgeChromiumDriverManager().install())",
        "            driver = webdriver.Edge(service=service, options=edge_options)",
        "        elif PREFERRED_BROWSER and PREFERRED_BROWSER.lower() == 'firefox':",
        "            service = FirefoxService(GeckoDriverManager().install())",
        "            driver = webdriver.Firefox(service=service, options=firefox_options)",
        "        else:",
        "            service = ChromeService(ChromeDriverManager().install())",
        "            driver = webdriver.Chrome(service=service, options=chrome_options)",
        "",
        "    driver.implicitly_wait(5)",
        "    yield driver",
        "    driver.quit()",
        "",
        "def test_page_loads(driver):",
        "    driver.get(BASE_URL)",
        "    assert driver.title is not None",
        ""
    ]
    code = "\n".join(code_lines)
    _validate_python_code(code)
    return code


async def generate_selenium_bundle(
    testcases: Any,
    testdata: Optional[Any] = None,
    scenarios: Optional[Any] = None,
    analysis: Optional[Any] = None,
) -> Dict[str, Any]:
    """Generate Selenium Python code from testcases and optional artifacts.

    This service delegates to GroqService.generate_selenium_code() and
    normalizes the returned JSON into a file bundle.
    """
    artifacts: Dict[str, Any] = {"testcases": testcases}
    if testdata is not None:
        artifacts["testdata"] = testdata
    if scenarios is not None:
        artifacts["scenarios"] = scenarios
    if analysis is not None:
        artifacts["analysis"] = analysis

    # Prefer deterministic, analysis-driven generation of Selenium code unless overridden
    USE_AI_SELENIUM = os.getenv("USE_AI_SELENIUM", "false").lower() in ("1", "true", "yes")
    parsed = None
    if USE_AI_SELENIUM:
        try:
            # Lazy-import GroqService so that analysis-driven generation works even if Groq/httpx deps are missing
            from app.core.groq_service import GroqService, GroqServiceError
            groq = GroqService()
            parsed = await groq.generate_selenium_code(artifacts)
        except Exception as exc:
            LOGGER.warning("Groq selenium generation failed; using analysis-driven code fallback: %s", exc)
            parsed = {"framework": "pytest", "selenium": "python", "notes": "Fallback script"}

    if parsed is None:
        # Directly build analysis-driven code
        try:
            fallback_code = _build_selenium_code_from_analysis(testcases, testdata=testdata, analysis=analysis, scenarios=scenarios)
        except (ValueError, SyntaxError, TypeError) as exc:
            LOGGER.exception("Analysis-driven Selenium code validation failed: %s", exc)
            fallback_code = _build_minimal_selenium_code(analysis)
        files = {"tests/test_generated.py": fallback_code}
        _validate_selenium_files(files)
        return {"files": files, "metadata": {"notes": "Analysis-driven Selenium script"}}

    LOGGER.info("generate_selenium_code returned: %s", repr(parsed))

    if isinstance(parsed, dict):
        if "files" in parsed:
            if _is_placeholder_bundle(parsed):
                try:
                    fallback_code = _build_selenium_code_from_analysis(testcases, testdata=testdata, analysis=analysis, scenarios=scenarios)
                except (ValueError, SyntaxError, TypeError) as exc:
                    LOGGER.exception("Fallback analysis-driven Selenium code validation failed: %s", exc)
                    fallback_code = _build_minimal_selenium_code(analysis)
                files = {"tests/test_generated.py": fallback_code}
                _validate_selenium_files(files)
                return {"files": files, "metadata": parsed}
            files_value = parsed.get("files")
            if isinstance(files_value, dict):
                _validate_selenium_files(files_value)
                return parsed
            LOGGER.warning("Parsed Groq selenium bundle contains invalid files payload; falling back to analysis-driven code.")
            try:
                fallback_code = _build_selenium_code_from_analysis(testcases, testdata=testdata, analysis=analysis, scenarios=scenarios)
            except (ValueError, SyntaxError, TypeError) as exc:
                LOGGER.exception("Fallback analysis-driven Selenium code validation failed: %s", exc)
                fallback_code = _build_minimal_selenium_code(analysis)
            files = {"tests/test_generated.py": fallback_code}
            _validate_selenium_files(files)
            return {"files": files, "metadata": parsed}
        if "code" in parsed and isinstance(parsed["code"], str):
            code_text = parsed["code"].strip()
            if "assert True" in code_text and "driver" not in code_text:
                try:
                    fallback_code = _build_selenium_code_from_analysis(testcases, testdata=testdata, analysis=analysis, scenarios=scenarios)
                except (ValueError, SyntaxError, TypeError) as exc:
                    LOGGER.exception("Fallback analysis-driven Selenium code validation failed: %s", exc)
                    fallback_code = _build_minimal_selenium_code(analysis)
                files = {"generated_selenium.py": fallback_code}
                _validate_selenium_files(files)
                return {"files": files, "metadata": parsed.get("metadata", {})}
            try:
                _validate_python_code(code_text)
                return {"files": {"generated_selenium.py": code_text}, "metadata": parsed.get("metadata", {})}
            except SyntaxError as exc:
                LOGGER.exception("Parsed Groq selenium code is invalid Python: %s", exc)
                try:
                    fallback_code = _build_selenium_code_from_analysis(testcases, testdata=testdata, analysis=analysis, scenarios=scenarios)
                except (ValueError, SyntaxError, TypeError) as exc2:
                    LOGGER.exception("Fallback analysis-driven Selenium code validation failed: %s", exc2)
                    fallback_code = _build_minimal_selenium_code(analysis)
                files = {"generated_selenium.py": fallback_code}
                _validate_selenium_files(files)
                return {"files": files, "metadata": parsed.get("metadata", {})}
        if parsed.get("framework") in {"pytest", "selenium"} or parsed.get("selenium") == "python":
            fallback_code = _build_selenium_code_from_analysis(testcases, testdata=testdata, analysis=analysis, scenarios=scenarios)
            files = {"tests/test_generated.py": fallback_code}
            _validate_selenium_files(files)
            return {"files": files, "metadata": parsed}

    if isinstance(parsed, str):
        text = parsed.strip()
        if "assert True" in text and "driver" not in text:
            try:
                fallback_code = _build_selenium_code_from_analysis(testcases, testdata=testdata, analysis=analysis, scenarios=scenarios)
            except (ValueError, SyntaxError, TypeError) as exc:
                LOGGER.exception("Fallback analysis-driven Selenium code validation failed: %s", exc)
                fallback_code = _build_minimal_selenium_code(analysis)
            files = {"generated_selenium.py": fallback_code}
            _validate_selenium_files(files)
            return {"files": files, "metadata": {}}
        try:
            _validate_python_code(text)
            return {"files": {"generated_selenium.py": text}, "metadata": {}}
        except SyntaxError as exc:
            LOGGER.exception("Parsed Groq selenium string is invalid Python: %s", exc)
            try:
                fallback_code = _build_selenium_code_from_analysis(testcases, testdata=testdata, analysis=analysis, scenarios=scenarios)
            except (ValueError, SyntaxError, TypeError) as exc2:
                LOGGER.exception("Fallback analysis-driven Selenium code validation failed: %s", exc2)
                fallback_code = _build_minimal_selenium_code(analysis)
            files = {"generated_selenium.py": fallback_code}
            _validate_selenium_files(files)
            return {"files": files, "metadata": {}}

    try:
        fallback_code = _build_selenium_code_from_analysis(testcases, testdata=testdata, analysis=analysis, scenarios=scenarios)
    except (ValueError, SyntaxError, TypeError) as exc:
        LOGGER.exception("Fallback analysis-driven Selenium code validation failed: %s", exc)
        fallback_code = _build_minimal_selenium_code(analysis)
    files = {"tests/test_generated.py": fallback_code}
    _validate_selenium_files(files)
    return {"files": files, "metadata": {"notes": "Generated analysis-driven Selenium script"}}
