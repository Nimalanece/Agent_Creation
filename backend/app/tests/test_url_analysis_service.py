from unittest.mock import patch

from app.services import url_analysis_service as service


def test_sanitize_url_extracts_href_from_anchor():
    assert service.sanitize_url('<a href="https://demoqa.com/text-box">https://demoqa.com/text-box</a>') == "https://demoqa.com/text-box"


def test_sanitize_url_removes_quotes_and_html_suffix():
    assert service.sanitize_url('"https://demoqa.com/text-box"') == "https://demoqa.com/text-box"
    assert service.sanitize_url("https://demoqa.com/text-box<br>") == "https://demoqa.com/text-box"


def test_sanitize_url_rejects_non_http_schemes_and_missing_urls():
    for value in ("javascript:alert(1)", "file:///tmp/page.html", "data:text/html,hello", "<span>not a url</span>"):
        assert service.sanitize_url(value) == ""


def test_validate_host_rejects_private_and_loopback_addresses():
    with patch.object(service.socket, "getaddrinfo", side_effect=lambda host, port: [(None, None, None, None, (host, 0))]):
        assert not service.validate_host("localhost")
        assert not service.validate_host("127.0.0.1")
        assert not service.validate_host("10.0.0.5")
        assert not service.validate_host("172.16.0.5")
        assert not service.validate_host("192.168.1.5")


def test_validate_host_allows_public_ip():
    with patch.object(service.socket, "getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
        assert service.validate_host("example.com")


def test_find_browser_binary_uses_chrome_install_dir_when_available():
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    with patch.object(service.shutil, "which", return_value=None), patch.object(service.os.path, "exists", side_effect=lambda p: p == chrome_path):
        assert service._find_browser_binary("chrome") == chrome_path


def test_find_browser_binary_uses_edge_install_dir_when_available():
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

    with patch.object(service.shutil, "which", return_value=None), patch.object(service.os.path, "exists", side_effect=lambda p: p == edge_path):
        assert service._find_browser_binary("edge") == edge_path


def test_preferred_browser_prefers_chrome_when_both_browsers_exist():
    with patch.object(service, "_find_browser_binary", side_effect=lambda browser: {
        "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    }[browser]):
        assert service._preferred_browser() == "chrome"
