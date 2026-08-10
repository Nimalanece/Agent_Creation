import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE_URL = "https://demoqa.com/text-box"


def wait_for_element(driver, by, locator, timeout=15):
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((by, locator))
    )


def test_text_box_page_loads(driver):
    driver.get(BASE_URL)
    assert "demosite" in driver.title.lower()
    assert driver.find_element(By.TAG_NAME, "body").is_displayed()


def test_text_box_inputs_accept_text(driver):
    driver.get(BASE_URL)

    name_input = wait_for_element(driver, By.ID, "userName")
    name_input.clear()
    name_input.send_keys("Alice Example")
    assert "Alice Example" in name_input.get_attribute("value")

    email_input = wait_for_element(driver, By.ID, "userEmail")
    email_input.clear()
    email_input.send_keys("alice@example.com")
    assert "alice@example.com" in email_input.get_attribute("value")

    current_address = wait_for_element(driver, By.ID, "currentAddress")
    current_address.clear()
    current_address.send_keys("123 Main St")
    assert "123 Main St" in current_address.get_attribute("value")

    permanent_address = wait_for_element(driver, By.ID, "permanentAddress")
    permanent_address.clear()
    permanent_address.send_keys("456 Elm St")
    assert "456 Elm St" in permanent_address.get_attribute("value")


def test_text_box_submission_shows_output(driver):
    driver.get(BASE_URL)

    wait_for_element(driver, By.ID, "userName").send_keys("Alice Example")
    wait_for_element(driver, By.ID, "userEmail").send_keys("alice@example.com")
    wait_for_element(driver, By.ID, "currentAddress").send_keys("123 Main St")
    wait_for_element(driver, By.ID, "permanentAddress").send_keys("456 Elm St")

    submit_button = wait_for_element(driver, By.ID, "submit")
    submit_button.click()

    output_area = wait_for_element(driver, By.ID, "output")
    output_text = output_area.text.lower()

    assert "alice example" in output_text
    assert "alice@example.com" in output_text
    assert "123 main st" in output_text
    assert "456 elm st" in output_text
