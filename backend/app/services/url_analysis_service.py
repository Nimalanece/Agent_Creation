import asyncio
import glob
import logging
import os
import shutil
import socket
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from dotenv import load_dotenv
from bs4 import BeautifulSoup

try:
    import httpx
    _HTTPX_AVAILABLE = True
except Exception:
    httpx = None
    _HTTPX_AVAILABLE = False

try:
    import requests
    _REQUESTS_AVAILABLE = True
except Exception:
    requests = None
    _REQUESTS_AVAILABLE = False

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException, TimeoutException
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.edge.service import Service as EdgeService
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    _SELENIUM_AVAILABLE = True
except ImportError:
    webdriver = None
    WebDriverException = Exception
    TimeoutException = Exception
    ChromeOptions = None
    EdgeOptions = None
    ChromeService = None
    EdgeService = None
    WebDriverWait = None
    EC = None
    ChromeDriverManager = None
    _SELENIUM_AVAILABLE = False

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

load_dotenv()

# Basic configuration
DEFAULT_TIMEOUT = 10  # seconds
USER_AGENT = "AI-QA-Agent-Analyzer/1.0 (+https://example.com)"
VERIFY_SSL = os.getenv("DISABLE_SSL_VERIFICATION", "false").lower() not in ("1", "true", "yes")


class URLAnalysisError(Exception):
    pass


def _is_valid_url(url: str) -> bool:
    """Basic validation that URL has http/https scheme and a hostname."""
    if not isinstance(url, str):
        return False
    if any(token in url for token in ("<", ">", "href=", "</a>", "&quot;")):
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.hostname:
            return False
        return True
    except Exception:
        return False


def _extract_raw_url_from_input(raw_url: Optional[str]) -> str:
    if not isinstance(raw_url, str) or not raw_url.strip():
        return ""
    text = raw_url.strip()

    # Prefer explicit href values from anchor tags.
    href_match = re.search(r'href\s*=\s*["\']([^"\']+)["\']', text, re.IGNORECASE)
    if href_match:
        text = href_match.group(1).strip()
    else:
        # Remove HTML tags completely and then find the first raw URL.
        text = re.sub(r'<[^>]+>', '', text)
        url_match = re.search(r'https?://[^\s<>"\']+', text)
        if url_match:
            text = url_match.group(0).strip()

    # If the URL is still wrapped or suffixed by HTML fragments, trim at the first disallowed character.
    text = re.split(r'[<>"\s]', text)[0].strip()

    if not _is_valid_url(text):
        return ""

    # Normalize and remove fragments.
    parsed = urlparse(text)
    cleaned = parsed._replace(fragment="")
    return cleaned.geturl()


def _is_private_host(hostname: str) -> bool:
    """Resolve hostname to IP and check for private ranges (naive check).

    This is a best-effort prevention for SSRF. It is NOT a replacement for a full
    allowlist/blocklist implemented in infra.
    """
    try:
        # Resolve to first IPv4 address
        ip = socket.gethostbyname(hostname)
        # Simple checks for common private ranges
        private_prefixes = ("10.", "172.", "192.168.", "127.")
        for p in private_prefixes:
            if ip.startswith(p):
                return True
        return False
    except Exception:
        # If resolution fails, be conservative and treat as non-private
        return False


def _element_selector(tag) -> str:
    """Construct a simple CSS selector for an element using id or classes when available."""
    if tag is None or not getattr(tag, "name", None):
        return ""
    name = tag.name
    if tag.has_attr("id") and tag["id"]:
        return f"{name}#{tag['id']}"
    if tag.has_attr("class") and tag["class"]:
        classes = ".".join([c for c in tag.get("class", []) if c])
        if classes:
            return f"{name}.{classes}"
    # fallback to tag and nth-child is expensive; return tag name
    return name


def _collect_ids_and_classes(soup: BeautifulSoup) -> Dict[str, List[Dict[str, Any]]]:
    ids: Set[str] = set()
    classes: Dict[str, Set[str]] = {}

    for el in soup.find_all(True):
        if el.has_attr("id") and el["id"]:
            ids.add(el["id"])
        if el.has_attr("class") and el.get("class"):
            for c in el.get("class", []):
                classes.setdefault(c, set()).add(el.name)

    return {
        "ids": sorted(list(ids)),
        "classes": {k: sorted(list(v)) for k, v in classes.items()},
    }


