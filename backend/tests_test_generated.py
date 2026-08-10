import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

BASE_URL = "https://demoqa.com/text-box"

@pytest.fixture
def driver():
    options = Options()
    options.add_argument("--start-maximized")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(5)
    yield driver
    driver.quit()

def wait_for_element(driver, by, locator, timeout=10):
    return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((by, locator)))

def test_page_loads(driver):
    driver.get(BASE_URL)
    assert driver.title
    assert "demosite" in driver.title
    assert driver.find_element(By.TAG_NAME, "body").is_displayed()

def test_form_fields_accept_input(driver):
    driver.get(BASE_URL)
    elem = wait_for_element(driver, By.ID, "userName")
    elem.clear()
    elem.send_keys("sample text")
    assert "sample text" in elem.get_attribute("value")
    elem = wait_for_element(driver, By.ID, "userEmail")
    elem.clear()
    elem.send_keys("test@example.com")
    assert "test@example.com" in elem.get_attribute("value")
    elem = wait_for_element(driver, By.ID, "currentAddress")
    elem.clear()
    elem.send_keys("sample text")
    assert "sample text" in elem.get_attribute("value")
    elem = wait_for_element(driver, By.ID, "permanentAddress")
    elem.clear()
    elem.send_keys("sample text")
    assert "sample text" in elem.get_attribute("value")

def test_primary_button_is_present(driver):
    driver.get(BASE_URL)
    button = wait_for_element(driver, By.CSS_SELECTOR, "button.navbar-toggler")
    assert button.is_displayed()
    assert button.is_enabled()

def test_safe_link_is_available(driver):
    driver.get(BASE_URL)
    link = wait_for_element(driver, By.CSS_SELECTOR, "a.router-link")
    assert link.is_displayed()
    assert link.get_attribute("href").endswith("text-box")
