"""
database.py — SQLite schema, seed data, and query helpers
Boutique Hotel Room Service App
"""

import sqlite3
import uuid
import hashlib
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "hotel.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def generate_token():
    return uuid.uuid4().hex + uuid.uuid4().hex[:8]


def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def ensure_admin_password():
    """Always ensure the admin password is set correctly on startup."""
    conn = get_db()
    conn.execute("UPDATE admin_users SET password_hash=? WHERE email=?",
                 (hash_password("RoomS@TGH2026!"), "admin@hotel.com"))
    conn.commit()
    conn.close()


def init_db():
    conn = get_db()
    c = conn.cursor()

    # ── Rooms ─────────────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        id TEXT PRIMARY KEY,
        room_number TEXT UNIQUE NOT NULL,
        name TEXT,
        qr_token TEXT UNIQUE NOT NULL,
        charge_to_room_enabled INTEGER DEFAULT 1,
        charge_to_room_limit REAL DEFAULT 1500.0,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    # ── Menu Categories ───────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        icon TEXT DEFAULT '🍽️',
        display_order INTEGER DEFAULT 0,
        available_from TEXT,
        available_to TEXT,
        is_active INTEGER DEFAULT 1
    )""")

    # ── Menu Items ────────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS menu_items (
        id TEXT PRIMARY KEY,
        category_id TEXT NOT NULL REFERENCES categories(id),
        name TEXT NOT NULL,
        description TEXT,
        price REAL NOT NULL,
        photo_url TEXT,
        dietary_tags TEXT DEFAULT '[]',
        allergens TEXT,
        prep_time_minutes INTEGER DEFAULT 20,
        is_available INTEGER DEFAULT 1,
        display_order INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # ── Orders ────────────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        order_reference TEXT UNIQUE NOT NULL,
        room_id TEXT NOT NULL REFERENCES rooms(id),
        guest_name TEXT,
        status TEXT DEFAULT 'received',
        payment_method TEXT NOT NULL,
        payment_status TEXT DEFAULT 'pending',
        subtotal REAL NOT NULL,
        total_amount REAL NOT NULL,
        delivery_type TEXT DEFAULT 'asap',
        scheduled_for TEXT,
        order_notes TEXT,
        ip_address TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    # ── Order Items ───────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS order_items (
        id TEXT PRIMARY KEY,
        order_id TEXT NOT NULL REFERENCES orders(id),
        menu_item_id TEXT REFERENCES menu_items(id),
        item_name TEXT NOT NULL,
        item_price REAL NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        line_total REAL NOT NULL,
        notes TEXT
    )""")

    # ── Payments ──────────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY,
        order_id TEXT NOT NULL REFERENCES orders(id),
        gateway TEXT NOT NULL,
        gateway_reference TEXT,
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'ZAR',
        status TEXT DEFAULT 'pending',
        refund_amount REAL DEFAULT 0,
        refund_reason TEXT,
        paid_at TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    # ── Admin Users ───────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'kitchen',
        is_active INTEGER DEFAULT 1,
        last_login_at TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    # ── Order Status History ──────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS order_status_history (
        id TEXT PRIMARY KEY,
        order_id TEXT NOT NULL REFERENCES orders(id),
        from_status TEXT,
        to_status TEXT NOT NULL,
        changed_by TEXT,
        note TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    # ── Operating Hours ───────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS operating_hours (
        id TEXT PRIMARY KEY,
        day_of_week INTEGER NOT NULL,
        open_time TEXT DEFAULT '07:00',
        close_time TEXT DEFAULT '23:00',
        is_open INTEGER DEFAULT 1,
        closed_message TEXT DEFAULT 'Kitchen is currently closed'
    )""")

    conn.commit()
    _seed_data(conn)
    conn.close()


def _seed_data(conn):
    c = conn.cursor()

    # Only seed if empty
    if c.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] > 0:
        return

    print("Seeding database with sample data...")

    # ── 13 Rooms ──────────────────────────────────────────────────────────────
    rooms = ["1","2","3","4","5","6","7","8","9","10","11","12","13"]
    for num in rooms:
        c.execute("INSERT INTO rooms (id, room_number, name, qr_token) VALUES (?,?,?,?)",
                  (str(uuid.uuid4()), num, "", generate_token()))

    # ── Categories ────────────────────────────────────────────────────────────
    cats = [
        ("Breakfast",        "Start your morning right",           "🌅", 1, "07:00", "11:00"),
        ("Light Meals",      "Sandwiches, salads & snacks",        "🥗", 2, None,    None),
        ("Mains",            "Hearty dishes served all day",       "🍽️", 3, "11:00", "22:00"),
        ("Desserts",         "Sweet endings",                      "🍰", 4, "11:00", "22:00"),
        ("Drinks",           "Non-alcoholic beverages",            "☕", 5, None,    None),
        ("Cocktails & Wine", "Crafted cocktails and fine wines",   "🍷", 6, "12:00", "23:00"),
    ]
    cat_ids = {}
    for name, desc, icon, order, avail_from, avail_to in cats:
        cid = str(uuid.uuid4())
        cat_ids[name] = cid
        c.execute("INSERT INTO categories (id, name, description, icon, display_order, available_from, available_to) VALUES (?,?,?,?,?,?,?)",
                  (cid, name, desc, icon, order, avail_from, avail_to))

    # ── Menu Items ────────────────────────────────────────────────────────────
    # (name, description, price, cat_key, photo_url, dietary_tags, allergens, prep_time_minutes, display_order)
    items = [
        # Breakfast
        ("Treat Yourself",                    "",                                                                                          50.0,  "Breakfast",        "https://images.unsplash.com/photo-1464349095431-e9a21285b5f3?w=400&h=300&fit=crop", '[]',                              "",       15,  1),
        ("Smashed Avo & Beetroot Hummus",     "Smashed avocado, beetroot hummus, feta & microgreens on toasted artisan bread",            145.0, "Breakfast",        "https://images.unsplash.com/photo-1541519227354-08fa5d50c820?w=400&h=300&fit=crop", '["vegetarian"]',                 "Gluten, Dairy", 15, 2),
        ("Flapjacks with Fresh Fruits & Maple Syrup", "200g sirloin steak with roasted garlic butter, seasonal vegetables and choice of sauce", 70.0, "Breakfast",   "https://images.unsplash.com/photo-1567620905732-2d1ec7ab7445?w=400&h=300&fit=crop", '["vegetarian"]',                 "Gluten, Eggs, Dairy", 15, 3),
        ("Sunny Bowl",                        "Creamy yoghurt topped with crunchy granola, seasonal fresh fruit and a drizzle of honey",  100.0, "Breakfast",        "https://images.unsplash.com/photo-1577234286642-fc512a5f8f11?w=400&h=300&fit=crop", '["vegetarian","gluten_free"]',   "Dairy, Nuts", 5, 4),
        ("Eglish Breakfast",                  "Two eggs cooked to your liking, crispy bacon, beef sausage, grilled tomato, mushrooms & toast", 145.0, "Breakfast",   "https://images.unsplash.com/photo-1533089860892-a7c6f0a88666?w=400&h=300&fit=crop", '[]',                              "Gluten, Eggs, Dairy", 20, 5),
        ("Egg on Toast",                      "Eggs cooked to your liking on toasted artisan bread, finished with fresh herbs",           72.0,  "Breakfast",        "https://images.unsplash.com/photo-1608039829572-78524f79c4c7?w=400&h=300&fit=crop", '["vegetarian"]',                 "Gluten, Eggs", 10, 6),
        ("Extra Bread",                       "Brown Toast",                                                                              17.0,  "Breakfast",        "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=400&h=300&fit=crop", '["vegan"]',                       "Gluten", 5, 7),
        ("Extra Bacon",                       "2 slices of crispy Bacon",                                                                 50.0,  "Breakfast",        "https://images.unsplash.com/photo-1528607929212-2636ec44253e?w=400&h=300&fit=crop", '[]',                              "", 5, 8),
        ("Extra Baked Beans",                 "small side dish bowl with baked beans",                                                    25.0,  "Breakfast",        "https://images.unsplash.com/photo-1551462147-ff29053bfc14?w=400&h=300&fit=crop", '["vegan","gluten_free"]',         "", 5, 9),
        ("Beef Saussage",                     "Extra Beef Saussage",                                                                      50.0,  "Breakfast",        "https://images.unsplash.com/photo-1585325701954-8e5dcf17eef7?w=400&h=300&fit=crop", '[]',                              "", 5, 10),
        ("Extra Mushrooms",                   "small side bowl with fried mushrooms",                                                     25.0,  "Breakfast",        "https://images.unsplash.com/photo-1504545102780-26774c1bb073?w=400&h=300&fit=crop", '["vegan","gluten_free"]',         "", 5, 11),
        ("Extra Honey",                       "",                                                                                          17.0,  "Breakfast",        "https://images.unsplash.com/photo-1587049352846-4a222e784d38?w=400&h=300&fit=crop", '["vegan","gluten_free"]',         "", 2, 12),
        ("Extra Butter",                      "",                                                                                          17.0,  "Breakfast",        "https://images.unsplash.com/photo-1589985270826-4b7bb135bc9d?w=400&h=300&fit=crop", '["vegetarian","gluten_free"]',   "Dairy", 2, 13),
        ("Extra Jam",                         "Apricot",                                                                                  17.0,  "Breakfast",        "https://images.unsplash.com/photo-1597528662465-55ece5734101?w=400&h=300&fit=crop", '["vegan","gluten_free"]',         "", 2, 14),

        # Drinks
        ("Single Espresso",                   "",                                                                                          30.0,  "Drinks",           "https://images.unsplash.com/photo-1510591509098-f4fdc6d0ff04?w=400&h=300&fit=crop", '["vegan","gluten_free"]',         "", 3, 1),
        ("Double Espresso",                   "",                                                                                          31.0,  "Drinks",           "https://images.unsplash.com/photo-1510591509098-f4fdc6d0ff04?w=400&h=300&fit=crop", '["vegan","gluten_free"]',         "", 3, 2),
        ("Espresso Macchiato",                "",                                                                                          35.0,  "Drinks",           "https://images.unsplash.com/photo-1485808191679-5f86510bd9d4?w=400&h=300&fit=crop", '["vegetarian","gluten_free"]',   "Dairy", 5, 3),
        ("Americano",                         "",                                                                                          31.0,  "Drinks",           "https://images.unsplash.com/photo-1534778101976-62847782c213?w=400&h=300&fit=crop", '["vegan","gluten_free"]',         "", 5, 4),
        ("Cappuccino",                        "Oat Milk available on request.",                                                           42.0,  "Drinks",           "https://images.unsplash.com/photo-1572442388796-11668a67e53d?w=400&h=300&fit=crop", '["vegetarian","gluten_free"]',   "Dairy", 5, 5),
        ("Decaf Cappuccino",                  "Oat milk available on request",                                                            42.0,  "Drinks",           "https://images.unsplash.com/photo-1572442388796-11668a67e53d?w=400&h=300&fit=crop", '["vegetarian","gluten_free"]',   "Dairy", 5, 6),
        ("Flat White",                        "",                                                                                          42.0,  "Drinks",           "https://images.unsplash.com/photo-1577968897966-3d4325b36b61?w=400&h=300&fit=crop", '["vegetarian","gluten_free"]',   "Dairy", 5, 7),
        ("Caffe Latte",                       "",                                                                                          45.0,  "Drinks",           "https://images.unsplash.com/photo-1561882468-9110e03e0f78?w=400&h=300&fit=crop", '["vegetarian","gluten_free"]',   "Dairy", 5, 8),
        ("Tea",                               "Rooibos, Camomile, Green & Ceylon",                                                        33.0,  "Drinks",           "https://images.unsplash.com/photo-1544787219-7f47ccb76574?w=400&h=300&fit=crop", '["vegan","gluten_free"]',         "", 5, 9),
        ("Hot Chocolate",                     "",                                                                                          47.0,  "Drinks",           "https://images.unsplash.com/photo-1542990253-0d0f5be5f0ed?w=400&h=300&fit=crop", '["vegetarian","gluten_free"]',   "Dairy", 5, 10),
        ("Extra Oat Milk",                    "a Glass, or substitute for cow Milk",                                                      26.0,  "Drinks",           "https://images.unsplash.com/photo-1550583724-b2692b85b150?w=400&h=300&fit=crop", '["vegan","gluten_free"]',         "", 2, 11),
        ("Fresh Squeezed Orange Juice",       "",                                                                                          42.0,  "Drinks",           "https://images.unsplash.com/photo-1621506289937-a8e4df240d0b?w=400&h=300&fit=crop", '["vegan","gluten_free"]',         "", 5, 12),
        ("Orange Juice",                      "",                                                                                          30.0,  "Drinks",           "https://images.unsplash.com/photo-1621506289937-a8e4df240d0b?w=400&h=300&fit=crop", '["vegan","gluten_free"]',         "", 2, 13),
        ("Cranberry Juice",                   "",                                                                                          30.0,  "Drinks",           "https://images.unsplash.com/photo-1513558161293-cdaf765ed2fd?w=400&h=300&fit=crop", '["vegan","gluten_free"]',         "", 2, 14),

        # Cocktails & Wine
        ("Mimosa",                            "",                                                                                         100.0,  "Cocktails & Wine", "https://images.unsplash.com/photo-1560512823-829485b8bf24?w=400&h=300&fit=crop", '["gluten_free"]',                 "Sulphites", 5, 1),
    ]

    for name, desc, price, cat_key, photo, tags, allergens, prep, order in items:
        c.execute("""INSERT INTO menu_items
            (id, category_id, name, description, price, photo_url, dietary_tags, allergens, prep_time_minutes, is_available, display_order)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), cat_ids[cat_key], name, desc, price, photo, tags, allergens, prep, 1, order))

    # ── Admin Users ───────────────────────────────────────────────────────────
    admin_users = [
        (str(uuid.uuid4()), "Hotel Manager", "admin@hotel.com", hash_password("RoomS@TGH2026!"), "admin"),
        (str(uuid.uuid4()), "Kitchen Staff", "kitchen@hotel.com", hash_password("kitchen123"), "kitchen"),
        (str(uuid.uuid4()), "Bar Staff", "bar@hotel.com", hash_password("bar123"), "bar"),
    ]
    for uid, name, email, pw, role in admin_users:
        c.execute("INSERT INTO admin_users (id, name, email, password_hash, role) VALUES (?,?,?,?,?)",
                  (uid, name, email, pw, role))

    # ── Operating Hours ───────────────────────────────────────────────────────
    for day in range(7):  # 0=Mon, 6=Sun
        c.execute("INSERT INTO operating_hours (id, day_of_week, open_time, close_time, is_open) VALUES (?,?,?,?,?)",
                  (str(uuid.uuid4()), day, "07:00", "23:00", 1))

    conn.commit()
    print("✓ Database seeded successfully")
    print("  Admin login: admin@hotel.com / admin123")
