# crm_selenium.py
import os, re, time, logging
from typing import Dict, Tuple, Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import config

_BY = {
    "id": By.ID, "name": By.NAME, "class_name": By.CLASS_NAME,
    "xpath": By.XPATH, "css_selector": By.CSS_SELECTOR,
    "link_text": By.LINK_TEXT, "partial_link_text": By.PARTIAL_LINK_TEXT,
    "tag_name": By.TAG_NAME,
}
def _loc(tup): kind, val = tup; return (_BY[kind], val)

class CRMSelenium:
    def __init__(self, headless: bool = True, timeout: int = 20):
        self.timeout = timeout
        self.driver = self._init_driver(headless=headless)
        self.wait = WebDriverWait(self.driver, timeout)

    def _init_driver(self, headless: bool) -> webdriver.Chrome:
        opts = Options()
        if headless:
            # nowszy headless (Chrome 109+)
            opts.add_argument("--headless=new")
        # stabilność w kontenerach/serwerach
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        # opcjonalne binaria z env
        chrome_bin = os.getenv("CHROME_BINARY")
        if chrome_bin:
            opts.binary_location = chrome_bin
        drv = webdriver.Chrome(options=opts)
        return drv

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass

    # ---------- Logowanie ----------
    def login(self, username: str, password: str) -> bool:
        self.driver.get(config.CRM_LOGIN_URL)
        try:
            self.wait.until(EC.presence_of_element_located(_loc(config.CRM_USERNAME_FIELD_LOCATOR))).send_keys(username)
            self.driver.find_element(*_loc(config.CRM_PASSWORD_FIELD_LOCATOR)).send_keys(password)
            self.driver.find_element(*_loc(config.CRM_LOGIN_BUTTON_LOCATOR)).click()

            # Czekamy aż formularz zniknie lub zmieni się kontekst/URL
            self.wait.until(EC.any_of(
                EC.url_contains("gincore.net"),
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            ))
            return True
        except Exception as e:
            logging.exception("Błąd logowania do CRM: %s", e)
            return False

    # ---------- Otwieranie i odczyt jednego zlecenia ----------
    def open_repair_order(self, rma_number: int) -> Tuple[bool, bool]:
        """
        Zwraca tuple: (page_loaded_ok: bool, rma_not_found: bool)
        Gwarantuje spójny zwrot – NIE miesza typów.
        """
        url = f"{config.CRM_REPAIR_ORDER_BASE_URL}{rma_number}"
        try:
            self.driver.get(url)
            self.wait.until(EC.any_of(
                EC.presence_of_element_located(_loc(config.CRM_RMA_NOT_FOUND_INDICATOR)),
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            ))
            # „not found”?
            if self.driver.find_elements(*_loc(config.CRM_RMA_NOT_FOUND_INDICATOR)):
                return (False, True)
            return (True, False)
        except Exception as e:
            logging.warning("Błąd ładowania RMA %s: %s", rma_number, e)
            return (False, False)

    def read_crm_field_values(self) -> Dict[str, Optional[str]]:
        """
        Czyta pola wg config.CRM_DATA_FIELDS_TO_READ, normalizuje 'Technik'.
        Brak pola -> None (zamiast 'N/A').
        """
        data: Dict[str, Optional[str]] = {}
        for notion_prop, locator in config.CRM_DATA_FIELDS_TO_READ.items():
            try:
                el = self.driver.find_element(*_loc(locator))
                tag = (el.tag_name or "").lower()
                if tag in ("input", "textarea"):
                    val = el.get_attribute("value") or el.text
                else:
                    val = el.text
                if notion_prop == "Technik" and val:
                    # obcięcie sufiksów w stylu "(workload ...)"
                    val = re.sub(r"\s*\(.*\)\s*$", "", val).strip()
                data[notion_prop] = (val or "").strip() or None
            except Exception:
                data[notion_prop] = None
        return data
