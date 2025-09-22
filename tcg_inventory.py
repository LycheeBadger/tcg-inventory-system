import sqlite3
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re

# Note: This script requires the following libraries to be installed:
# pip install requests beautifulsoup4
# This is a simple CLI-based inventory tracking system for TCG cards.
# It uses SQLite for persistence. Run this script in a terminal.
# Database file: tcg_inventory.db

DB_FILE = 'tcg_inventory.db'

def init_db():
    """Initialize the database with required tables."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT
        )
    ''')
    
    # Cards table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            set_name TEXT,
            condition TEXT,  -- e.g., NM, LP, MP
            purchase_price REAL,
            current_owner_id INTEGER,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (current_owner_id) REFERENCES users (id)
        )
    ''')
    
    # Transactions table for tracking ins/outs/sells/transfers
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER,
            transaction_type TEXT,  -- 'in', 'out', 'sell', 'transfer'
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            price REAL,
            from_user_id INTEGER,
            to_user_id INTEGER,
            notes TEXT,
            FOREIGN KEY (card_id) REFERENCES cards (id),
            FOREIGN KEY (from_user_id) REFERENCES users (id),
            FOREIGN KEY (to_user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_ebay_last_sold_price(card_name):
    """
    Scrape eBay for the last sold price of a card.
    Note: This is a basic scraper and may break if eBay changes layout.
    eBay scraping is for personal use; consider using official API for production.
    Returns the most recent sold price or None if not found.
    """
    try:
        # Search for sold listings
        search_url = f"https://www.ebay.com/sch/i.html?_nkw={card_name.replace(' ', '+')}&_sacat=0&LH_Sold=1&LH_Complete=1&rt=nc&LH_PrefLoc=1"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find sold items - look for price in sold listings
        sold_items = soup.find_all('div', class_='s-item__info')
        for item in sold_items[:5]:  # Check top 5 for relevance
            price_elem = item.find('span', class_='s-item__price')
            if price_elem:
                price_text = price_elem.text.strip()
                # Extract numeric price, e.g., "$10.00" -> 10.00
                match = re.search(r'\$([\d,]+\.?\d*)', price_text)
                if match:
                    price = float(match.group(1).replace(',', ''))
                    # Also check if it's a sold item (look for 'sold' text)
                    sold_text = item.find(string=re.compile(r'sold', re.I))
                    if sold_text:
                        return price
        return None
    except Exception as e:
        print(f"Error fetching eBay price: {e}")
        return None

def add_user(username, email=None):
    """Add a new user."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO users (username, email) VALUES (?, ?)', (username, email))
        conn.commit()
        print(f"User '{username}' added successfully.")
    except sqlite3.IntegrityError:
        print(f"User '{username}' already exists.")
    conn.close()

