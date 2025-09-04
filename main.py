# main.py
import os
import sys
import asyncio
import logging
import select
from getpass import getpass
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from playwright.async_api import async_playwright

import config
from notion_utils import NotionAPI
from gincore_playwright import (
    BROWSERLESS_WS,
    login,
    open_repair_order,
    read_crm_field_values,
)

# Konfiguracja logów
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

console = Console()

# Kolejność wyświetlania pól w tabeli (display_name, key_in_data)
ORDERED_FIELDS = [
    ("RMA", "RMA"),
    ("Klient", "Klient"),
    ("Numer telefonu", "Numer telefonu"),
    ("Typ urządzenia", "Typ urządzenia"),
    ("Producent", "Producent"),
    ("Model", "Model"),
    ("Numer Seryjny", "Numer Seryjny"),
    ("Opis Usterki", "Opis Usterki"),
    ("Stan wizualny urządzenia", "Stan wizualny urządzenia"),
    ("Technik", "Technik"),
    ("Uwagi", "Uwagi"),
    ("URL", "URL"),
]

# Mapowanie nazw pól na kolory w tabeli
FIELD_COLORS = {
    "RMA": "bold cyan",
    "Klient": "bright_blue",
    "Numer telefonu": "bright_cyan",
    "Typ urządzenia": "green",
    "Producent": "bright_green",
    "Model": "bright_green",
    "Numer Seryjny": "magenta",
    "Opis Usterki": "yellow",
    "Stan wizualny urządzenia": "yellow",
    "Technik": "bright_green",
    "Uwagi": "bright_magenta",
    "URL": "bright_blue",
}

