import json
import asyncio
from bs4 import BeautifulSoup

try:
    # Use Playwright sync API when available
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

from app.services import url_analysis_service as u
from app.services import scenarios_service as sserv

URL = "https://demoqa.com/text-box"


def render_page(url: str) -> str:
    if sync_playwright is None:
        raise RuntimeError("playwright is not installed")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        html = page.content()
        browser.close()
    return html


def build_analysis_from_html(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    ids_classes = u._collect_ids_and_classes(soup)
    buttons = u._extract_buttons(soup)
    inputs = u._extract_inputs(soup)
    selects = u._extract_selects(soup)
    links = u._extract_links(soup, url)
    forms = u._extract_forms(soup)

    analysis = {
        "url": url,
        "fetched_at": None,
        "status_code": 200,
        "title": title,
        "meta_description": "",
        "counts": {
            "buttons": len(buttons),
            "inputs": len(inputs),
            "selects": len(selects),
            "links": len(links),
            "forms": len(forms),
        },
        "ids": ids_classes.get("ids", []),
        "classes": ids_classes.get("classes", {}),
        "buttons": buttons,
        "inputs": inputs,
        "selects": selects,
        "links": links,
        "forms": forms,
        "html_snapshot": None,
    }
    return analysis


def main():
    try:
        html = render_page(URL)
    except Exception as e:
        print(json.dumps({"error": "render_failed", "detail": str(e)}))
        return

    analysis = build_analysis_from_html(URL, html)

    # Call the existing async generator; fall back to conservative analysis-driven generator if the AI call fails.
    try:
        scenarios = asyncio.run(sserv.generate_scenarios(analysis))
    except Exception as e:
        # Use the conservative analysis-driven fallback directly to avoid external LLM dependency
        fallback = sserv._build_fallback_scenarios(analysis)
        scenarios = {"scenarios": fallback}

    output = {
        "analysis": analysis,
        "scenarios": scenarios.get("scenarios", []),
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