def add_card(name, set_name, condition, purchase_price, owner_username):
    """Add a card to inventory for a user (in transaction)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get owner ID
    cursor.execute('SELECT id FROM users WHERE username = ?', (owner_username,))
    owner = cursor.fetchone()
    if not owner:
        print(f"Owner '{owner_username}' not found.")
        conn.close()
        return
    
    owner_id = owner[0]
    cursor.execute('''
        INSERT INTO cards (name, set_name, condition, purchase_price, current_owner_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, set_name, condition, purchase_price, owner_id))
    
    card_id = cursor.lastrowid
    conn.commit()
    
    # Log 'in' transaction
    cursor.execute('''
        INSERT INTO transactions (card_id, transaction_type, price, from_user_id, to_user_id)
        VALUES (?, 'in', ?, NULL, ?)
    ''', (card_id, purchase_price, owner_id))
    conn.commit()
    conn.close()
    print(f"Card '{name}' added to '{owner_username}'s inventory.")

def sell_card(card_name, seller_username, buyer_username=None, sale_price=None):
    """
    Sell a card (out transaction). If buyer_username provided, it's a transfer/sale between users.
    Updates current owner if buyer provided.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get seller ID and card
    cursor.execute('SELECT id FROM users WHERE username = ?', (seller_username,))
    seller = cursor.fetchone()
    if not seller:
        print(f"Seller '{seller_username}' not found.")
        conn.close()
        return
    seller_id = seller[0]
    
    cursor.execute('''
        SELECT id, current_owner_id FROM cards WHERE name = ? AND current_owner_id = ?
    ''', (card_name, seller_id))
    card = cursor.fetchone()
    if not card:
        print(f"Card '{card_name}' not found in '{seller_username}'s inventory.")
        conn.close()
        return
    
    card_id, _ = card
    
    # Get eBay last sold if no sale_price provided
    if sale_price is None:
        ebay_price = get_ebay_last_sold_price(card_name)
        if ebay_price:
            sale_price = ebay_price
            print(f"Using eBay last sold price: ${ebay_price}")
        else:
            sale_price = float(input("Enter sale price: "))
    
    # Log 'out' or 'sell' transaction
    transaction_type = 'sell' if buyer_username else 'out'
    to_user_id = None
    if buyer_username:
        cursor.execute('SELECT id FROM users WHERE username = ?', (buyer_username,))
        buyer = cursor.fetchone()
        if buyer:
            to_user_id = buyer[0]
            # Update card owner
            cursor.execute('UPDATE cards SET current_owner_id = ? WHERE id = ?', (to_user_id, card_id))
        else:
            print(f"Buyer '{buyer_username}' not found.")
    
    cursor.execute('''
        INSERT INTO transactions (card_id, transaction_type, price, from_user_id, to_user_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (card_id, transaction_type, sale_price, seller_id, to_user_id))
    conn.commit()
    conn.close()
    print(f"Card '{card_name}' sold for ${sale_price}.")

def transfer_card(card_name, from_username, to_username):
    """Transfer ownership of a card between users (no price change)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE username = ?', (from_username,))
    from_user = cursor.fetchone()
    if not from_user:
        print(f"From user '{from_username}' not found.")
        conn.close()
        return
    from_id = from_user[0]
    
    cursor.execute('SELECT id FROM users WHERE username = ?', (to_username,))
    to_user = cursor.fetchone()
    if not to_user:
        print(f"To user '{to_username}' not found.")
        conn.close()
        return
    to_id = to_user[0]
    
    cursor.execute('''
        UPDATE cards SET current_owner_id = ? WHERE name = ? AND current_owner_id = ?
    ''', (to_id, card_name, from_id))
    
    if cursor.rowcount > 0:
        cursor.execute('''
            INSERT INTO transactions (card_id, transaction_type, from_user_id, to_user_id)
            SELECT id, 'transfer', ?, ? FROM cards WHERE name = ? AND current_owner_id = ?
        ''', (from_id, to_id, card_name, from_id))
        conn.commit()
        print(f"Card '{card_name}' transferred from '{from_username}' to '{to_username}'.")
    else:
        print(f"Card '{card_name}' not found in '{from_username}'s inventory.")
    conn.close()

def view_inventory(username):
    """View a user's current inventory with purchase prices."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    if not user:
        print(f"User '{username}' not found.")
        conn.close()
        return
    user_id = user[0]
    
    cursor.execute('''
        SELECT name, set_name, condition, purchase_price FROM cards
        WHERE current_owner_id = ?
    ''', (user_id,))
    cards = cursor.fetchall()
    
    if not cards:
        print(f"No cards in '{username}'s inventory.")
    else:
        print(f"\n{username}'s Inventory:")
        print("-" * 50)
        for card in cards:
            print(f"Name: {card[0]}, Set: {card[1]}, Condition: {card[2]}, Purchase Price: ${card[3]:.2f}")
    conn.close()

def view_transactions(card_name=None, user_username=None):
    """View transaction history, optionally filtered by card or user."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    query = '''
        SELECT t.date, t.transaction_type, t.price, u1.username as from_user, u2.username as to_user, c.name
        FROM transactions t
        JOIN cards c ON t.card_id = c.id
        LEFT JOIN users u1 ON t.from_user_id = u1.id
        LEFT JOIN users u2 ON t.to_user_id = u2.id
    '''
    params = []
    
    if card_name:
        query += ' WHERE c.name = ?'
        params.append(card_name)
    elif user_username:
        query += ' WHERE u1.username = ? OR u2.username = ?'
        params.extend([user_username, user_username])
    
    query += ' ORDER BY t.date DESC'
    
    cursor.execute(query, params)
    trans = cursor.fetchall()
    
    if not trans:
        filter_str = f" for card '{card_name}'" if card_name else f" for user '{user_username}'" if user_username else ""
        print(f"No transactions found{filter_str}.")
    else:
        print("\nTransaction History:")
        print("-" * 80)
        print(f"{'Date':<20} {'Type':<10} {'Price':<8} {'From':<15} {'To':<15} {'Card':<20}")
        print("-" * 80)
        for t in trans:
            from_u = t[3] or 'N/A'
            to_u = t[4] or 'N/A'
            price = f"${t[2]:.2f}" if t[2] else 'N/A'
            print(f"{t[0][:19]:<20} {t[1]:<10} {price:<8} {from_u:<15} {to_u:<15} {t[5]:<20}")
    conn.close()

def search_ebay_price(card_name):
    """Standalone function to search eBay price for a card."""
    price = get_ebay_last_sold_price(card_name)
    if price:
        print(f"Last sold price on eBay for '{card_name}': ${price:.2f}")
    else:
        print(f"No recent sold listings found for '{card_name}'.")

def main_menu():
    """CLI Menu."""
    init_db()
    while True:
        print("\nTCG Inventory System")
        print("1. Add User")
        print("2. Add Card (In)")
        print("3. Sell Card (Out/Sell)")
        print("4. Transfer Card")
        print("5. View Inventory")
        print("6. View Transactions")
        print("7. Search eBay Price")
        print("8. Exit")
        
        choice = input("Choose option: ").strip()
        
        if choice == '1':
            username = input("Username: ").strip()
            email = input("Email (optional): ").strip() or None
            add_user(username, email)
        elif choice == '2':
            name = input("Card Name: ").strip()
            set_name = input("Set Name: ").strip()
            condition = input("Condition (e.g., NM): ").strip()
            purchase_price = float(input("Purchase Price: "))
            owner = input("Owner Username: ").strip()
            add_card(name, set_name, condition, purchase_price, owner)
        elif choice == '3':
            name = input("Card Name: ").strip()
            seller = input("Seller Username: ").strip()
            buyer = input("Buyer Username (optional): ").strip() or None
            if buyer:
                price_input = input("Sale Price (or press Enter for eBay lookup): ").strip()
                sale_price = float(price_input) if price_input else None
            else:
                sale_price = float(input("Sale Price: "))
            sell_card(name, seller, buyer, sale_price)
        elif choice == '4':
            name = input("Card Name: ").strip()
            from_u = input("From Username: ").strip()
            to_u = input("To Username: ").strip()
            transfer_card(name, from_u, to_u)
        elif choice == '5':
            username = input("Username: ").strip()
            view_inventory(username)
        elif choice == '6':
            card_filter = input("Filter by Card Name (or Enter for all): ").strip() or None
            user_filter = input("Filter by User (or Enter): ").strip() or None
            if card_filter:
                view_transactions(card_filter)
            elif user_filter:
                view_transactions(user_username=user_filter)
            else:
                view_transactions()
        elif choice == '7':
            name = input("Card Name: ").strip()
            search_ebay_price(name)
        elif choice == '8':
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main_menu()
