import os
from dotenv import load_dotenv

load_dotenv()

CRM_LOGIN_URL = "https://serwisfixed.gincore.net/auth/login_form"
CRM_REPAIR_ORDER_BASE_URL = "https://serwisfixed.gincore.net/orders/"

CRM_USERNAME = os.getenv("CRM_USERNAME")
CRM_PASSWORD = os.getenv("CRM_PASSWORD")

NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

CRM_USERNAME_FIELD_LOCATOR = ("name", "login")
CRM_PASSWORD_FIELD_LOCATOR = ("name", "password")
CRM_LOGIN_BUTTON_LOCATOR = ("xpath", "//button[contains(text(), 'Sign In')]")

CRM_REPAIR_ORDER_SEARCH_FIELD_LOCATOR = ("id", "repairOrderSearchInput")
CRM_REPAIR_ORDER_GO_BUTTON_LOCATOR = ("id", "searchButton")
CRM_RMA_NOT_FOUND_INDICATOR = ("xpath", "//h4[contains(text(), 'Order not found')]")

CRM_DATA_FIELDS_TO_READ = {
    "Klient": ("xpath", "//div[contains(@class,'order-edit-client')]/a"),
    "Numer telefonu": ("xpath", "//div[contains(@class,'order-edit-client-phone')]/a"),
    "Producent": ("name", "users_fields[u_producent]"),
    "Typ urządzenia": ("name", "users_fields[u_typ_urzadzenia]"),
    "Model": ("name", "categories-goods-value[]"),
    "Numer Seryjny": ("name", "serial[]"),
    "Uwagi": ("name", "users_fields[u_komentarz_do_zlecenia]"),
    "Opis Usterki": ("name", "defect"),
    "Stan wizualny urządzenia": ("name", "comment"),
    "Technik": ("xpath", "//select[@name='engineer']/../div/button/span"),
}

USERS_NAME_TO_NOTION_ID_MAP = {
    "Marian": "e9b2da1f-9ee2-4f0b-bf37-dbe991877990",
    "Piotr Urbanek": "7724bbb5-9400-40e3-b08e-11f7ee6ec9f3",
}
