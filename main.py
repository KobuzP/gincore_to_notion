#!/usr/bin/env python3
import argparse
import asyncio
import os
import sys
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

# Kolejność i kolory pól w tabeli
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

console = Console()

# ------------------- Funkcje główne -------------------

async def sync_all():
    """Skanuje i dodaje kolejne RMA aż do pierwszego braku zgłoszenia."""
    notion = NotionAPI()
    last = notion.get_last_repair_order_number()
    start_rma = int(last) + 1 if last else 1
    current = start_rma

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(BROWSERLESS_WS)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()

        await login(page, config.CRM_USERNAME, config.CRM_PASSWORD)

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
                        f"[yellow]RMA {current} nie istnieje lub nie można wczytać strony. Kończę skanowanie.[/yellow]"
                    )
                    break

                crm_data = await read_crm_field_values(page)
                crm_data["RMA"] = str(current)
                crm_data["URL"] = f"{config.CRM_REPAIR_ORDER_BASE_URL}{current}"

                # Kolorowa tabela
                table = Table(show_header=False)
                table.add_column("Pole", style="bold", width=28)
                table.add_column("Wartość", style="white", overflow="fold")
                for disp_name, key in ORDERED_FIELDS:
                    value = crm_data.get(key) or "-"
                    color = FIELD_COLORS.get(disp_name, "white")
                    table.add_row(f"[{color}]{disp_name}[/{color}]", value)
                console.print(table)

                if notion.add_crm_data_to_notion(crm_data):
                    console.print(f"[green]Zapisano RMA {current} w Notion.[/green]")
                else:
                    console.print(f"[red]Błąd przy zapisie RMA {current} do Notion.[/red]")

                current += 1
                progress.advance(task)

        await page.close()
        await context.close()
        await browser.close()

async def sync_single(rma_num: int):
    """Dodaje pojedyncze zgłoszenie o numerze RMA."""
    notion = NotionAPI()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(BROWSERLESS_WS)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()

        await login(page, config.CRM_USERNAME, config.CRM_PASSWORD)
        page_ok, not_found = await open_repair_order(page, rma_num)
        if not_found or not page_ok:
            console.print(f"[yellow]RMA {rma_num} nie istnieje lub nie można wczytać strony.[/yellow]")
        else:
            crm_data = await read_crm_field_values(page)
            crm_data["RMA"] = str(rma_num)
            crm_data["URL"] = f"{config.CRM_REPAIR_ORDER_BASE_URL}{rma_num}"
            table = Table(show_header=False)
            table.add_column("Pole", style="bold", width=28)
            table.add_column("Wartość", style="white", overflow="fold")
            for disp_name, key in ORDERED_FIELDS:
                value = crm_data.get(key) or "-"
                color = FIELD_COLORS.get(disp_name, "white")
                table.add_row(f"[{color}]{disp_name}[/{color}]", value)
            console.print(table)
            if notion.add_crm_data_to_notion(crm_data):
                console.print(f"[green]Zapisano RMA {rma_num} w Notion.[/green]")
            else:
                console.print(f"[red]Błąd przy zapisie RMA {rma_num} do Notion.[/red]")

        await page.close()
        await context.close()
        await browser.close()

def change_credentials():
    """Zmienia login i hasło CRM w pliku .env oraz w konfiguracji."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    new_user = input("Podaj nowy login do CRM: ").strip()
    new_pass = getpass("Podaj nowe hasło do CRM: ")

    lines = []
    user_updated = pass_updated = False
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("CRM_USERNAME"):
                lines.append(f'CRM_USERNAME="{new_user}"\n')
                user_updated = True
            elif line.startswith("CRM_PASSWORD"):
                lines.append(f'CRM_PASSWORD="{new_pass}"\n')
                pass_updated = True
            else:
                lines.append(line)
    if not user_updated:
        lines.append(f'CRM_USERNAME="{new_user}"\n')
    if not pass_updated:
        lines.append(f'CRM_PASSWORD="{new_pass}"\n')

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    config.CRM_USERNAME = new_user
    config.CRM_PASSWORD = new_pass
    console.print("[green]Zmieniono login i hasło CRM.[/green]")

# ------------------- Menu i CLI -------------------

def run_menu(timeout=3) -> str:
    console.print("\n[bold blue]== Gincore → Notion ==[/bold blue]")
    console.print("1. [cyan]Skanuj wszystkie nowe zgłoszenia[/cyan]")
    console.print("2. [magenta]Przetwarzaj pojedyncze zgłoszenie[/magenta]")
    console.print("3. [yellow]Zmień dane logowania CRM (login i hasło)[/yellow]")
    console.print("4. [red]Wyjście[/red]")
    console.print(f"[dim]Wybierz opcję [1-4] (domyślnie 1, jeśli nic nie wybierzesz w {timeout} s)...[/dim]")
    try:
        i, _, _ = select.select([sys.stdin], [], [], timeout)
        if i:
            return sys.stdin.readline().strip()
    except Exception:
        pass
    return "1"

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Synchronizacja CRM Gincore z Notion.")
    subparsers = parser.add_subparsers(dest="cmd")
    subparsers.add_parser("sync", help="Skanuj wszystkie nowe zgłoszenia.")
    sp_single = subparsers.add_parser("single", help="Dodaj pojedyncze zgłoszenie.")
    sp_single.add_argument("--rma", type=int, required=True, help="Numer RMA do dodania")
    subparsers.add_parser("credentials", help="Zmień login i hasło CRM.")
    args, _ = parser.parse_known_args()

    if args.cmd is None:
        choice = run_menu(timeout=3)
        if choice == "1":
            asyncio.run(sync_all())
        elif choice == "2":
            try:
                rma_num = int(input("Podaj numer RMA: ").strip())
                asyncio.run(sync_single(rma_num))
            except ValueError:
                console.print("[red]Błąd: numer RMA musi być liczbą całkowitą.[/red]")
        elif choice == "3":
            change_credentials()
        else:
            console.print("[dim]Zamykam program.[/dim]")
        return

    # Obsługa subkomend
    if args.cmd == "sync":
        asyncio.run(sync_all())
    elif args.cmd == "single":
        asyncio.run(sync_single(args.rma))
    elif args.cmd == "credentials":
        change_credentials()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
