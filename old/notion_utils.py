import requests
from notion_client import Client
import json
from config import NOTION_API_TOKEN, NOTION_DATABASE_ID, USERS_NAME_TO_NOTION_ID_MAP


class NotionAPI:
    def __init__(self):
        """
        Initializes the Notion API client with the provided token and database ID.
        """
        self.notion = Client(auth=NOTION_API_TOKEN)
        self.database_id = NOTION_DATABASE_ID
        print("NotionAPI initialized.")

    def get_last_repair_order_number(self, property_name="RMA"):
        """
        Retrieves the last added repair order number from the Notion database.
        It queries the database, sorts by 'Created time' in descending order,
        and picks the first result.

        Args:
            property_name (str): The name of the property in Notion that holds
                                 the repair order number. Defaults to "Repair Order Number".

        Returns:
            str or None: The repair order number as a string, or None if not found or an error occurs.
        """
        try:
            print(f"Querying Notion database '{self.database_id}' for last '{property_name}'...")
            # Query the database, ordering by creation time to get the latest entry
            response = self.notion.databases.query(
                database_id=self.database_id,
                sorts=[
                    {"property": "RMA", "direction": "descending"}
                ],
                page_size=1  # We only need the latest one
            )

            if response and response["results"]:
                latest_page = response["results"][0]
                print(latest_page)
                properties = latest_page["properties"]
                print(f"props: {properties}")

                # Extract the value based on the property type.
                # You might need to adjust this logic based on your Notion property's exact type.
                if property_name in properties:
                    prop_data = properties[property_name]
                    if prop_data["type"] == "title":
                        if prop_data["title"]:
                            return prop_data["title"][0]["plain_text"]
                    elif prop_data["type"] == "number":
                        return str(prop_data["number"])  # Convert number to string for consistency
                    elif prop_data["type"] == "rich_text":
                        if prop_data["rich_text"]:
                            return prop_data["rich_text"][0]["plain_text"]
                    else:
                        print(f"Unsupported Notion property type for '{property_name}': {prop_data['type']}")
                else:
                    print(f"Property '{property_name}' not found in the latest Notion entry.")
                return None
            else:
                print("No entries found in Notion database or database query failed.")
                return None
        except Exception as e:
            print(f"Error getting last repair order number from Notion: {e}")
            return None

    def add_crm_data_to_notion(self, crm_data):
        """
        Adds data extracted from CRM to the Notion database.
        This function assumes 'crm_data' is a dictionary where keys are Notion property names
        and values are the data to be inserted.

        Args:
            crm_data (dict): A dictionary containing the data to be sent to Notion.
                             Example: {
                                 "Repair Order Number": "12345",
                                 "Customer Name": "John Doe",
                                 "Repair Status": "Completed"
                             }
        """
        properties = {}
        # RMA (Title property) - REQUIRED for page creation
        rma_number = crm_data.get("RMA")
        if rma_number:
            properties["RMA"] = {"title": [{"text": {"content": f"№ {rma_number}"}}]}
        else:
            print("Error: 'RMA' number is missing from CRM data. Cannot create Notion page.")
            return  # Cannot create a page without a title

        # Klient (Rich Text)
        if "Klient" in crm_data and crm_data["Klient"]:
            properties["Klient"] = {"rich_text": [{"text": {"content": crm_data["Klient"]}}]}

        # Numer telefonu (Phone Number)
        if "Numer telefonu" in crm_data and crm_data["Numer telefonu"]:
            properties["Numer telefonu"] = {"phone_number": crm_data["Numer telefonu"]}

        # Producent (Select)
        if "Producent" in crm_data and crm_data["Producent"]:
            properties["Producent"] = {"select": {"name": crm_data["Producent"]}}

        # Typ Urządzenia (Select) - Optional field, will be skipped if not present in crm_data
        if "Typ urządzenia" in crm_data and crm_data["Typ urządzenia"]:
            properties["Typ Urządzenia"] = {"select": {"name": crm_data["Typ urządzenia"]}}

        # Model (Rich Text)
        if "Model" in crm_data and crm_data["Model"]:
            properties["Model"] = {"rich_text": [{"text": {"content": crm_data["Model"]}}]}

        # Numer Seryjny (SN) (Rich Text)
        # Note: CRM data has "Numer Seryjny", Notion has "Numer Seryjny (SN)"
        if "Numer Seryjny" in crm_data and crm_data["Numer Seryjny"]:
            properties["Numer Seryjny (SN)"] = {"rich_text": [{"text": {"content": crm_data["Numer Seryjny"]}}]}

        # Uwagi (obsługa) (Rich Text)
        # Note: CRM data has "Uwagi", Notion has "Uwagi (obsługa)"
        if "Uwagi" in crm_data and crm_data["Uwagi"]:
            properties["Uwagi (obsługa)"] = {"rich_text": [{"text": {"content": crm_data["Uwagi"]}}]}

        # Opis Usterki (Klient) (Rich Text)
        # Note: CRM data has "Opis Usterki", Notion has "Opis Usterki (Klient)"
        if "Opis Usterki" in crm_data and crm_data["Opis Usterki"]:
            properties["Opis Usterki (Klient)"] = {"rich_text": [{"text": {"content": crm_data["Opis Usterki"]}}]}

        # Stan wizualny urządzenia (Rich Text)
        if "Stan wizualny urządzenia" in crm_data and crm_data["Stan wizualny urządzenia"]:
            properties["Stan wizualny urządzenia"] = {
                "rich_text": [{"text": {"content": crm_data["Stan wizualny urządzenia"]}}]}

        technician_full_crm_string = crm_data.get("Technik")
        if technician_full_crm_string:
            technician_name_for_lookup = technician_full_crm_string.split('(')[0].strip()
            if technician_name_for_lookup in USERS_NAME_TO_NOTION_ID_MAP:
                notion_user_id = USERS_NAME_TO_NOTION_ID_MAP[technician_name_for_lookup]
                properties["Technik"] = {"people": [{"id": notion_user_id}]}
                print(f"Mapped technician '{technician_name_for_lookup}' to Notion people property.")
            else:
                print(
                    f"Warning: Technician name '{technician_name_for_lookup}' found but no Notion ID mapping in config.py for this name.")
        else:
            print("No 'Technik' data found in CRM for mapping to Notion people property.")

        properties["Status Zgłoszenia"] = {'status': {'name': 'Nowe'}}
        manager_user_id = USERS_NAME_TO_NOTION_ID_MAP["Piotr Urbanek"]
        properties["Manager Zgłoszenia"] = {"people": [{"id": manager_user_id}]}
        properties["Priorytet"] = {"select": {"name": "Standardowy"}}

        if "URL" in crm_data and crm_data["URL"]:
            properties["URL"] = {"url": crm_data["URL"]}

        print(f'properties: {properties}')

        try:
            print(f"Attempting to add/update Notion page with data: {crm_data.get('RMA', 'N/A')}")
            self.notion.pages.create(
                parent={"database_id": self.database_id},
                properties=properties
            )
            print(f"Successfully sent data to Notion for repair order: {crm_data.get('RMA', 'N/A')}")
        except Exception as e:
            print(f"Error sending data to Notion: {e}")
            print(f"Data attempted to send: {json.dumps(properties, indent=2)}")

