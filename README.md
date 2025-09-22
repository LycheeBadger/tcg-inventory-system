# tcg-inventory-system
# TCG Inventory System
A Python-based system for tracking trading card game (TCG) inventory, including purchase prices and eBay last sold prices. Supports multiple users and transaction tracking.

## Setup
1. Install dependencies: `pip install requests beautifulsoup4`
2. Run the script: `python tcg_inventory.py`
3. Follow the CLI menu to manage cards and users.

## Features
- Add users and cards
- Track card purchases and sales
- Transfer cards between users
- View inventory and transaction history
- Search eBay for last sold prices (basic scraper)

## Notes
- Requires SQLite database (`tcg_inventory.db`).
- eBay scraping is for personal use; consider using the eBay API for production.
