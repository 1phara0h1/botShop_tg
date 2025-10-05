import sqlite3

def init_db():
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()
    # пользователи (по контактам / telegram id)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER UNIQUE,
        contact TEXT,
        username TEXT
    )
    """)
    # категории
    cur.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT UNIQUE
    )
    """)
    # продукты
    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER,
        title TEXT,
        description TEXT,
        price INTEGER, -- цена в "сотых" валюты для Telegram (например, копейки)
        currency TEXT,
        photo_file_id TEXT,
        FOREIGN KEY(category_id) REFERENCES categories(id)
    )
    """)
    # заказы
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_tg_id INTEGER,
        product_id INTEGER,
        amount INTEGER,
        currency TEXT,
        status TEXT,
        provider_payment_charge_id TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()
    print("DB initialized.")

if name == "__main__":
    init_db()