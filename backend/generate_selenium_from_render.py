import json
import asyncio
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from app.services import url_analysis_service as u
from app.services import selenium_service as sservice

def render_page(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        html = page.content()
        browser.close()
    return html

def build_analysis_from_html(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    ids = [elem.get('id') for elem in soup.find_all(attrs={'id': True}) if elem.get('id')]
    names = [elem.get('name') for elem in soup.find_all(attrs={'name': True}) if elem.get('name')]
    buttons = [elem.get('id') or elem.get('name') or elem.get('class') for elem in soup.find_all('button')]
    inputs = [elem.get('id') or elem.get('name') or elem.get('class') for elem in soup.find_all('input')]
    links = [elem.get('id') or elem.get('name') or elem.get('class') for elem in soup.find_all('a')]
    analysis = {
        "url": url,
        "ids": ids,
        "names": names,
        "buttons": buttons,
        "inputs": inputs,
        "links": links
    }
    return analysis

def main():
    url = input("Enter the URL to test: ").strip()
    html = render_page(url)
    analysis = build_analysis_from_html(url, html)
    bundle = asyncio.run(sservice.generate_selenium_bundle(
        testcases=None, testdata=None, scenarios=None, analysis=analysis
    ))
    print(json.dumps({"analysis": analysis, "selenium_bundle": bundle}, indent=2))
    for filename, content in bundle.get("files", {}).items():
        print(f"\n# {filename}\n{content}")

if __name__ == "__main__":
    main()