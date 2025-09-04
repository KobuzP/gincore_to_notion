import json
import re
import logging
from notion_client import Client
from config import NOTION_API_TOKEN, NOTION_DATABASE_ID, USERS_NAME_TO_NOTION_ID_MAP


class NotionAPI:
    def __init__(self):
        """
        Initializes the Notion API client with the provided token and database ID.
        """
        if not NOTION_API_TOKEN or not NOTION_DATABASE_ID:
            raise RuntimeError("Brak NOTION_API_TOKEN lub NOTION_DATABASE_ID (sprawdź .env)")

        self.notion = Client(auth=NOTION_API_TOKEN)
        self.database_id = NOTION_DATABASE_ID

    # Wyciąganie cyfr z tytułu (np. z "№ 2864" -> "2864")
    @staticmethod
    def _strip_symbols(val: str) -> str:
        if not val:
            return val
        m = re.search(r"(\d+)$", val)
        return m.group(1) if m else val

    def get_last_repair_order_number(self, property_name: str = "RMA"):
        """
        Retrieves the last added repair order number from the Notion database.
        Sorts by RMA descending and returns the first numeric part found.
        """
        try:
            response = self.notion.databases.query(
                database_id=self.database_id,
                sorts=[{"property": "RMA", "direction": "descending"}],
                page_size=1
            )

            if response and response.get("results"):
                latest_page = response["results"][0]
                properties = latest_page.get("properties", {})
                if property_name in properties:
                    prop_data = properties[property_name]
                    ptype = prop_data.get("type")

                    if ptype == "title":
                        items = prop_data.get("title", [])
                        if items:
                            raw = items[0].get("plain_text", "")
                            return self._strip_symbols(raw)
                    elif ptype == "number":
                        num = prop_data.get("number")
                        return str(num) if num is not None else None
                    elif ptype == "rich_text":
                        items = prop_data.get("rich_text", [])
                        if items:
                            raw = items[0].get("plain_text", "")
                            return self._strip_symbols(raw)
                return None
            return None
        except Exception as e:
            logging.exception("Błąd pobierania RMA z Notion: %s", e)
            return None

    def add_crm_data_to_notion(self, crm_data: dict) -> bool:
        """
        Adds a record to Notion based on data from CRM.
        Returns True if success, False otherwise.
        """
        properties = {}

        # RMA (Title) – wymagane
        rma_number = crm_data.get("RMA")
        if rma_number:
            properties["RMA"] = {"title": [{"text": {"content": f"№ {rma_number}"}}]}
        else:
            logging.warning("Brak 'RMA' w danych CRM – pomijam wpis.")
            return False

        # Klient
        v = crm_data.get("Klient")
        if v:
            properties["Klient"] = {"rich_text": [{"text": {"content": v}}]}

        # Numer telefonu
        v = crm_data.get("Numer telefonu")
        if v:
            properties["Numer telefonu"] = {"phone_number": v}

        # Producent (Select)
        v = crm_data.get("Producent")
        if v:
            properties["Producent"] = {"select": {"name": v}}

        # Typ urządzenia w CRM → Typ Urządzenia w Notion
        v = crm_data.get("Typ urządzenia")
        if v:
            properties["Typ Urządzenia"] = {"select": {"name": v}}

        # Model
        v = crm_data.get("Model")
        if v:
            properties["Model"] = {"rich_text": [{"text": {"content": v}}]}

        # Numer Seryjny → Numer Seryjny (SN)
        v = crm_data.get("Numer Seryjny")
        if v:
            properties["Numer Seryjny (SN)"] = {"rich_text": [{"text": {"content": v}}]}

        # Uwagi → Uwagi (obsługa)
        v = crm_data.get("Uwagi")
        if v:
            properties["Uwagi (obsługa)"] = {"rich_text": [{"text": {"content": v}}]}

        # Opis Usterki → Opis Usterki (Klient)
        v = crm_data.get("Opis Usterki")
        if v:
            properties["Opis Usterki (Klient)"] = {"rich_text": [{"text": {"content": v}}]}

        # Stan wizualny urządzenia
        v = crm_data.get("Stan wizualny urządzenia")
        if v:
            properties["Stan wizualny urządzenia"] = {
                "rich_text": [{"text": {"content": v}}]
            }

        # Technik (People)
        technician_full = crm_data.get("Technik")
        if technician_full:
            technician_name_for_lookup = technician_full.split("(")[0].strip()
            notion_user_id = USERS_NAME_TO_NOTION_ID_MAP.get(technician_name_for_lookup)
            if notion_user_id:
                properties["Technik"] = {"people": [{"id": notion_user_id}]}
            # brak else – po prostu nie dodajemy, by uniknąć komunikatów

        # Status Zgłoszenia (Status)
        properties["Status Zgłoszenia"] = {"status": {"name": "Nowe"}}

        # Manager Zgłoszenia (People) – stałe ID
        manager_user_id = USERS_NAME_TO_NOTION_ID_MAP.get("Piotr Urbanek")
        if manager_user_id:
            properties["Manager Zgłoszenia"] = {"people": [{"id": manager_user_id}]}

        # Priorytet (Select)
        properties["Priorytet"] = {"select": {"name": "Standardowy"}}

        # URL
        v = crm_data.get("URL")
        if v:
            properties["URL"] = {"url": v}

        try:
            self.notion.pages.create(
                parent={"database_id": self.database_id},
                properties=properties
            )
            return True
        except Exception as e:
            logging.exception("Błąd wysyłania danych do Notion: %s", e)
            return False

    # alias zgodny ze starą wersją
    def upsert_crm_data(self, crm_data: dict) -> bool:
        return self.add_crm_data_to_notion(crm_data)
