"""
server.py — Tornado web server for the Boutique Hotel Room Service App
Run with: python server.py
Access:
  Guest app:   http://localhost:8080/room-service?room=1&token=<token>
  Admin panel: http://localhost:8080/admin
"""

import json
import uuid
import mimetypes
import os
import hashlib
import sqlite3
from datetime import datetime, timedelta

import tornado.ioloop
import tornado.web
import tornado.websocket
import jwt

from database import init_db, ensure_admin_password, get_db, hash_password, generate_token, DB_PATH

PORT = int(os.environ.get("PORT", 8080))
JWT_SECRET = os.environ.get("JWT_SECRET", "boutique-hotel-secret-change-in-production")
JWT_EXPIRY_HOURS = 12

# Track WebSocket connections for real-time order push
_ws_clients = set()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_jwt(user_id, role):
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_jwt(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None


def db_row_to_dict(row):
    return dict(row) if row else None


def db_rows_to_list(rows):
    return [dict(r) for r in rows]


def broadcast_order_update(order_data):
    """Push new/updated order to all connected admin WebSocket clients."""
    global _ws_clients
    msg = json.dumps({"type": "order_update", "order": order_data})
    dead = set()
    for client in _ws_clients:
        try:
            client.write_message(msg)
        except Exception:
            dead.add(client)
    _ws_clients -= dead


def json_response(handler, data, status=200):
    handler.set_status(status)
    handler.set_header("Content-Type", "application/json")
    handler.write(json.dumps(data))


def is_kitchen_open():
    now = datetime.now()
    day = now.weekday()  # 0=Mon
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM operating_hours WHERE day_of_week=?", (day,)
    ).fetchone()
    conn.close()
    if not row or not row["is_open"]:
        return False, "Kitchen is currently closed"
    open_t = datetime.strptime(row["open_time"], "%H:%M").time()
    close_t = datetime.strptime(row["close_time"], "%H:%M").time()
    current = now.time().replace(second=0, microsecond=0)
    if open_t <= current <= close_t:
        return True, ""
    return False, row["closed_message"] or "Kitchen is currently closed"


def get_order_with_items(order_id, conn=None):
    """Fetch a full order dict including its items."""
    close_after = conn is None
    if conn is None:
        conn = get_db()
    order = db_row_to_dict(
        conn.execute("SELECT o.*, r.room_number FROM orders o JOIN rooms r ON o.room_id=r.id WHERE o.id=?", (order_id,)).fetchone()
    )
    if order:
        items = db_rows_to_list(
            conn.execute("SELECT * FROM order_items WHERE order_id=?", (order_id,)).fetchall()
        )
        for item in items:
            try:
                item["dietary_tags"] = []
            except Exception:
                pass
        order["items"] = items
    if close_after:
        conn.close()
    return order


# ─── Base Handler ─────────────────────────────────────────────────────────────

class BaseHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Cache-Control", "no-cache")

    def get_current_user(self):
        auth = self.request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return decode_jwt(auth[7:])
        return None

    def require_auth(self, roles=None):
        user = self.get_current_user()
        if not user:
            json_response(self, {"error": "Unauthorised"}, 401)
            return None
        if roles and user.get("role") not in roles:
            json_response(self, {"error": "Forbidden"}, 403)
            return None
        return user

    def json_body(self):
        try:
            return json.loads(self.request.body)
        except Exception:
            return {}


# ─── Static & App Serving ─────────────────────────────────────────────────────

