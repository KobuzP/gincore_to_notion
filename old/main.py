from config import CRM_REPAIR_ORDER_BASE_URL
from notion_utils import NotionAPI
from crm_selenium import CRMSelenium
import logging

import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("automation.log"),
        logging.StreamHandler() # Also print to console if available (e.g., when debugging)
    ]
)

def main():
    """
    Main function to orchestrate the Notion-CRM data transfer.
    """
    logging.info("Automation script started.")
    notion_api = NotionAPI()
    crm_automation = CRMSelenium()

    try:
        logging.info("\n--- Step 1: Retrieving last repair order number from Notion ---")
        print("\n--- Step 1: Retrieving last repair order number from Notion ---")
        last_rma_str = notion_api.get_last_repair_order_number()
        last_rma_str = last_rma_str[2:]
        print(last_rma_str)

        if not last_rma_str:
            logging.info("No repair order number found in Notion database. Starting from a default (e.g., 1).")
            print("No repair order number found in Notion database. Starting from a default (e.g., 1).")
            return
        else:
            try:
                current_rma_number = int(last_rma_str) + 1
                logging.info(f"Successfully retrieved last RMA from Notion: '{last_rma_str}'. Starting scan from: {current_rma_number}")
                print(f"Successfully retrieved last RMA from Notion: '{last_rma_str}'. Starting scan from: {current_rma_number}")
            except ValueError:
                print(f"Last RMA '{last_rma_str}' from Notion is not a valid number. Please check Notion data. Exiting.")
                logging.error(f"Last RMA '{last_rma_str}' from Notion is not a valid number. Please check Notion data. Exiting.")
                return

        logging.info("\n--- Step 2: Initializing Selenium and logging into CRM ---")
        print("\n--- Step 2: Initializing Selenium and logging into CRM ---")
        crm_automation.initialize_driver()
        if not crm_automation.login_to_crm():
            logging.error("CRM login failed. Please check your CRM credentials and locators in config.py. Exiting.")
            print("CRM login failed. Please check your CRM credentials and locators in config.py.")
            return

        print("\n--- Step 3-5: Scanning CRM for new RMAs and pushing to Notion ---")
        logging.info("\n--- Step 3-5: Scanning CRM for new RMAs and pushing to Notion ---")

        processed_count = 0
        while True:
            logging.info(f"\nAttempting to process RMA number: {current_rma_number}")
            print(f"\nAttempting to process RMA number: {current_rma_number}")

            page_loaded_successfully, rma_not_found = crm_automation.open_repair_order(current_rma_number)

            if rma_not_found:
                logging.info(f"RMA number {current_rma_number} not found in CRM. Assuming Notion is up-to-date. Stopping scan.")
                print(
                    f"RMA number {current_rma_number} not found in CRM. Assuming Notion is up-to-date. Stopping scan.")
                break  # Exit the loop if RMA is not found
            elif not page_loaded_successfully:
                logging.warning(f"Failed to load page for RMA {current_rma_number} due to a general error. Skipping this RMA and continuing.")
                print(
                    f"Failed to load page for RMA {current_rma_number} due to a general error. Skipping this RMA and continuing.")
                # You might want to implement a retry mechanism or log this more thoroughly
                current_rma_number += 1
                continue  # Skip to the next RMA if page didn't load properly

            print(f"Page for RMA {current_rma_number} loaded. Reading data...")
            crm_data = crm_automation.read_crm_field_values()
            # Ensure the repair order number is part of the data to be sent back to Notion
            crm_data["RMA"] = str(current_rma_number)  # Ensure it's a string for Notion
            full_url = f"{CRM_REPAIR_ORDER_BASE_URL}{current_rma_number}"
            crm_data["URL"] = full_url

            logging.info("\n--- Extracted CRM Data ---")
            for key, value in crm_data.items():
                logging.info(f"{key}: {value}")
            logging.info("--------------------------")

            logging.info("Sending extracted CRM data to Notion...")
            print("Sending extracted CRM data to Notion...")
            notion_api.add_crm_data_to_notion(crm_data)
            processed_count += 1

            current_rma_number += 1
            time.sleep(1)

    except Exception as e:
        logging.exception(f"\nAn unhandled error occurred during the automation process: {e}")
        print(f"\nAn unhandled error occurred during the automation process: {e}")
    finally:
        # Ensure the browser is closed even if errors occur
        crm_automation.close_driver()
        print("Cleanup: Selenium driver closed.")
        logging.info("Cleanup: Selenium driver closed.")
        logging.info("Automation script finished.")

if __name__ == "__main__":
    main()
