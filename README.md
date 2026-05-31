# 🏨 Boutique Hotel Room Service App

A complete, working web application for QR-code-based room service ordering.

## Quick Start

### 1. Requirements
- Python 3.8 or later (already installed on Mac)
- Internet connection (for your browser to load the QR code library and food photos)

### 2. Install & Run

Double-click `start.sh` in Terminal, or run:

```bash
cd hotel-app
bash start.sh
```

Or manually:
```bash
pip3 install tornado PyJWT
python3 server.py
```

The server starts at **http://localhost:8080**

---

## Access the App

| URL | What it is |
|-----|-----------|
| `http://localhost:8080/admin` | Staff/admin panel |
| `http://localhost:8080/room-service?room=1&token=<token>` | Guest ordering (get token from admin QR Codes page) |

---

## Default Admin Logins

| Email | Password | Role |
|-------|----------|------|
| admin@hotel.com | admin123 | Full access |
| kitchen@hotel.com | kitchen123 | Kitchen staff |
| bar@hotel.com | bar123 | Bar staff |

**Change these passwords immediately before going live.**

---

## What's Included

### Guest App (`/room-service`)
- Mobile-first menu with 6 categories and 28 sample dishes
- Item photos, dietary tags, allergen information
- Add to cart, per-item notes
- ASAP or scheduled delivery
- Charge to room or card payment (simulated)
- Order confirmation with live status tracking

### Admin Panel (`/admin`)
- **Orders**: Live order dashboard with Kanban columns (New → Accepted → Preparing → Delivered)
- **Menu**: Add/edit/delete items, toggle availability, photo support
- **QR Codes**: Generate and download QR codes for all 13 rooms
- **Reports**: Revenue, top items, by-room breakdown, daily trends, CSV export
- **Hours**: Set open/close times for each day of the week

### Real-Time Updates
The admin panel connects via WebSocket — new orders appear instantly without refreshing.

---

## File Structure

```
hotel-app/
├── server.py          Main web server (Tornado)
├── database.py        Database schema + seed data
├── hotel.db           SQLite database (created on first run)
├── requirements.txt   Python dependencies
├── start.sh           Quick-start script
└── public/
    ├── guest.html     Guest ordering app
    └── admin.html     Staff dashboard
```

---

## Deploying to the Internet

To make the app accessible to guests' phones, deploy to a cloud server:

1. **Render.com** (recommended, free tier available):
   - Push files to GitHub
   - Connect repo to Render → New Web Service
   - Build command: `pip install -r requirements.txt`
   - Start command: `python server.py`

2. **Set environment variables** on your host:
   - `JWT_SECRET` = a long random string (keep secret!)
   - `PORT` = 8080 (or as required by host)

3. **Get your domain** (e.g. yourhotel.co.za) and point it to the server.

4. **Print QR codes** from Admin → QR Codes page once the live URL is configured.

---

## Connecting Real Payments (Yoco)

The app currently simulates card payments. To enable real Yoco payments:

1. Sign up at yoco.com and get your API keys
2. Replace the `ApiPaymentSimulateHandler` in `server.py` with a Yoco payment intent call
3. Add a Yoco webhook endpoint to receive payment confirmations
4. See: https://developer.yoco.com/online/payments/

---

## Security Checklist Before Going Live

- [ ] Change all default passwords in the admin panel
- [ ] Set a strong `JWT_SECRET` environment variable
- [ ] Enable HTTPS on your hosting provider
- [ ] Review charge-to-room limits per room
- [ ] Test QR codes on multiple phone types
- [ ] Run through a full order end-to-end
