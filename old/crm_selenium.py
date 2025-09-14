from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time

from config import (
    CRM_USERNAME, CRM_PASSWORD, CRM_LOGIN_URL, CRM_REPAIR_ORDER_BASE_URL,
    CRM_USERNAME_FIELD_LOCATOR, CRM_PASSWORD_FIELD_LOCATOR,
    CRM_LOGIN_BUTTON_LOCATOR, CRM_REPAIR_ORDER_SEARCH_FIELD_LOCATOR,
    CRM_REPAIR_ORDER_GO_BUTTON_LOCATOR, CRM_DATA_FIELDS_TO_READ,
    CRM_RMA_NOT_FOUND_INDICATOR
)

class CRMSelenium:
    def __init__(self):
        """
        Initializes the Selenium WebDriver.
        """
        self.driver = None
        self.wait = None
        print("CRMSelenium initialized.")

    def initialize_driver(self):
        """
        Sets up the Chrome WebDriver using webdriver_manager to handle driver downloads.
        Configures Chrome options like headless mode.
        """
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1920,1080") # Set a consistent window size
        options.add_argument("--start-maximized") # Maximize the window on start
        options.add_argument("--disable-dev-shm-usage") # Overcome limited resource problems

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait = WebDriverWait(self.driver, 30) # Increased wait time for potentially slow CRMs
            print("Selenium WebDriver initialized successfully.")
        except Exception as e:
            print(f"Failed to initialize Selenium WebDriver: {e}")
            raise # Re-raise the exception to stop execution if driver fails to initialize

    def _get_by_strategy(self, locator_type):
        """Helper to get Selenium's By strategy from a string."""
        locator_type_map = {
            "id": By.ID,
            "name": By.NAME,
            "xpath": By.XPATH,
            "css_selector": By.CSS_SELECTOR,
            "class_name": By.CLASS_NAME,
            "link_text": By.LINK_TEXT,
            "partial_link_text": By.PARTIAL_LINK_TEXT,
            "tag_name": By.TAG_NAME
        }
        return locator_type_map.get(locator_type.lower())

    def login_to_crm(self):
        """
        Navigates to the CRM login page and attempts to log in using provided credentials.
        """
        print(f"Navigating to CRM login page: {CRM_LOGIN_URL}")
        try:
            self.driver.get(CRM_LOGIN_URL)
            self.wait.until(EC.url_to_be(CRM_LOGIN_URL)) # Ensure the login page is loaded

            # Find and fill username field
            username_strategy = self._get_by_strategy(CRM_USERNAME_FIELD_LOCATOR[0])
            username_field = self.wait.until(EC.presence_of_element_located((username_strategy, CRM_USERNAME_FIELD_LOCATOR[1])))
            username_field.send_keys(CRM_USERNAME)
            print(f"Entered username: {CRM_USERNAME}")

            # Find and fill password field
            password_strategy = self._get_by_strategy(CRM_PASSWORD_FIELD_LOCATOR[0])
            password_field = self.wait.until(EC.presence_of_element_located((password_strategy, CRM_PASSWORD_FIELD_LOCATOR[1])))
            password_field.send_keys(CRM_PASSWORD)
            print("Entered password.")

            # Find and click login button
            login_button_strategy = self._get_by_strategy(CRM_LOGIN_BUTTON_LOCATOR[0])
            login_button = self.wait.until(EC.element_to_be_clickable((login_button_strategy, CRM_LOGIN_BUTTON_LOCATOR[1])))
            login_button.click()
            print("Clicked login button. Waiting for dashboard...")

            # Add a more robust check for successful login, e.g., waiting for an element
            # that only appears after successful login, or checking URL change
            # This example waits for the URL to change from the login URL
            self.wait.until(EC.url_changes(CRM_LOGIN_URL))
            print("Successfully logged into CRM.")
            return True
        except Exception as e:
            print(f"Error during CRM login: {e}")
            # Optionally take a screenshot for debugging
            self.driver.save_screenshot("crm_login_error.png")
            return False

    def _is_rma_not_found(self):
        """
        Checks if the current page indicates that the RMA was not found.
        Returns True if not found, False otherwise.
        """
        try:
            if CRM_RMA_NOT_FOUND_INDICATOR:
                strategy = self._get_by_strategy(CRM_RMA_NOT_FOUND_INDICATOR[0])

                short_wait = WebDriverWait(self.driver, 2)  # Shorter wait for this specific check
                short_wait.until(EC.presence_of_element_located((strategy, CRM_RMA_NOT_FOUND_INDICATOR[1])))
                print("Detected 'RMA Not Found' indicator on the page.")
                return True

            return False
        except Exception:
            # If the element is not found within the short wait, it's likely not an error page
            return False

    def open_repair_order(self, repair_order_number):
        """
        Opens the specified repair order in the CRM.
        Prioritizes direct URL access if CRM_REPAIR_ORDER_BASE_URL is set,
        otherwise attempts to use a search field.
        """
        print(f"Attempting to open repair order: {repair_order_number}")
        if CRM_REPAIR_ORDER_BASE_URL:
            full_url = f"{CRM_REPAIR_ORDER_BASE_URL}{repair_order_number}"
            print(f"Navigating directly to: {full_url}")
            try:
                self.driver.get(full_url)
                # Wait for the URL to contain the repair order number, or for a specific element
                # Using a general wait for page to load, then check for "not found"
                self.wait.until(EC.url_contains(str(repair_order_number)) or EC.presence_of_element_located(
                    (By.TAG_NAME, 'body')))  # Wait for body to be present

                if self._is_rma_not_found():
                    print(f"Repair order {repair_order_number} not found via direct URL.")
                    return False, True  # Page loaded, but RMA not found

                print(f"Successfully opened repair order {repair_order_number} via direct URL.")
                return True, False  # Page loaded, RMA found
            except Exception as e:
                print(
                    f"General error opening repair order directly via URL ({full_url}): {e}. Trying search if configured.")
                # Fallback to search if direct URL fails or is not applicable
                return self._search_for_repair_order(repair_order_number)
        else:
            print("CRM_REPAIR_ORDER_BASE_URL not configured. Attempting to search for repair order.")
            return self._search_for_repair_order(repair_order_number)

    def _search_for_repair_order(self, repair_order_number):
        """
        Internal helper to search for a repair order within the CRM if direct URL isn't used.
        """
        if not CRM_REPAIR_ORDER_SEARCH_FIELD_LOCATOR or not CRM_REPAIR_ORDER_GO_BUTTON_LOCATOR:
            print("Search locators are not configured in config.py. Cannot search for repair order.")
            return False

        try:
            search_field_strategy = self._get_by_strategy(CRM_REPAIR_ORDER_SEARCH_FIELD_LOCATOR[0])
            search_field = self.wait.until(EC.presence_of_element_located((search_field_strategy, CRM_REPAIR_ORDER_SEARCH_FIELD_LOCATOR[1])))
            search_field.clear()
            search_field.send_keys(repair_order_number)
            print(f"Entered '{repair_order_number}' into search field.")

            go_button_strategy = self._get_by_strategy(CRM_REPAIR_ORDER_GO_BUTTON_LOCATOR[0])
            go_button = self.wait.until(EC.element_to_be_clickable((go_button_strategy, CRM_REPAIR_ORDER_GO_BUTTON_LOCATOR[1])))
            go_button.click()
            print("Clicked search/go button. Waiting for results...")

            # Add a wait for the search results or the specific repair order page to load
            # This might be a new URL, a modal, or content appearing on the current page.
            # Adjust this wait condition based on your CRM's behavior.
            time.sleep(5) # A simple sleep as a fallback; prefer explicit waits
            print(f"Successfully searched for repair order: {repair_order_number}")
            return True
        except Exception as e:
            print(f"Error searching for repair order in CRM: {e}")
            self.driver.save_screenshot(f"crm_search_error_{repair_order_number}.png")
            return False

    def read_crm_field_values(self):
        """
        Reads values from the specified CRM fields using their locators.

        Returns:
            dict: A dictionary where keys are Notion property names and values are
                  the extracted data from CRM.
        """
        extracted_data = {}
        print("Attempting to read data from CRM fields...")
        for notion_field_name, (locator_type, locator_value) in CRM_DATA_FIELDS_TO_READ.items():
            try:
                strategy = self._get_by_strategy(locator_type)
                element = self.wait.until(EC.presence_of_element_located((strategy, locator_value)))

                # Determine how to get the value based on the element's tag name
                if element.tag_name in ["input", "textarea"]:
                    value = element.get_attribute('value')
                elif element.tag_name == "select":
                    # For select elements, get the text of the selected option
                    from selenium.webdriver.support.ui import Select
                    select_element = Select(element)
                    value = select_element.first_selected_option.text
                else:
                    # For other elements (div, span, p, h1 etc.), get their text content
                    value = element.text

                extracted_data[notion_field_name] = value.strip()
                print(f"  Read '{notion_field_name}': '{extracted_data[notion_field_name]}'")
            except Exception as e:
                extracted_data[notion_field_name] = "N/A"
                print(f"  Could not read '{notion_field_name}' (Locator: {locator_type}, Value: {locator_value}): {e}")
                # Optionally take a screenshot for debugging specific field failures
                # self.driver.save_screenshot(f"crm_field_read_error_{notion_field_name}.png")
        return extracted_data

    def close_driver(self):
        """
        Closes the Selenium WebDriver.
        """
        if self.driver:
            self.driver.quit()
            print("Selenium driver closed.")