def update_password():
    """Interaktywnie aktualizuje hasło CRM w pliku .env oraz konfiguracji."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        console.print(f"[red]Plik .env nie istnieje: {env_path}[/red]")
        return
    new_pass = getpass("Podaj nowe hasło do CRM: ")
    if not new_pass:
        console.print("[yellow]Hasło nie zostało zmienione.[/yellow]")
        return
    # Wczytaj i zmodyfikuj linie .env
    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    updated = False
    with open(env_path, "w", encoding="utf-8") as f:
        for line in lines:
            if line.strip().startswith("CRM_PASSWORD"):
                f.write(f'CRM_PASSWORD="{new_pass}"\n')
                updated = True
            else:
                f.write(line)
        if not updated:
            f.write(f'CRM_PASSWORD="{new_pass}"\n')
    # Odśwież konfigurację w pamięci
    config.CRM_PASSWORD = new_pass
    console.print("[green]Hasło CRM zostało zaktualizowane.[/green]")

def prompt_menu():
    """
    Wyświetla menu i czeka maksymalnie 3 sekundy na wybór użytkownika.
    Zwraca:
        "1" - skanuj wszystkie,
        "2" - pojedyncze RMA,
        "3" - zmiana hasła.
    Jeżeli nie podano wyboru w ciągu 3 sekund, domyślnie zwraca "1".
    """
    console.print("[bold]Wybierz tryb pracy:[/bold]")
    console.print("1. [cyan]Skanuj wszystkie nowe zgłoszenia[/cyan]")
    console.print("2. [magenta]Przetwórz pojedyncze zgłoszenie (podaj numer RMA)[/magenta]")
    console.print("3. [yellow]Zmień hasło do CRM[/yellow]")
    console.print("Jeśli nie wybierzesz nic w ciągu 3 sekund, rozpocznie się pełne skanowanie...\n")

    try:
        i, _, _ = select.select([sys.stdin], [], [], 3)
        if i:
            choice = sys.stdin.readline().strip()
        else:
            choice = "1"
    except Exception:
        # Fallback, jeśli select nie działa (np. na Windows)
        try:
            choice = input("Podaj numer opcji i naciśnij Enter (domyślnie 1): ").strip()
        except Exception:
            choice = "1"
        if not choice:
            choice = "1"
    return choice

async def process_all():
    """Skanuje kolejne numery RMA do momentu napotkania pierwszego braku."""
    # sprawdzenie .env
    load_dotenv()

    if not BROWSERLESS_WS:
        console.print("[red]Błąd: BROWSERLESS_WS nie ustawiono.[/red]")
        return
    if not config.CRM_USERNAME or not config.CRM_PASSWORD:
        console.print("[red]Błąd: CRM_USERNAME lub CRM_PASSWORD nie ustawiono.[/red]")
        return

    notion = NotionAPI()
    last = notion.get_last_repair_order_number()
    start_rma = int(last) + 1 if last else 1

    console.print("[bold blue]== Pełne skanowanie Gincore → Notion ==[/bold blue]")
    console.print(f"Start od RMA: [cyan]{start_rma}[/cyan]\n")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(BROWSERLESS_WS)
        except Exception as e:
            console.print(f"[red]Nie udało się połączyć do browserless: {e}[/red]")
            return

        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()

        try:
            if not await login(page, config.CRM_USERNAME, config.CRM_PASSWORD):
                console.print("[red]Logowanie do CRM nie powiodło się.[/red]")
                return

            current = start_rma
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Skanowanie...", total=None)
                while True:
                    console.print(f"\n[bold]Przetwarzanie RMA {current}[/bold]")
                    page_ok, not_found = await open_repair_order(page, current)

                    if not_found or not page_ok:
                        console.print(
                            f"[yellow]RMA {current} nie istnieje lub nie wczytano strony. Kończę skanowanie.[/yellow]"
                        )
                        break

                    crm_data = await read_crm_field_values(page)
                    crm_data["RMA"] = str(current)
                    crm_data["URL"] = f"{config.CRM_REPAIR_ORDER_BASE_URL}{current}"

                    # Budowanie tabeli kolorowej z ustaloną kolejnością
                    table = Table(show_header=False)
                    table.add_column("Pole", style="bold", width=28)
                    table.add_column("Wartość", style="white", overflow="fold")
                    for disp_name, key in ORDERED_FIELDS:
                        value = crm_data.get(key) or "-"
                        color = FIELD_COLORS.get(disp_name, "white")
                        table.add_row(f"[{color}]{disp_name}[/{color}]", value)
                    console.print(table)

                    if notion.add_crm_data_to_notion(crm_data):
                        console.print(f"[green]RMA {current} zapisano w Notion.[/green]")
                    else:
                        console.print(f"[red]Błąd zapisu RMA {current} do Notion.[/red]")

                    current += 1
                    progress.advance(task)
        finally:
            try:
                await page.close()
            except Exception:
                pass
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass

async def process_single(rma_number: str):
    """Przetwarza pojedyncze zgłoszenie o numerze RMA."""
    load_dotenv()

    if not BROWSERLESS_WS:
        console.print("[red]Błąd: BROWSERLESS_WS nie ustawiono.[/red]")
        return
    if not config.CRM_USERNAME or not config.CRM_PASSWORD:
        console.print("[red]Błąd: CRM_USERNAME lub CRM_PASSWORD nie ustawiono.[/red]")
        return

    try:
        rma_int = int(rma_number)
    except ValueError:
        console.print("[red]Błąd: numer RMA musi być liczbą całkowitą.[/red]")
        return

    notion = NotionAPI()
    console.print(f"[bold blue]== Pojedyncze zgłoszenie RMA {rma_int} ==[/bold blue]\n")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(BROWSERLESS_WS)
        except Exception as e:
            console.print(f"[red]Nie udało się połączyć do browserless: {e}[/red]")
            return

        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()

        try:
            if not await login(page, config.CRM_USERNAME, config.CRM_PASSWORD):
                console.print("[red]Logowanie do CRM nie powiodło się.[/red]")
                return

            page_ok, not_found = await open_repair_order(page, rma_int)

            if not_found or not page_ok:
                console.print(f"[yellow]RMA {rma_int} nie istnieje lub strona jest niedostępna.[/yellow]")
                return

            crm_data = await read_crm_field_values(page)
            crm_data["RMA"] = str(rma_int)
            crm_data["URL"] = f"{config.CRM_REPAIR_ORDER_BASE_URL}{rma_int}"

            table = Table(show_header=False)
            table.add_column("Pole", style="bold", width=28)
            table.add_column("Wartość", style="white", overflow="fold")
            for disp_name, key in ORDERED_FIELDS:
                value = crm_data.get(key) or "-"
                color = FIELD_COLORS.get(disp_name, "white")
                table.add_row(f"[{color}]{disp_name}[/{color}]", value)
            console.print(table)

            if notion.add_crm_data_to_notion(crm_data):
                console.print(f"[green]RMA {rma_int} zapisano w Notion.[/green]")
            else:
                console.print(f"[red]Błąd zapisu RMA {rma_int} do Notion.[/red]")

        finally:
            try:
                await page.close()
            except Exception:
                pass
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass

def main():
    load_dotenv()

    choice = prompt_menu()
    if choice == "3":
        update_password()
        # po zmianie hasła zakończ
    elif choice == "2":
        rma_str = input("Podaj numer RMA: ").strip()
        asyncio.run(process_single(rma_str))
    else:
        asyncio.run(process_all())

    console.print("\n[bold green]Zakończono działanie programu.[/bold green]")
    input("Naciśnij Enter, aby zamknąć...")

if __name__ == "__main__":
    main()