def _extract_label_mapping(soup: BeautifulSoup) -> Dict[str, str]:
    """Map form controls to their visible label text when available."""
    labels: Dict[str, str] = {}
    for label in soup.find_all("label"):
        label_text = (label.get_text(strip=True) or "").strip()
        if not label_text:
            continue
        if label.has_attr("for"):
            labels[label["for"]] = label_text
            continue
        for control in label.find_all(["input", "textarea", "select"]):
            if control.has_attr("id"):
                labels[control["id"]] = label_text
            elif control.has_attr("name"):
                labels[control["name"]] = label_text
    return labels


def _get_label_for_element(element: Any, labels: Dict[str, str]) -> str:
    if not labels:
        return ""
    if element.has_attr("id") and element["id"] in labels:
        return labels[element["id"]]
    if element.has_attr("name") and element["name"] in labels:
        return labels[element["name"]]
    return ""


def _extract_buttons(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    # <button> tags
    for btn in soup.find_all("button"):
        results.append(
            {
                    "tag": btn.name,
                    "type": "button",
                    "text": (btn.get_text(strip=True) or ""),
                    "id": btn.get("id"),
                    "name": btn.get("name"),
                    "classes": btn.get("class", []),
                    "attrs": dict(btn.attrs),
                    "selector": _element_selector(btn),
                }
            )

    # <input type=button|submit|reset>
    for inp in soup.find_all("input", {"type": True}):
        t = inp.get("type", "").lower()
        if t in ("button", "submit", "reset"):
            results.append(
                {
                    "tag": inp.name,
                    "type": t,
                    "value": inp.get("value"),
                    "id": inp.get("id"),
                    "name": inp.get("name"),
                    "classes": inp.get("class", []),
                    "attrs": dict(inp.attrs),
                    "selector": _element_selector(inp),
                }
            )

    # elements with role=button
    for el in soup.find_all(attrs={"role": "button"}):
        results.append(
            {
                "tag": el.name,
                "type": "role-button",
                "text": (el.get_text(strip=True) or ""),
                "id": el.get("id"),
                "name": el.get("name"),
                "classes": el.get("class", []),
                "attrs": dict(el.attrs),
                "selector": _element_selector(el),
            }
        )

    return results


def _extract_inputs(soup: BeautifulSoup, labels: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    inputs = soup.find_all("input")
    for inp in inputs:
        results.append(
            {
                "tag": inp.name,
                "type": inp.get("type", "text"),
                "name": inp.get("name"),
                "id": inp.get("id"),
                "label": _get_label_for_element(inp, labels or {}),
                "placeholder": inp.get("placeholder"),
                "required": inp.has_attr("required"),
                "classes": inp.get("class", []),
                "attrs": dict(inp.attrs),
                "selector": _element_selector(inp),
            }
        )
    # also include textarea
    for ta in soup.find_all("textarea"):
        results.append(
            {
                "tag": ta.name,
                "type": "textarea",
                "name": ta.get("name"),
                "id": ta.get("id"),
                "label": _get_label_for_element(ta, labels or {}),
                "placeholder": ta.get("placeholder"),
                "required": ta.has_attr("required"),
                "classes": ta.get("class", []),
                "attrs": dict(ta.attrs),
                "selector": _element_selector(ta),
            }
        )
    return results


def _extract_selects(soup: BeautifulSoup, labels: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for sel in soup.find_all("select"):
        options = []
        for opt in sel.find_all("option"):
            options.append({
                "value": opt.get("value"),
                "text": opt.get_text(strip=True),
                "selected": opt.has_attr("selected"),
                "attrs": dict(opt.attrs),
            })
        results.append(
            {
                "tag": sel.name,
                "name": sel.get("name"),
                "id": sel.get("id"),
                "label": _get_label_for_element(sel, labels or {}),
                "multiple": sel.has_attr("multiple"),
                "classes": sel.get("class", []),
                "options": options,
                "attrs": dict(sel.attrs),
                "selector": _element_selector(sel),
            }
        )
    return results


def _extract_links(soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for a in soup.find_all("a"):
        href = a.get("href")
        text = a.get_text(strip=True) or ""
        results.append(
            {
                "tag": a.name,
                "href": href,
                "text": text,
                "id": a.get("id"),
                "name": a.get("name"),
                "classes": a.get("class", []),
                "rel": a.get("rel"),
                "target": a.get("target"),
                "attrs": dict(a.attrs),
                "selector": _element_selector(a),
            }
        )
    return results


def _extract_forms(soup: BeautifulSoup, labels: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for form in soup.find_all("form"):
        inputs = []
        for inp in form.find_all(["input", "textarea", "select"]):
            tag_name = inp.name
            if tag_name == "select":
                options = [
                    {"value": o.get("value"), "text": o.get_text(strip=True), "selected": o.has_attr("selected")}
                    for o in inp.find_all("option")
                ]
                inputs.append({
                    "tag": inp.name,
                    "kind": "select",
                    "name": inp.get("name"),
                    "id": inp.get("id"),
                    "label": _get_label_for_element(inp, labels or {}),
                    "options": options,
                    "attrs": dict(inp.attrs),
                    "selector": _element_selector(inp),
                })
            else:
                inputs.append({
                    "tag": inp.name,
                    "kind": tag_name,
                    "type": inp.get("type") if inp.name == "input" else None,
                    "name": inp.get("name"),
                    "id": inp.get("id"),
                    "label": _get_label_for_element(inp, labels or {}),
                    "placeholder": inp.get("placeholder"),
                    "required": inp.has_attr("required"),
                    "attrs": dict(inp.attrs),
                    "selector": _element_selector(inp),
                })
        buttons = []
        for btn in form.find_all(["button", "input"]):
            if btn.name == "button" or (btn.name == "input" and btn.get("type") in ("submit", "button", "reset")):
                buttons.append({
                    "tag": btn.name,
                    "type": btn.get("type", "button"),
                    "text": btn.get_text(strip=True) if btn.name == "button" else btn.get("value"),
                    "id": btn.get("id"),
                    "name": btn.get("name"),
                    "label": _get_label_for_element(btn, labels or {}),
                    "attrs": dict(btn.attrs),
                    "selector": _element_selector(btn),
                })
        results.append(
            {
                "id": form.get("id"),
                "name": form.get("name"),
                "action": form.get("action"),
                "method": form.get("method", "get").lower(),
                "classes": form.get("class", []),
                "inputs": inputs,
                "buttons": buttons,
                "attrs": dict(form.attrs),
                "selector": _element_selector(form),
            }
        )
    return results


def _should_render_js(soup: BeautifulSoup, analysis: Dict[str, Any]) -> bool:
    script_tags = soup.find_all("script")
    if not script_tags:
        return False

    interactive = sum(
        analysis.get("counts", {}).get(key, 0)
        for key in ("buttons", "inputs", "selects", "forms")
    )
    return interactive == 0


def _find_local_driver_path(browser: str) -> Optional[str]:
    user_home = os.path.expanduser("~")
    candidates: List[str] = []
    if browser == "chrome":
        candidates.extend(glob.glob(os.path.join(user_home, ".cache", "selenium", "chromedriver", "**", "chromedriver.exe"), recursive=True))
        candidates.extend(glob.glob(os.path.join(user_home, ".wdm", "drivers", "chromedriver", "**", "chromedriver.exe"), recursive=True))
        candidates.extend(glob.glob(os.path.join(user_home, "Downloads", "**", "chromedriver.exe"), recursive=True))
    elif browser == "edge":
        candidates.extend(glob.glob(os.path.join(user_home, ".cache", "selenium", "msedgedriver", "**", "msedgedriver.exe"), recursive=True))
        candidates.extend(glob.glob(os.path.join(user_home, ".wdm", "drivers", "edgedriver", "**", "msedgedriver.exe"), recursive=True))
        candidates.extend(glob.glob(os.path.join(user_home, "Downloads", "**", "msedgedriver.exe"), recursive=True))

    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _render_page_html(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    if not _SELENIUM_AVAILABLE or webdriver is None or ChromeOptions is None or EdgeOptions is None or ChromeService is None or EdgeService is None or WebDriverWait is None or EC is None or ChromeDriverManager is None:
        raise URLAnalysisError("Selenium is not installed or unavailable for JS rendering")

    driver = None
    options = None
    try:
        # Allow manually-provided driver paths for offline or locked-down environments.
        chromedriver_path = (
            os.getenv("CHROME_DRIVER_PATH", "")
            or os.getenv("CHROMEDRIVER_PATH", "")
        ).strip().strip('"')
        edgedriver_path = (
            os.getenv("EDGE_DRIVER_PATH", "")
            or os.getenv("EDGEDRIVER_PATH", "")
        ).strip().strip('"')
        service = None
        used_browser = "chrome"

        if chromedriver_path:
            if not os.path.exists(chromedriver_path):
                raise URLAnalysisError(f"CHROME_DRIVER_PATH does not exist: {chromedriver_path}")
            service = ChromeService(chromedriver_path)
        elif edgedriver_path:
            if not os.path.exists(edgedriver_path):
                raise URLAnalysisError(f"EDGE_DRIVER_PATH does not exist: {edgedriver_path}")
            used_browser = "edge"
            service = EdgeService(edgedriver_path)
        else:
            # Look for a local driver executable in PATH or known cache folders before downloading
            path_chromedriver = (
                shutil.which("chromedriver")
                or shutil.which("chromedriver.exe")
                or _find_local_driver_path("chrome")
            )
            path_edgedriver = (
                shutil.which("msedgedriver")
                or shutil.which("msedgedriver.exe")
                or _find_local_driver_path("edge")
            )
            if path_chromedriver:
                LOGGER.info("Found local chromedriver at %s", path_chromedriver)
                service = ChromeService(path_chromedriver)
            elif path_edgedriver:
                LOGGER.info("Found local msedgedriver at %s", path_edgedriver)
                used_browser = "edge"
                service = EdgeService(path_edgedriver)
            else:
                try:
                    chromedriver_path = ChromeDriverManager().install()
                    service = ChromeService(chromedriver_path)
                except Exception as e:
                    LOGGER.warning("ChromeDriverManager failed to install driver: %s", e)
                    try:
                        from webdriver_manager.microsoft import EdgeChromiumDriverManager
                        edriver_path = EdgeChromiumDriverManager().install()
                        service = EdgeService(edriver_path)
                        used_browser = "edge"
                    except Exception as ee:
                        LOGGER.exception("EdgeDriverManager fallback also failed: %s", ee)
                        raise URLAnalysisError(
                            "Failed to obtain a suitable WebDriver. "
                            "Set CHROME_DRIVER_PATH or EDGE_DRIVER_PATH to a local driver binary, "
                            "or install a compatible chromedriver/msedgedriver in your PATH."
                        ) from ee

        if used_browser == "edge":
            options = EdgeOptions()
        else:
            options = ChromeOptions()

        options.headless = True
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--remote-allow-origins=*")

        LOGGER.debug(
            "Launching Selenium render: browser=%s driver_path=%s url=%s",
            used_browser,
            getattr(service, "path", None) or getattr(service, "executable_path", None),
            url,
        )

        # Start the appropriate webdriver
        if used_browser == "edge":
            driver = webdriver.Edge(service=service, options=options)
        else:
            driver = webdriver.Chrome(service=service, options=options)

        driver.set_page_load_timeout(timeout)
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        # Wait for rendered interactive elements if the page is a JavaScript-driven app.
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script(
                    "return !!document.querySelector('input,button,select,textarea,form')"
                )
            )
        except TimeoutException:
            LOGGER.warning("Timed out waiting for interactive elements after page load for %s", url)

        return driver.page_source
    except (WebDriverException, TimeoutException) as exc:
        LOGGER.exception("Selenium rendering failed for %s: %s", url, exc)
        raise URLAnalysisError("JS rendering via Selenium failed") from exc
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


async def analyze_url(url: str, render_js: bool = False, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Fetch and analyze a URL, returning structured JSON suitable for AI-driven test generation.

    Args:
        url: The webpage URL to analyze.
        render_js: If True, force a headless browser render and parse the final client-side DOM.
        timeout: Request timeout in seconds.

    Returns:
        A dict containing page metadata and lists of extracted elements.

    Raises:
        URLAnalysisError: on validation, network, or parsing failures.
    """
    normalized_url = _extract_raw_url_from_input(url)
    if not normalized_url:
        raise URLAnalysisError("Invalid or malformed URL input")
    if not _is_valid_url(normalized_url):
        raise URLAnalysisError("Invalid URL scheme or hostname")

    parsed = urlparse(normalized_url)
    if _is_private_host(parsed.hostname or ""):
        raise URLAnalysisError("Refusing to analyze private or loopback hosts")
    url = normalized_url

    headers = {"User-Agent": USER_AGENT}
    verify_attempts = [VERIFY_SSL]
    if VERIFY_SSL:
        verify_attempts.append(False)

    last_exc: Optional[Exception] = None
    resp = None

    def _fetch_with_requests(verify_ssl: bool):
        try:
            return requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, verify=verify_ssl)
        except Exception as exc:
            raise exc

    for verify_ssl in verify_attempts:
        if _HTTPX_AVAILABLE:
            try:
                async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True, verify=verify_ssl) as client:
                    resp = await client.get(url)
                break
            except httpx.RequestError as exc:
                last_exc = exc
                if verify_ssl:
                    LOGGER.warning("Initial fetch failed for %s with SSL verification enabled; retrying with verification disabled: %s", url, exc)
                    continue
                LOGGER.exception("Request failed for %s: %s", url, exc)
                raise URLAnalysisError(f"Failed to fetch URL: {exc}") from exc
        elif _REQUESTS_AVAILABLE:
            try:
                resp = await asyncio.to_thread(_fetch_with_requests, verify_ssl)
                break
            except Exception as exc:
                last_exc = exc
                if verify_ssl:
                    LOGGER.warning("Initial fetch failed for %s with SSL verification enabled; retrying with verification disabled: %s", url, exc)
                    continue
                LOGGER.exception("Request failed for %s: %s", url, exc)
                raise URLAnalysisError(f"Failed to fetch URL: {exc}") from exc
        else:
            raise URLAnalysisError("No HTTP client available to fetch URL; install httpx or requests.")

    if resp is None:
        raise URLAnalysisError(f"Failed to fetch URL: {last_exc}") from last_exc

    if getattr(resp, 'status_code', None) is None:
        raise URLAnalysisError("Unexpected response object from HTTP client")
    if resp.status_code >= 400:
        raise URLAnalysisError(f"Failed to fetch URL, status_code={resp.status_code}")

    html = resp.text

    # parse with BeautifulSoup
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        # fallback to html.parser
        soup = BeautifulSoup(html, "html.parser")

    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    meta_description = ""
    md = soup.find("meta", attrs={"name": "description"})
    if md and md.get("content"):
        meta_description = md.get("content")

    labels = _extract_label_mapping(soup)
    buttons = _extract_buttons(soup)
    inputs = _extract_inputs(soup, labels=labels)
    selects = _extract_selects(soup, labels=labels)
    links = _extract_links(soup, url)
    forms = _extract_forms(soup, labels=labels)
    ids_classes = _collect_ids_and_classes(soup)

    counts = {
        "buttons": len(buttons),
        "inputs": len(inputs),
        "selects": len(selects),
        "links": len(links),
        "forms": len(forms),
    }

    should_try_render = render_js or _should_render_js(soup, {"counts": counts})
    if should_try_render:
        try:
            rendered_html = _render_page_html(url, timeout)
            try:
                soup = BeautifulSoup(rendered_html, "lxml")
            except Exception:
                soup = BeautifulSoup(rendered_html, "html.parser")

            title = (soup.title.string.strip() if soup.title and soup.title.string else title)
            md = soup.find("meta", attrs={"name": "description"})
            if md and md.get("content"):
                meta_description = md.get("content")

            labels = _extract_label_mapping(soup)
            buttons = _extract_buttons(soup)
            inputs = _extract_inputs(soup, labels=labels)
            selects = _extract_selects(soup, labels=labels)
            links = _extract_links(soup, url)
            forms = _extract_forms(soup, labels=labels)
            ids_classes = _collect_ids_and_classes(soup)
            counts = {
                "buttons": len(buttons),
                "inputs": len(inputs),
                "selects": len(selects),
                "links": len(links),
                "forms": len(forms),
            }
        except URLAnalysisError:
            if render_js:
                raise
            LOGGER.warning("JS render fallback failed for %s, continuing with static analysis.", url)

    result = {
        "url": url,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "status_code": resp.status_code,
        "title": title,
        "meta_description": meta_description,
        "counts": counts,
        "ids": ids_classes.get("ids", []),
        "classes": ids_classes.get("classes", {}),
        "buttons": buttons,
        "inputs": inputs,
        "selects": selects,
        "links": links,
        "forms": forms,
        "html_snapshot": None,
    }

    return result


# Synchronous wrapper for convenience
def analyze_url_sync(url: str, render_js: bool = False, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    return asyncio.get_event_loop().run_until_complete(analyze_url(url, render_js=render_js, timeout=timeout))
