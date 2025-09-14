# gincore_playwright.py
import os, re, asyncio
from typing import Dict, Optional
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page

import config

load_dotenv()
BROWSERLESS_WS = os.getenv("BROWSERLESS_WS")

# Mapowanie Twoich locatorów (tak jak w Selenium) na selektory Playwright
def _selector(kind: str, value: str) -> str:
    kind = kind.lower()
    if kind == "xpath":
        return f"{value}"  # Playwright akceptuje //... bez prefixu
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

async def login(page: Page, username: str, password: str) -> bool:
    await page.goto(config.CRM_LOGIN_URL, wait_until="domcontentloaded")
    # Pola logowania
    u = _selector(*config.CRM_USERNAME_FIELD_LOCATOR)
    p = _selector(*config.CRM_PASSWORD_FIELD_LOCATOR)
    b = _selector(*config.CRM_LOGIN_BUTTON_LOCATOR)
    await page.fill(u, username)
    await page.fill(p, password)
    await page.click(b)
    # Poczekaj albo na nawigację, albo render strony po zalogowaniu
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
        return True
    except Exception:
        return False

async def open_repair_order(page: Page, rma_number: int) -> tuple[bool, bool]:
    """(page_ok, rma_not_found)"""
    url = f"{config.CRM_REPAIR_ORDER_BASE_URL}{rma_number}"
    try:
        await page.goto(url, wait_until="domcontentloaded")
        # Sprawdź, czy pojawił się komunikat 'not found'
        nf_sel = _selector(*config.CRM_RMA_NOT_FOUND_INDICATOR)
        nf = await page.locator(nf_sel).first
        if await nf.is_visible():
            return (False, True)
        # Dodatkowo chwilę daj na doładowanie
        await page.wait_for_load_state("networkidle", timeout=8000)
        return (True, False)
    except Exception:
        return (False, False)

async def read_crm_field_values(page: Page) -> Dict[str, Optional[str]]:
    data: Dict[str, Optional[str]] = {}
    for notion_prop, (kind, val) in config.CRM_DATA_FIELDS_TO_READ.items():
        sel = _selector(kind, val)
        loc = page.locator(sel).first
        try:
            # spróbuj value, jeśli to input/textarea, inaczej inner_text
            tag = (await loc.evaluate("el => el.tagName")).lower()
            if tag in ("input", "textarea", "select"):
                v = await loc.input_value()
                if not v:
                    v = (await loc.inner_text()).strip()
            else:
                v = (await loc.inner_text()).strip()
            if notion_prop == "Technik" and v:
                v = re.sub(r"\s*\(.*\)\s*$", "", v).strip()
            data[notion_prop] = v or None
        except Exception:
            data[notion_prop] = None
    return data