class GuestAppHandler(BaseHandler):
    """Serves the guest-facing app, validating room token."""
    def get(self):
        room_num = self.get_argument("room", "")
        token = self.get_argument("token", "")

        if not room_num or not token:
            self.render_error("Missing room or token. Please scan the QR code in your room.")
            return

        conn = get_db()
        room = db_row_to_dict(
            conn.execute("SELECT * FROM rooms WHERE room_number=? AND qr_token=? AND is_active=1", (room_num, token)).fetchone()
        )
        conn.close()

        if not room:
            self.render_error("Invalid or expired QR code. Please contact reception.")
            return

        # Serve the guest HTML
        public_dir = os.path.join(os.path.dirname(__file__), "public")
        with open(os.path.join(public_dir, "guest.html"), "r") as f:
            html = f.read()
        self.write(html)

    def render_error(self, message):
        self.write(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Room Service</title>
<style>body{{font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;
min-height:100vh;margin:0;background:#f5f5f0;}}
.card{{background:white;padding:2rem;border-radius:16px;max-width:360px;text-align:center;
box-shadow:0 4px 20px rgba(0,0,0,.1);}}
h2{{color:#1a1a2e;}}p{{color:#666;}}
a{{color:#B8973A;font-weight:bold;}}</style></head>
<body><div class="card"><h2>⚠️ QR Code Error</h2>
<p>{message}</p>
<p>📞 Call Reception for assistance</p></div></body></html>""")


class AdminAppHandler(BaseHandler):
    """Serves the admin SPA."""
    def get(self):
        public_dir = os.path.join(os.path.dirname(__file__), "public")
        with open(os.path.join(public_dir, "admin.html"), "r") as f:
            self.write(f.read())


# ─── API: Public (Guest) ──────────────────────────────────────────────────────

class ApiMenuHandler(BaseHandler):
    def get(self):
        conn = get_db()
        categories = db_rows_to_list(
            conn.execute("SELECT * FROM categories WHERE is_active=1 ORDER BY display_order").fetchall()
        )
        items = db_rows_to_list(
            conn.execute("SELECT * FROM menu_items WHERE is_available=1 ORDER BY display_order").fetchall()
        )
        conn.close()
        for item in items:
            try:
                item["dietary_tags"] = json.loads(item["dietary_tags"] or "[]")
            except Exception:
                item["dietary_tags"] = []
            try:
                item["customisation_options"] = json.loads(item.get("customisation_options") or "[]")
            except Exception:
                item["customisation_options"] = []
        json_response(self, {"categories": categories, "items": items})


class ApiMenuItemHandler(BaseHandler):
    def get(self, item_id):
        conn = get_db()
        item = db_row_to_dict(conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone())
        conn.close()
        if not item:
            json_response(self, {"error": "Not found"}, 404)
            return
        try:
            item["dietary_tags"] = json.loads(item["dietary_tags"] or "[]")
        except Exception:
            item["dietary_tags"] = []
        json_response(self, item)


class ApiKitchenStatusHandler(BaseHandler):
    def get(self):
        is_open, message = is_kitchen_open()
        json_response(self, {"is_open": is_open, "message": message})


class ApiOrdersHandler(BaseHandler):
    def post(self):
        """Create a new order from a guest."""
        body = self.json_body()
        room_num = body.get("room_number", "")
        token = body.get("token", "")

        # Validate room
        conn = get_db()
        room = db_row_to_dict(
            conn.execute("SELECT * FROM rooms WHERE room_number=? AND qr_token=? AND is_active=1", (room_num, token)).fetchone()
        )
        if not room:
            conn.close()
            json_response(self, {"error": "Invalid room or token"}, 400)
            return

        cart_items = body.get("items", [])
        if not cart_items:
            conn.close()
            json_response(self, {"error": "Cart is empty"}, 400)
            return

        payment_method = body.get("payment_method", "")
        if payment_method not in ("card", "charge_to_room"):
            conn.close()
            json_response(self, {"error": "Invalid payment method"}, 400)
            return

        # Validate charge-to-room
        if payment_method == "charge_to_room" and not room["charge_to_room_enabled"]:
            conn.close()
            json_response(self, {"error": "Charge to room is not available for this room"}, 400)
            return

        # Build order
        order_id = str(uuid.uuid4())
        order_ref = f"RS-{datetime.now().strftime('%y%m%d')}-{order_id[:4].upper()}"
        subtotal = 0.0
        order_item_rows = []

        for ci in cart_items:
            item = db_row_to_dict(
                conn.execute("SELECT * FROM menu_items WHERE id=? AND is_available=1", (ci["id"],)).fetchone()
            )
            if not item:
                continue
            qty = max(1, int(ci.get("quantity", 1)))
            line_total = round(item["price"] * qty, 2)
            subtotal += line_total
            order_item_rows.append((
                str(uuid.uuid4()), order_id, item["id"],
                item["name"], item["price"], qty, line_total,
                ci.get("notes", "")
            ))

        subtotal = round(subtotal, 2)

        # Check charge-to-room limit
        if payment_method == "charge_to_room":
            limit = room.get("charge_to_room_limit", 1500.0)
            if subtotal > limit:
                conn.close()
                json_response(self, {"error": f"Order total exceeds charge-to-room limit of R{limit:.0f}"}, 400)
                return

        payment_status = "pending" if payment_method == "card" else "pending_settlement"

        conn.execute("""INSERT INTO orders
            (id, order_reference, room_id, guest_name, status, payment_method,
             payment_status, subtotal, total_amount, delivery_type, scheduled_for,
             order_notes, ip_address)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (order_id, order_ref, room["id"], body.get("guest_name", ""),
             "received", payment_method, payment_status,
             subtotal, subtotal,
             body.get("delivery_type", "asap"), body.get("scheduled_for"),
             body.get("order_notes", ""),
             self.request.remote_ip))

        for row in order_item_rows:
            conn.execute("""INSERT INTO order_items
                (id, order_id, menu_item_id, item_name, item_price, quantity, line_total, notes)
                VALUES (?,?,?,?,?,?,?,?)""", row)

        # Status history
        conn.execute("""INSERT INTO order_status_history (id, order_id, from_status, to_status)
            VALUES (?,?,?,?)""", (str(uuid.uuid4()), order_id, None, "received"))

        # Payment record
        conn.execute("""INSERT INTO payments (id, order_id, gateway, amount, status)
            VALUES (?,?,?,?,?)""",
            (str(uuid.uuid4()), order_id,
             "manual" if payment_method == "charge_to_room" else "yoco",
             subtotal,
             "pending_settlement" if payment_method == "charge_to_room" else "pending"))

        conn.commit()

        # Calc max prep time for ETA
        max_prep = 30
        if order_item_rows:
            ids = [r[2] for r in order_item_rows if r[2]]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                row = conn.execute(
                    f"SELECT MAX(prep_time_minutes) FROM menu_items WHERE id IN ({placeholders})", ids
                ).fetchone()
                if row and row[0]:
                    max_prep = row[0]

        full_order = get_order_with_items(order_id, conn)
        conn.close()

        # Broadcast to admin WebSocket clients
        broadcast_order_update(full_order)

        json_response(self, {
            "order_id": order_id,
            "order_reference": order_ref,
            "status": "received",
            "estimated_minutes": max_prep + 10,
            "payment_method": payment_method,
            "total_amount": subtotal,
        }, 201)


class ApiOrderStatusHandler(BaseHandler):
    def get(self, order_id):
        conn = get_db()
        order = db_row_to_dict(
            conn.execute("SELECT id, order_reference, status, payment_status, total_amount, created_at FROM orders WHERE id=?", (order_id,)).fetchone()
        )
        conn.close()
        if not order:
            json_response(self, {"error": "Order not found"}, 404)
            return
        json_response(self, order)


class ApiPaymentSimulateHandler(BaseHandler):
    """Simulate card payment (in production, replace with Yoco webhook handler)."""
    def post(self):
        body = self.json_body()
        order_id = body.get("order_id")
        # Simulate success (in production, Yoco sends a webhook here)
        conn = get_db()
        conn.execute("UPDATE orders SET payment_status='paid', status='received', updated_at=? WHERE id=?",
                     (datetime.now().isoformat(), order_id))
        conn.execute("UPDATE payments SET status='succeeded', paid_at=? WHERE order_id=?",
                     (datetime.now().isoformat(), order_id))
        conn.commit()
        full_order = get_order_with_items(order_id, conn)
        conn.close()
        if full_order:
            broadcast_order_update(full_order)
        json_response(self, {"success": True, "message": "Payment confirmed"})


# ─── API: Admin (Protected) ───────────────────────────────────────────────────

class ApiAdminLoginHandler(BaseHandler):
    def post(self):
        body = self.json_body()
        email = body.get("email", "")
        password = body.get("password", "")
        pw_hash = hash_password(password)
        conn = get_db()
        user = db_row_to_dict(
            conn.execute("SELECT * FROM admin_users WHERE email=? AND password_hash=? AND is_active=1", (email, pw_hash)).fetchone()
        )
        if user:
            conn.execute("UPDATE admin_users SET last_login_at=? WHERE id=?", (datetime.now().isoformat(), user["id"]))
            conn.commit()
        conn.close()
        if not user:
            json_response(self, {"error": "Invalid email or password"}, 401)
            return
        token = make_jwt(user["id"], user["role"])
        json_response(self, {"token": token, "name": user["name"], "role": user["role"]})


class ApiAdminOrdersHandler(BaseHandler):
    def get(self):
        user = self.require_auth()
        if not user:
            return
        status_filter = self.get_argument("status", "")
        conn = get_db()
        if status_filter:
            rows = conn.execute(
                "SELECT o.*, r.room_number FROM orders o JOIN rooms r ON o.room_id=r.id WHERE o.status=? ORDER BY o.created_at DESC",
                (status_filter,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT o.*, r.room_number FROM orders o JOIN rooms r ON o.room_id=r.id ORDER BY o.created_at DESC LIMIT 200"
            ).fetchall()
        orders = db_rows_to_list(rows)
        for order in orders:
            items = db_rows_to_list(
                conn.execute("SELECT * FROM order_items WHERE order_id=?", (order["id"],)).fetchall()
            )
            order["items"] = items
        conn.close()
        json_response(self, orders)


class ApiAdminOrderStatusHandler(BaseHandler):
    def put(self, order_id):
        user = self.require_auth()
        if not user:
            return
        body = self.json_body()
        new_status = body.get("status")
        note = body.get("note", "")
        valid = ["received", "accepted", "preparing", "delivered", "cancelled"]
        if new_status not in valid:
            json_response(self, {"error": "Invalid status"}, 400)
            return
        conn = get_db()
        order = db_row_to_dict(conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone())
        if not order:
            conn.close()
            json_response(self, {"error": "Order not found"}, 404)
            return
        old_status = order["status"]
        conn.execute("UPDATE orders SET status=?, updated_at=? WHERE id=?",
                     (new_status, datetime.now().isoformat(), order_id))
        conn.execute("""INSERT INTO order_status_history (id, order_id, from_status, to_status, changed_by, note)
            VALUES (?,?,?,?,?,?)""",
            (str(uuid.uuid4()), order_id, old_status, new_status, user.get("sub"), note))
        conn.commit()
        full_order = get_order_with_items(order_id, conn)
        conn.close()
        broadcast_order_update(full_order)
        json_response(self, {"success": True, "order": full_order})


# ─── Admin Menu API ───────────────────────────────────────────────────────────

class ApiAdminUploadPhotoHandler(BaseHandler):
    """Handle menu item photo uploads — saves to public/uploads/"""
    def post(self):
        user = self.require_auth()
        if not user:
            return
        upload_dir = os.path.join(os.path.dirname(__file__), "public", "uploads")
        os.makedirs(upload_dir, exist_ok=True)

        if not self.request.files:
            json_response(self, {"error": "No file received"}, 400)
            return

        file_info = self.request.files.get("photo", [None])[0]
        if not file_info:
            json_response(self, {"error": "No photo field in upload"}, 400)
            return

        # Validate file type
        content_type = file_info.get("content_type", "")
        if not content_type.startswith("image/"):
            json_response(self, {"error": "Only image files are allowed"}, 400)
            return

        # Generate unique filename keeping original extension
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        ext = ext.replace(".jpe", ".jpg")  # normalise jpeg extension
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(upload_dir, filename)

        with open(filepath, "wb") as f:
            f.write(file_info["body"])

        url = f"/static/uploads/{filename}"
        json_response(self, {"url": url})


class ApiAdminMenuItemsHandler(BaseHandler):
    def get(self):
        user = self.require_auth()
        if not user:
            return
        conn = get_db()
        items = db_rows_to_list(
            conn.execute("SELECT mi.*, c.name as category_name FROM menu_items mi JOIN categories c ON mi.category_id=c.id ORDER BY mi.display_order").fetchall()
        )
        categories = db_rows_to_list(conn.execute("SELECT * FROM categories ORDER BY display_order").fetchall())
        conn.close()
        for item in items:
            try:
                item["dietary_tags"] = json.loads(item["dietary_tags"] or "[]")
            except Exception:
                item["dietary_tags"] = []
        json_response(self, {"items": items, "categories": categories})

    def post(self):
        user = self.require_auth(["admin", "manager"])
        if not user:
            return
        body = self.json_body()
        required = ["name", "category_id", "price"]
        for f in required:
            if not body.get(f):
                json_response(self, {"error": f"Missing field: {f}"}, 400)
                return
        item_id = str(uuid.uuid4())
        tags = json.dumps(body.get("dietary_tags", []))
        conn = get_db()
        conn.execute("""INSERT INTO menu_items
            (id, category_id, name, description, price, photo_url, dietary_tags, allergens, prep_time_minutes, is_available, display_order)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (item_id, body["category_id"], body["name"],
             body.get("description", ""), float(body["price"]),
             body.get("photo_url", ""), tags,
             body.get("allergens", ""),
             int(body.get("prep_time_minutes", 20)),
             1 if body.get("is_available", True) else 0,
             int(body.get("display_order", 99))))
        conn.commit()
        item = db_row_to_dict(conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone())
        conn.close()
        json_response(self, item, 201)


class ApiAdminMenuItemHandler(BaseHandler):
    def put(self, item_id):
        user = self.require_auth(["admin", "manager"])
        if not user:
            return
        body = self.json_body()
        conn = get_db()
        item = db_row_to_dict(conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone())
        if not item:
            conn.close()
            json_response(self, {"error": "Not found"}, 404)
            return
        tags = json.dumps(body.get("dietary_tags", json.loads(item["dietary_tags"] or "[]")))
        conn.execute("""UPDATE menu_items SET
            category_id=?, name=?, description=?, price=?, photo_url=?,
            dietary_tags=?, allergens=?, prep_time_minutes=?, is_available=?,
            display_order=?, updated_at=? WHERE id=?""",
            (body.get("category_id", item["category_id"]),
             body.get("name", item["name"]),
             body.get("description", item["description"]),
             float(body.get("price", item["price"])),
             body.get("photo_url", item["photo_url"]),
             tags,
             body.get("allergens", item["allergens"]),
             int(body.get("prep_time_minutes", item["prep_time_minutes"])),
             1 if body.get("is_available", bool(item["is_available"])) else 0,
             int(body.get("display_order", item["display_order"])),
             datetime.now().isoformat(), item_id))
        conn.commit()
        updated = db_row_to_dict(conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone())
        conn.close()
        json_response(self, updated)

    def delete(self, item_id):
        user = self.require_auth(["admin", "manager"])
        if not user:
            return
        conn = get_db()
        conn.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
        conn.commit()
        conn.close()
        json_response(self, {"success": True})


class ApiAdminToggleAvailabilityHandler(BaseHandler):
    def post(self, item_id):
        user = self.require_auth()
        if not user:
            return
        conn = get_db()
        item = db_row_to_dict(conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone())
        if not item:
            conn.close()
            json_response(self, {"error": "Not found"}, 404)
            return
        new_val = 0 if item["is_available"] else 1
        conn.execute("UPDATE menu_items SET is_available=?, updated_at=? WHERE id=?",
                     (new_val, datetime.now().isoformat(), item_id))
        conn.commit()
        conn.close()
        json_response(self, {"is_available": bool(new_val)})


# ─── Admin Rooms & QR API ─────────────────────────────────────────────────────

class ApiAdminRoomsHandler(BaseHandler):
    def get(self):
        user = self.require_auth()
        if not user:
            return
        conn = get_db()
        rooms = db_rows_to_list(conn.execute("SELECT * FROM rooms ORDER BY CAST(room_number AS INTEGER)").fetchall())
        # Add last order time per room
        for room in rooms:
            last = conn.execute(
                "SELECT created_at FROM orders WHERE room_id=? ORDER BY created_at DESC LIMIT 1", (room["id"],)
            ).fetchone()
            room["last_order_at"] = last["created_at"] if last else None
            # Include QR URL
            base = self.request.protocol + "://" + self.request.host
            room["qr_url"] = f"{base}/room-service?room={room['room_number']}&token={room['qr_token']}"
        conn.close()
        json_response(self, rooms)


class ApiAdminRegenerateTokenHandler(BaseHandler):
    def post(self, room_id):
        user = self.require_auth(["admin", "manager"])
        if not user:
            return
        new_token = generate_token()
        conn = get_db()
        conn.execute("UPDATE rooms SET qr_token=? WHERE id=?", (new_token, room_id))
        conn.commit()
        room = db_row_to_dict(conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone())
        conn.close()
        base = self.request.protocol + "://" + self.request.host
        room["qr_url"] = f"{base}/room-service?room={room['room_number']}&token={room['qr_token']}"
        json_response(self, room)


# ─── Admin Reports API ────────────────────────────────────────────────────────

class ApiAdminReportsHandler(BaseHandler):
    def get(self):
        user = self.require_auth()
        if not user:
            return
        days = int(self.get_argument("days", 30))
        since = (datetime.now() - timedelta(days=days)).isoformat()
        conn = get_db()

        total_revenue = conn.execute(
            "SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE created_at>=? AND status!='cancelled'", (since,)
        ).fetchone()[0]

        total_orders = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE created_at>=? AND status!='cancelled'", (since,)
        ).fetchone()[0]

        avg_order = total_revenue / total_orders if total_orders else 0

        top_items = db_rows_to_list(conn.execute("""
            SELECT oi.item_name, SUM(oi.quantity) as total_qty, SUM(oi.line_total) as total_revenue
            FROM order_items oi
            JOIN orders o ON oi.order_id=o.id
            WHERE o.created_at>=? AND o.status!='cancelled'
            GROUP BY oi.item_name ORDER BY total_qty DESC LIMIT 10
        """, (since,)).fetchall())

        by_payment = db_rows_to_list(conn.execute("""
            SELECT payment_method, COUNT(*) as count, SUM(total_amount) as revenue
            FROM orders WHERE created_at>=? AND status!='cancelled'
            GROUP BY payment_method
        """, (since,)).fetchall())

        by_room = db_rows_to_list(conn.execute("""
            SELECT r.room_number, COUNT(o.id) as order_count, SUM(o.total_amount) as total_spent
            FROM orders o JOIN rooms r ON o.room_id=r.id
            WHERE o.created_at>=? AND o.status!='cancelled'
            GROUP BY r.room_number ORDER BY total_spent DESC
        """, (since,)).fetchall())

        daily = db_rows_to_list(conn.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as orders, SUM(total_amount) as revenue
            FROM orders WHERE created_at>=? AND status!='cancelled'
            GROUP BY DATE(created_at) ORDER BY date
        """, (since,)).fetchall())

        conn.close()
        json_response(self, {
            "total_revenue": round(total_revenue, 2),
            "total_orders": total_orders,
            "avg_order_value": round(avg_order, 2),
            "top_items": top_items,
            "by_payment_method": by_payment,
            "by_room": by_room,
            "daily": daily,
            "days": days,
        })


# ─── Admin Operating Hours API ────────────────────────────────────────────────

class ApiAdminHoursHandler(BaseHandler):
    def get(self):
        user = self.require_auth()
        if not user:
            return
        conn = get_db()
        hours = db_rows_to_list(conn.execute("SELECT * FROM operating_hours ORDER BY day_of_week").fetchall())
        conn.close()
        json_response(self, hours)

    def put(self):
        user = self.require_auth(["admin", "manager"])
        if not user:
            return
        body = self.json_body()  # list of hour objects
        conn = get_db()
        for h in body:
            conn.execute("""UPDATE operating_hours SET open_time=?, close_time=?, is_open=?, closed_message=?
                WHERE day_of_week=?""",
                (h.get("open_time", "07:00"), h.get("close_time", "23:00"),
                 1 if h.get("is_open", True) else 0,
                 h.get("closed_message", "Kitchen is currently closed"),
                 h["day_of_week"]))
        conn.commit()
        conn.close()
        json_response(self, {"success": True})


# ─── WebSocket for Real-Time Orders ──────────────────────────────────────────

class OrderWebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True  # Allow any origin (restrict in production)

    def open(self):
        # Validate JWT from query param
        token = self.get_argument("token", "")
        user = decode_jwt(token)
        if not user:
            self.close(code=4001, reason="Unauthorised")
            return
        _ws_clients.add(self)
        self.write_message(json.dumps({"type": "connected", "message": "Real-time orders active"}))

    def on_close(self):
        _ws_clients.discard(self)

    def on_message(self, message):
        pass  # Client → server messages not needed currently


# ─── App ─────────────────────────────────────────────────────────────────────

def make_app():
    public_dir = os.path.join(os.path.dirname(__file__), "public")
    return tornado.web.Application([
        # Guest
        (r"/room-service", GuestAppHandler),
        (r"/api/menu", ApiMenuHandler),
        (r"/api/menu/items/([^/]+)", ApiMenuItemHandler),
        (r"/api/kitchen-status", ApiKitchenStatusHandler),
        (r"/api/orders", ApiOrdersHandler),
        (r"/api/orders/([^/]+)/status", ApiOrderStatusHandler),
        (r"/api/payments/simulate", ApiPaymentSimulateHandler),

        # Admin
        (r"/admin/?", AdminAppHandler),
        (r"/api/admin/login", ApiAdminLoginHandler),
        (r"/api/admin/orders", ApiAdminOrdersHandler),
        (r"/api/admin/orders/([^/]+)/status", ApiAdminOrderStatusHandler),
        (r"/api/admin/menu-items/upload-photo", ApiAdminUploadPhotoHandler),
        (r"/api/admin/menu-items", ApiAdminMenuItemsHandler),
        (r"/api/admin/menu-items/([^/]+)", ApiAdminMenuItemHandler),
        (r"/api/admin/menu-items/([^/]+)/toggle", ApiAdminToggleAvailabilityHandler),
        (r"/api/admin/rooms", ApiAdminRoomsHandler),
        (r"/api/admin/rooms/([^/]+)/regenerate-token", ApiAdminRegenerateTokenHandler),
        (r"/api/admin/reports", ApiAdminReportsHandler),
        (r"/api/admin/hours", ApiAdminHoursHandler),

        # WebSocket
        (r"/ws/orders", OrderWebSocketHandler),

        # Static files
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": public_dir}),
        (r"/", tornado.web.RedirectHandler, {"url": "/admin"}),
    ], debug=True)


if __name__ == "__main__":
    print("🏨 Boutique Hotel Room Service App")
    print("─" * 40)
    init_db()
    ensure_admin_password()
    app = make_app()
    app.listen(PORT)
    print(f"✓ Server running at http://localhost:{PORT}")
    print(f"  Admin panel:  http://localhost:{PORT}/admin")
    print(f"  Guest app:    http://localhost:{PORT}/room-service?room=1&token=<token>")
    print(f"  (Get room tokens from the admin panel → QR Codes)")
    print("─" * 40)
    print("  Admin logins:")
    print("    admin@hotel.com   / admin123  (full access)")
    print("    kitchen@hotel.com / kitchen123")
    print("    bar@hotel.com     / bar123")
    print("─" * 40)
    tornado.ioloop.IOLoop.current().start()
