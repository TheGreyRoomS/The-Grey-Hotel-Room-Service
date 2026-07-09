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
    conn.execute("UPDATE rooms SET name=''")
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
        customisation_options TEXT DEFAULT '[]',
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
        roomraccoon_reservation_number TEXT,
        roomraccoon_charge_status TEXT,
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

    # ── Migrations: add RoomRaccoon columns to existing databases ────────────
    for migration_sql in [
        "ALTER TABLE orders ADD COLUMN roomraccoon_reservation_number TEXT",
        "ALTER TABLE orders ADD COLUMN roomraccoon_charge_status TEXT",
    ]:
        try:
            c.execute(migration_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists — safe to ignore

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
    oat_milk_opt = json.dumps([{"label": "Substitute with Oat Milk", "type": "checkbox", "price_add": 15, "required": False}])

    # (name, description, price, cat_key, photo_url, dietary_tags, allergens, prep_time_minutes, display_order, customisation_options)
    items = [
        # Breakfast
        ("Treat Yourself",                    "",                                                                                          50.0,  "Breakfast",        "/static/uploads/4ecdb58b1cae48d691673183be22b6ac.png", '[]',                              "",       15,  1,  '[]'),
        ("Smashed Avo & Beetroot Hummus",     "Smashed avocado, beetroot hummus, feta & microgreens on toasted artisan bread",            145.0, "Breakfast",        "/static/uploads/7a85bd4f2ceb4847a339cf8ee819625a.png", '["vegetarian"]',                 "Gluten, Dairy", 15, 2,  '[]'),
        ("Flapjacks with Fresh Fruits & Maple Syrup", "Fluffy flapjacks served with fresh seasonal fruits and maple syrup",              70.0,  "Breakfast",        "/static/uploads/36512d422bd84e24804a4a118f3c804b.png", '["vegetarian"]',                 "Gluten, Eggs, Dairy", 15, 3,  '[]'),
        ("Sunny Bowl",                        "Creamy yoghurt topped with crunchy granola, seasonal fresh fruit and a drizzle of honey",  100.0, "Breakfast",        "/static/uploads/26bb0eddd89c42b1b932001409db0a24.png", '["vegetarian","gluten_free"]',   "Dairy, Nuts", 5, 4,  '[]'),
        ("Eglish Breakfast",                  "Two eggs cooked to your liking, crispy bacon, beef sausage, grilled tomato, mushrooms & toast", 145.0, "Breakfast",   "/static/uploads/a91bd673fb0e42e88a001205fdd29a25.png", '[]',                              "Gluten, Eggs, Dairy", 20, 5,  '[]'),
        ("Egg on Toast",                      "Eggs cooked to your liking on toasted artisan bread, finished with fresh herbs",           72.0,  "Breakfast",        "/static/uploads/ab2584e845984960882880377c290e87.png", '["vegetarian"]',                 "Gluten, Eggs", 10, 6,  '[]'),
        ("Extra Bread",                       "Brown Toast",                                                                              17.0,  "Breakfast",        "/static/uploads/c77226867c2d4f7bb2187c2917addb49.png", '["vegan"]',                       "Gluten", 5, 7,  '[]'),
        ("Extra Bacon",                       "2 slices of crispy Bacon",                                                                 50.0,  "Breakfast",        "/static/uploads/f4bf87bcb56d4b439c9f611ef861f43c.png", '[]',                              "", 5, 8,  '[]'),
        ("Extra Baked Beans",                 "small side dish bowl with baked beans",                                                    25.0,  "Breakfast",        "/static/uploads/476e22d841204f19b9b613dc4415c0f4.png", '["vegan","gluten_free"]',         "", 5, 9,  '[]'),
        ("Beef Saussage",                     "Extra Beef Saussage",                                                                      50.0,  "Breakfast",        "/static/uploads/a10d15920dcd45f999c5bc9d86a480a9.png", '[]',                              "", 5, 10, '[]'),
        ("Extra Mushrooms",                   "small side bowl with fried mushrooms",                                                     25.0,  "Breakfast",        "/static/uploads/f8c68cf6ca8749f598840dc31a27947d.png", '["vegan","gluten_free"]',         "", 5, 11, '[]'),
        ("Extra Honey",                       "",                                                                                          17.0,  "Breakfast",        "/static/uploads/ef3ce0b33e234dd4998366132b5fee60.png", '["vegan","gluten_free"]',         "", 2, 12, '[]'),
        ("Extra Butter",                      "",                                                                                          17.0,  "Breakfast",        "/static/uploads/e43bef412d564a08b7b6f9dea9247f61.png", '["vegetarian","gluten_free"]',   "Dairy", 2, 13, '[]'),
        ("Extra Jam",                         "Apricot",                                                                                  17.0,  "Breakfast",        "/static/uploads/898309284dde4471841b6b5dee8156fa.png", '["vegan","gluten_free"]',         "", 2, 14, '[]'),

        # Drinks — coffee & tea get oat milk option
        ("Single Espresso",                   "",                                                                                          30.0,  "Drinks",           "/static/uploads/1122027b5d3647f6a509b28c7cb1dfa2.png", '["vegan","gluten_free"]',         "", 3, 1,  oat_milk_opt),
        ("Double Espresso",                   "",                                                                                          31.0,  "Drinks",           "/static/uploads/492be1c5bea344b4a0af558e760385e6.png", '["vegan","gluten_free"]',         "", 3, 2,  oat_milk_opt),
        ("Espresso Macchiato",                "",                                                                                          35.0,  "Drinks",           "/static/uploads/c629809064114c0d9e0b11b4887ccd7c.png", '["vegetarian","gluten_free"]',   "Dairy", 5, 3,  oat_milk_opt),
        ("Americano",                         "",                                                                                          31.0,  "Drinks",           "/static/uploads/5ec583ad1ea44316a9c556253c6bc6b1.png", '["vegan","gluten_free"]',         "", 5, 4,  oat_milk_opt),
        ("Cappuccino",                        "Oat Milk available on request.",                                                           42.0,  "Drinks",           "/static/uploads/3c109f26f3c24b8bafd491db84e368b6.png", '["vegetarian","gluten_free"]',   "Dairy", 5, 5,  oat_milk_opt),
        ("Decaf Cappuccino",                  "Oat milk available on request",                                                            42.0,  "Drinks",           "/static/uploads/61b9dfabfb8542cb8fac9910034e285a.png", '["vegetarian","gluten_free"]',   "Dairy", 5, 6,  oat_milk_opt),
        ("Flat White",                        "",                                                                                          42.0,  "Drinks",           "/static/uploads/44fab51226e345d3bd7551a60307daf1.png", '["vegetarian","gluten_free"]',   "Dairy", 5, 7,  oat_milk_opt),
        ("Caffe Latte",                       "",                                                                                          45.0,  "Drinks",           "/static/uploads/66f5b4df04c441d981e94b02c746fa4b.png", '["vegetarian","gluten_free"]',   "Dairy", 5, 8,  oat_milk_opt),
        ("Tea",                               "Rooibos, Camomile, Green & Ceylon",                                                        33.0,  "Drinks",           "/static/uploads/aff503819d2449b7a225563ed697cfb5.png", '["vegan","gluten_free"]',         "", 5, 9,  oat_milk_opt),
        ("Hot Chocolate",                     "",                                                                                          47.0,  "Drinks",           "/static/uploads/763d4b5aea4f4409ab8496b6915fdddd.png", '["vegetarian","gluten_free"]',   "Dairy", 5, 10, oat_milk_opt),
        ("Extra Oat Milk",                    "a Glass, or substitute for cow Milk",                                                      26.0,  "Drinks",           "/static/uploads/b1e8b26f089a4687a390f822f71dbcf2.png", '["vegan","gluten_free"]',         "", 2, 11, '[]'),
        ("Fresh Squeezed Orange Juice",       "",                                                                                          42.0,  "Drinks",           "/static/uploads/d45e2eede32f45789bc9c61a4ba9337e.png", '["vegan","gluten_free"]',         "", 5, 12, '[]'),
        ("Orange Juice",                      "",                                                                                          30.0,  "Drinks",           "/static/uploads/faec579aed004171b2e40600654f80cb.png", '["vegan","gluten_free"]',         "", 2, 13, '[]'),
        ("Cranberry Juice",                   "",                                                                                          30.0,  "Drinks",           "/static/uploads/2b23797a39af470aa7d4afba399f04ff.png", '["vegan","gluten_free"]',         "", 2, 14, '[]'),

        # Cocktails & Wine
        ("Mimosa",                            "",                                                                                         100.0,  "Cocktails & Wine", "/static/uploads/798ef1733db141738bc161f89efde85f.png", '["gluten_free"]',                 "Sulphites", 5, 1, '[]'),
    ]

    for name, desc, price, cat_key, photo, tags, allergens, prep, order, custom_opts in items:
        c.execute("""INSERT INTO menu_items
            (id, category_id, name, description, price, photo_url, dietary_tags, allergens, prep_time_minutes, is_available, display_order, customisation_options)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), cat_ids[cat_key], name, desc, price, photo, tags, allergens, prep, 1, order, custom_opts))

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
    print("  Admin login: admin@hotel.com / RoomS@TGH2026!")
