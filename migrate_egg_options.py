"""
migrate_egg_options.py
Adds customisation_options column and sets egg dish options.
Run once: python3 migrate_egg_options.py
"""
import sqlite3, json, os

DB_PATH = os.path.join(os.path.dirname(__file__), "hotel.db")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Add column if it doesn't exist
try:
    c.execute("ALTER TABLE menu_items ADD COLUMN customisation_options TEXT DEFAULT '[]'")
    print("✓ Column added")
except sqlite3.OperationalError:
    print("✓ Column already exists")

# Option groups for egg dishes
egg_options = json.dumps([
    {
        "label": "Egg Style",
        "required": True,
        "options": ["Fried", "Scrambled", "Poached", "Boiled"]
    },
    {
        "label": "Doneness",
        "required": True,
        "options": ["Soft", "Medium", "Hard"]
    }
])

# Apply to all egg-related dishes
egg_dishes = [
    "Full English Breakfast",
    "Eggs Benedict",
    "Avocado Toast",
]

for name in egg_dishes:
    result = c.execute(
        "UPDATE menu_items SET customisation_options=? WHERE name=?",
        (egg_options, name)
    )
    if result.rowcount:
        print(f"✓ Options set on: {name}")
    else:
        print(f"  Not found: {name}")

conn.commit()
conn.close()
print("\nDone — restart the server to apply changes.")
