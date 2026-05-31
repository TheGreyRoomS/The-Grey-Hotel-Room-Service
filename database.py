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
    rooms = [
        ("1", "Garden View"),
        ("2", "Mountain View"),
        ("3", "Pool Suite"),
        ("4", "Standard"),
        ("5", "Deluxe Room"),
        ("6", "Standard"),
        ("7", "Balcony Room"),
        ("8", "Balcony Room"),
        ("9", "Corner Suite"),
        ("10", "Standard"),
        ("11", "Standard"),
        ("12", "Honeymoon Suite"),
        ("13", "Penthouse"),
    ]
    for num, name in rooms:
        c.execute("INSERT INTO rooms (id, room_number, name, qr_token) VALUES (?,?,?,?)",
                  (str(uuid.uuid4()), num, name, generate_token()))

    # ── Categories ────────────────────────────────────────────────────────────
    cats = [
        ("Breakfast",    "Start your morning right",           "🌅", 1, "07:00", "11:30"),
        ("Light Meals",  "Sandwiches, salads & snacks",        "🥗", 2, None,    None),
        ("Mains",        "Hearty dishes served all day",       "🍽️", 3, "11:00", "22:00"),
        ("Desserts",     "Sweet endings",                      "🍰", 4, "11:00", "22:00"),
        ("Drinks",       "Non-alcoholic beverages",            "☕", 5, None,    None),
        ("Cocktails & Wine", "Crafted cocktails and fine wines","🍷", 6, "12:00", "23:00"),
    ]
    cat_ids = {}
    for name, desc, icon, order, avail_from, avail_to in cats:
        cid = str(uuid.uuid4())
        cat_ids[name] = cid
        c.execute("INSERT INTO categories (id, name, description, icon, display_order, available_from, available_to) VALUES (?,?,?,?,?,?,?)",
                  (cid, name, desc, icon, order, avail_from, avail_to))

    # ── Menu Items ────────────────────────────────────────────────────────────
    # photo_url uses Unsplash source (will load in browser)
    items = [
        # Breakfast
        ("Full English Breakfast", "Two eggs any style, streaky bacon, grilled tomato, sautéed mushrooms, baked beans and toast", 185.0, "breakfast", cat_ids["Breakfast"], "https://images.unsplash.com/photo-1533089860892-a7c6f0a88666?w=400&h=300&fit=crop", '["gluten_free_option"]', "Gluten, Eggs, Dairy", 20, 1),
        ("Eggs Benedict", "Poached eggs on toasted English muffin with hollandaise sauce and grilled ham", 165.0, "breakfast", cat_ids["Breakfast"], "https://images.unsplash.com/photo-1608039829572-78524f79c4c7?w=400&h=300&fit=crop", '[]', "Eggs, Gluten, Dairy", 18, 2),
        ("Avocado Toast", "Sourdough toast with smashed avocado, poached egg, chilli flakes and microgreens", 145.0, "breakfast", cat_ids["Breakfast"], "https://images.unsplash.com/photo-1541519227354-08fa5d50c820?w=400&h=300&fit=crop", '["vegetarian"]', "Gluten, Eggs", 15, 3),
        ("Granola & Yoghurt Bowl", "House granola with Greek yoghurt, seasonal berries and honey", 95.0, "breakfast", cat_ids["Breakfast"], "https://images.unsplash.com/photo-1577234286642-fc512a5f8f11?w=400&h=300&fit=crop", '["vegetarian","gluten_free"]', "Dairy, Nuts", 5, 4),
        ("Continental Basket", "Assorted pastries, fresh fruit, juice and coffee or tea", 125.0, "breakfast", cat_ids["Breakfast"], "https://images.unsplash.com/photo-1555507036-ab1f4038808a?w=400&h=300&fit=crop", '["vegetarian"]', "Gluten, Dairy, Eggs", 10, 5),

        # Light Meals
        ("Club Sandwich", "Triple-decker with chicken, bacon, egg, lettuce, tomato and mayo on toasted white bread. Served with fries.", 165.0, "light", cat_ids["Light Meals"], "https://images.unsplash.com/photo-1553909489-cd47e0907980?w=400&h=300&fit=crop", '[]', "Gluten, Eggs, Dairy", 20, 1),
        ("Caesar Salad", "Cos lettuce, parmesan shavings, garlic croutons and house Caesar dressing. Add grilled chicken +R35.", 135.0, "light", cat_ids["Light Meals"], "https://images.unsplash.com/photo-1512852939750-1305098529bf?w=400&h=300&fit=crop", '["vegetarian"]', "Gluten, Dairy, Eggs, Fish", 15, 2),
        ("Cheese Board", "Selection of three artisan cheeses with fig preserve, grapes, walnuts and crackers", 195.0, "light", cat_ids["Light Meals"], "https://images.unsplash.com/photo-1452195100486-9cc805987862?w=400&h=300&fit=crop", '["vegetarian"]', "Dairy, Gluten, Nuts", 10, 3),
        ("Margherita Pizza", "Thin-base pizza with tomato sauce, fresh mozzarella and basil", 175.0, "light", cat_ids["Light Meals"], "https://images.unsplash.com/photo-1574071318508-1cdbab80d002?w=400&h=300&fit=crop", '["vegetarian"]', "Gluten, Dairy", 25, 4),

        # Mains
        ("Grilled Sirloin Steak", "200g sirloin steak with roasted garlic butter, seasonal vegetables and choice of sauce", 325.0, "mains", cat_ids["Mains"], "https://images.unsplash.com/photo-1546833999-b9f581a1996d?w=400&h=300&fit=crop", '["gluten_free"]', "Dairy", 30, 1),
        ("Kingklip Fillet", "Pan-seared kingklip with lemon butter sauce, wilted spinach and herb crushed potatoes", 295.0, "mains", cat_ids["Mains"], "https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=400&h=300&fit=crop", '["gluten_free"]', "Fish, Dairy", 25, 2),
        ("Pasta Primavera", "Penne with seasonal vegetables in a light tomato and basil sauce, topped with parmesan", 175.0, "mains", cat_ids["Mains"], "https://images.unsplash.com/photo-1563379091339-03246963d2f2?w=400&h=300&fit=crop", '["vegetarian"]', "Gluten, Dairy", 20, 3),
        ("Chicken Schnitzel", "Crumbed free-range chicken breast with mushroom cream sauce, chips and coleslaw", 225.0, "mains", cat_ids["Mains"], "https://images.unsplash.com/photo-1585325701954-8e5dcf17eef7?w=400&h=300&fit=crop", '[]', "Gluten, Dairy, Eggs", 25, 4),
        ("Vegetable Curry", "Slow-cooked mixed vegetable curry in a rich spiced coconut cream, served with basmati rice", 165.0, "mains", cat_ids["Mains"], "https://images.unsplash.com/photo-1565557623262-b51c2513a641?w=400&h=300&fit=crop", '["vegetarian","vegan","gluten_free"]', "None", 25, 5),

        # Desserts
        ("Chocolate Fondant", "Warm dark chocolate fondant with vanilla bean ice cream", 95.0, "dessert", cat_ids["Desserts"], "https://images.unsplash.com/photo-1606313564200-e75d5e30476c?w=400&h=300&fit=crop", '["vegetarian"]', "Gluten, Dairy, Eggs", 20, 1),
        ("Crème Brûlée", "Classic French vanilla crème brûlée with caramelised sugar crust", 85.0, "dessert", cat_ids["Desserts"], "https://images.unsplash.com/photo-1470124182917-cc6e71b22ecc?w=400&h=300&fit=crop", '["vegetarian","gluten_free"]', "Dairy, Eggs", 15, 2),
        ("Seasonal Fruit Platter", "Fresh seasonal fruit with honey and mint yoghurt dip", 75.0, "dessert", cat_ids["Desserts"], "https://images.unsplash.com/photo-1568702846914-96b305d2aaeb?w=400&h=300&fit=crop", '["vegetarian","vegan","gluten_free"]', "None", 5, 3),

        # Drinks
        ("Fresh Orange Juice", "Freshly squeezed orange juice (300ml)", 45.0, "drink", cat_ids["Drinks"], "https://images.unsplash.com/photo-1621506289937-a8e4df240d0b?w=400&h=300&fit=crop", '["vegan","gluten_free"]', "None", 5, 1),
        ("Pot of Coffee", "French press coffee for one with milk and sugar (250ml)", 55.0, "drink", cat_ids["Drinks"], "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=400&h=300&fit=crop", '["vegetarian","gluten_free"]', "Dairy", 8, 2),
        ("Herbal Tea Selection", "Choice of chamomile, rooibos, peppermint or green tea", 45.0, "drink", cat_ids["Drinks"], "https://images.unsplash.com/photo-1544787219-7f47ccb76574?w=400&h=300&fit=crop", '["vegan","gluten_free"]', "None", 5, 3),
        ("Still / Sparkling Water", "Bottled mineral water (500ml)", 35.0, "drink", cat_ids["Drinks"], "https://images.unsplash.com/photo-1548839140-29a749e1cf4d?w=400&h=300&fit=crop", '["vegan","gluten_free"]', "None", 2, 4),
        ("Selection of Cold Drinks", "Coke, Coke Zero, Sprite, Fanta or Lemon Twist (330ml can)", 35.0, "drink", cat_ids["Drinks"], "https://images.unsplash.com/photo-1581636625402-29b2a704ef13?w=400&h=300&fit=crop", '["vegan","gluten_free"]', "None", 2, 5),
        ("Mocktail", "Ask our bar team for today's featured alcohol-free mocktail", 75.0, "drink", cat_ids["Drinks"], "https://images.unsplash.com/photo-1513558161293-cdaf765ed2fd?w=400&h=300&fit=crop", '["vegan","gluten_free"]', "None", 10, 6),

        # Cocktails & Wine
        ("Gin & Tonic", "Premium local gin with tonic water, fresh lime and botanicals", 95.0, "cocktail", cat_ids["Cocktails & Wine"], "https://images.unsplash.com/photo-1514362545857-3bc16c4c7d1b?w=400&h=300&fit=crop", '["gluten_free"]', "None", 5, 1),
        ("Aperol Spritz", "Aperol, Prosecco, splash of soda and orange slice", 110.0, "cocktail", cat_ids["Cocktails & Wine"], "https://images.unsplash.com/photo-1560512823-829485b8bf24?w=400&h=300&fit=crop", '["gluten_free"]', "Sulphites", 5, 2),
        ("Glass of House Wine", "Ask about today's featured red or white (200ml)", 75.0, "cocktail", cat_ids["Cocktails & Wine"], "https://images.unsplash.com/photo-1510812431401-41d2bd2722f3?w=400&h=300&fit=crop", '["vegan","gluten_free"]', "Sulphites", 5, 3),
        ("Craft Beer", "Local craft beer selection — ask about today's options (340ml)", 65.0, "cocktail", cat_ids["Cocktails & Wine"], "https://images.unsplash.com/photo-1608270586620-248524c67de9?w=400&h=300&fit=crop", '[]', "Gluten", 3, 4),
        ("Whisky on the Rocks", "Premium South African or Scotch whisky over ice (30ml)", 125.0, "cocktail", cat_ids["Cocktails & Wine"], "https://images.unsplash.com/photo-1569529465841-dfecdab7503b?w=400&h=300&fit=crop", '["gluten_free"]', "None", 3, 5),
    ]

    for name, desc, price, slug, cat_id, photo, tags, allergens, prep, order in items:
        c.execute("""INSERT INTO menu_items
            (id, category_id, name, description, price, photo_url, dietary_tags, allergens, prep_time_minutes, is_available, display_order)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), cat_id, name, desc, price, photo, tags, allergens, prep, 1, order))

    # ── Admin Users ───────────────────────────────────────────────────────────
    admin_users = [
        (str(uuid.uuid4()), "Hotel Manager", "admin@hotel.com", hash_password("admin123"), "admin"),
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
