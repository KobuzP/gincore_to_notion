# gincore_playwright.py
import os
import re
from typing import Dict, Optional, Tuple
from dotenv import load_dotenv
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

import config

load_dotenv()
BROWSERLESS_WS = os.getenv("BROWSERLESS_WS")

# --- Mapowanie Twoich locatorów (jak w Selenium) na selektory Playwright ---
def _selector(kind: str, value: str) -> str:
    kind = kind.lower()
    if kind == "xpath":
        return value  # Playwright akceptuje //... bez prefixu
    if kind == "css_selector":
        return value
    if kind == "id":
        return f"#{value}"
    if kind == "name":
        return f'[name="{value}"]'
    if kind == "class_name":
        return f".{value}"
    if kind == "link_text":
        return f':text("{value}")'
    if kind == "partial_link_text":
        return f':text("{value}")'
    if kind == "tag_name":
        return value
    raise ValueError(f"Nieobsługiwany rodzaj lokatora: {kind}")

# --- Logowanie ---
async def login(page: Page, username: str, password: str) -> bool:
    await page.goto(config.CRM_LOGIN_URL, wait_until="domcontentloaded")
    u = _selector(*config.CRM_USERNAME_FIELD_LOCATOR)
    p = _selector(*config.CRM_PASSWORD_FIELD_LOCATOR)
    b = _selector(*config.CRM_LOGIN_BUTTON_LOCATOR)
    await page.fill(u, username)
    await page.fill(p, password)
    await page.click(b)
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
        return True
    except Exception:
        return False

# --- Pozytywna detekcja strony zlecenia ---
async def _is_order_page_loaded(page: Page) -> bool:
    for _, (kind, val) in config.CRM_DATA_FIELDS_TO_READ.items():
        sel = _selector(kind, val)
        try:
            if await page.locator(sel).first.is_visible():
                return True
        except Exception:
            continue
    return False

URL_CANDIDATES_SUFFIXES = [
    "",        # .../orders/2865
    "view/",   # .../orders/view/2865
    "edit/",   # .../orders/edit/2865
]

# --- Otwieranie zlecenia: kilka wariantów URL + fallback wyszukiwarka ---

# gincore_playwright.py (fragment)
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

async def open_repair_order(page: Page, rma_number: int) -> tuple[bool, bool]:
    """
    Spróbuj otworzyć stronę RMA i zwróć (page_ok, not_found).
    Jeśli status HTTP==404, uznajemy, że RMA nie istnieje.
    """
    base = config.CRM_REPAIR_ORDER_BASE_URL
    base = base if base.endswith("/") else base + "/"

    for suf in URL_CANDIDATES_SUFFIXES:
        try_url = f"{base}{suf}{rma_number}"
        try:
            # Używamy wait_until="commit", aby nie czekać na pełne załadowanie strony
            # oraz krótszy timeout (5 s zamiast domyślnych 30 s).
            response = await page.goto(try_url, wait_until="commit", timeout=5000)
            if response:
                status = response.status
                # 404 -> RMA nie istnieje
                if status == 404:
                    return (False, True)
            else:
                # Jeśli response jest None, Playwright nie zwrócił obiektu (może być redirect).
                # Sprawdźmy później po widocznych elementach
                pass

        except PlaywrightTimeoutError:
            # Zbyt długie ładowanie – potraktuj jako niezaładowanie strony
            return (False, False)

        # Sprawdź, czy nie wypadło logowanie
        try:
            login_sel = _selector(*config.CRM_USERNAME_FIELD_LOCATOR)
            if await page.locator(login_sel).first.is_visible():
                return (False, False)
        except Exception:
            pass

        # Pozytywna detekcja elementów: strona jest załadowana
        try:
            if await _is_order_page_loaded(page):
                return (True, False)
        except Exception:
            pass

        # Negatywna detekcja: widoczny komunikat "Order not found"
        try:
            nf_sel = _selector(*config.CRM_RMA_NOT_FOUND_INDICATOR)
            if await page.locator(nf_sel).first.is_visible():
                return (False, True)
        except Exception:
            pass

        # Jeśli ta wersja URL nie zadziałała, spróbuj następnego sufiksu
    return (False, False)

# --- Wyszukiwarka ---
async def open_repair_order_via_search(page: Page, rma_number: int) -> Tuple[bool, bool]:
    """
    Używa lokatorów wyszukiwarki z configu:
      - CRM_REPAIR_ORDER_SEARCH_FIELD_LOCATOR
      - CRM_REPAIR_ORDER_GO_BUTTON_LOCATOR
    Zwraca (page_ok, rma_not_found)
    """
    try:
        base = config.CRM_REPAIR_ORDER_BASE_URL
        list_url = base if base.endswith("/") else f"{base}/"
        try:
            await page.goto(list_url, wait_until="domcontentloaded")
        except Exception:
            pass

        sf = _selector(*config.CRM_REPAIR_ORDER_SEARCH_FIELD_LOCATOR)
        go = _selector(*config.CRM_REPAIR_ORDER_GO_BUTTON_LOCATOR)

        await page.fill(sf, str(rma_number))
        await page.click(go)

        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

        if await _is_order_page_loaded(page):
            return (True, False)

        # negatywna detekcja
        try:
            nf_sel = _selector(*config.CRM_RMA_NOT_FOUND_INDICATOR)
            if await page.locator(nf_sel).first.is_visible():
                return (False, True)
        except Exception:
            pass

        return (False, False)

    except Exception:
        return (False, False)

# --- Odczyt wartości pól ---
async def read_crm_field_values(page: Page) -> Dict[str, Optional[str]]:
    data: Dict[str, Optional[str]] = {}
    for notion_prop, (kind, val) in config.CRM_DATA_FIELDS_TO_READ.items():
        sel = _selector(kind, val)
        loc = page.locator(sel).first
        try:
            tag = (await loc.evaluate("el => el.tagName")).lower()
            if tag in ("input", "textarea", "select"):
                try:
                    v = await loc.input_value()
                except Exception:
                    v = (await loc.inner_text()).strip()
            else:
                v = (await loc.inner_text()).strip()
            if notion_prop == "Technik" and v:
                v = re.sub(r"\s*\(.*\)\s*$", "", v).strip()
            data[notion_prop] = v or None
        except Exception:
            data[notion_prop] = None
    return data
