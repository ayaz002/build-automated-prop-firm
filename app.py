from flask import Flask, jsonify, request, send_from_directory, redirect
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import json, os, hashlib, secrets
from datetime import datetime
from gmail_parser import get_auth_url, exchange_code, fetch_gmail_data

app = Flask(__name__)
CORS(app, origins="*")

DATA_FILE = "data.json"
USERS  = {}
TOKENS = {}  # token -> username

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def seed_admin():
    admin_pw = os.environ.get("ADMIN_PASSWORD", "admin123")
    USERS["admin"] = {
        "password": hash_pw(admin_pw),
        "role": "admin",
        "gmail_creds": None,
        "firms": {}
    }
    print("✅ Admin seeded")

def get_current_user():
    token = request.headers.get("X-Token", "")
    return TOKENS.get(token)

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE) as f:
        return json.load(f)

def save_data(obj):
    with open(DATA_FILE, "w") as f:
        json.dump(obj, f, indent=2)

def run_daily_scrape():
    all_data = load_data()
    for username, info in USERS.items():
        creds = info.get("gmail_creds")
        if not creds:
            continue
        try:
            result = fetch_gmail_data(creds)
            all_data[username] = {
                "last_updated": datetime.utcnow().isoformat(),
                "firms": {
                    "lucid": {
                        "firm": "Lucid Trading",
                        "payouts":        [p for p in result["payouts"]  if p["firm"] == "Lucid Trading"],
                        "spending":       [s for s in result["spending"] if s["firm"] == "Lucid Trading"],
                        "total_payout":   round(sum(p["amount"] for p in result["payouts"]  if p["firm"] == "Lucid Trading"), 2),
                        "total_spending": round(sum(s["amount"] for s in result["spending"] if s["firm"] == "Lucid Trading"), 2),
                    },
                    "tpt": {
                        "firm": "Take Profit Trader",
                        "payouts":        [p for p in result["payouts"]  if p["firm"] == "Take Profit Trader"],
                        "spending":       [s for s in result["spending"] if s["firm"] == "Take Profit Trader"],
                        "total_payout":   round(sum(p["amount"] for p in result["payouts"]  if p["firm"] == "Take Profit Trader"), 2),
                        "total_spending": round(sum(s["amount"] for s in result["spending"] if s["firm"] == "Take Profit Trader"), 2),
                    },
                }
            }
        except Exception as e:
            print(f"Scrape error for {username}: {e}")
    save_data(all_data)
    print(f"✅ Daily sync complete at {datetime.utcnow().isoformat()}")

# ── FRONTEND ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

# ── AUTH ──────────────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    body  = request.json or {}
    uname = body.get("username", "")
    user  = USERS.get(uname)
    if user and user["password"] == hash_pw(body.get("password", "")):
        token = secrets.token_hex(32)
        TOKENS[token] = uname
        has_gmail = bool(user.get("gmail_creds"))
        return jsonify({"ok": True, "role": user["role"], "token": token, "has_gmail": has_gmail})
    return jsonify({"ok": False, "error": "Invalid credentials"}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    token = request.headers.get("X-Token", "")
    TOKENS.pop(token, None)
    return jsonify({"ok": True})

@app.route("/api/me")
def me():
    uname = get_current_user()
    if not uname:
        return jsonify({"ok": False}), 401
    return jsonify({"ok": True, "username": uname, "role": USERS[uname]["role"],
                    "has_gmail": bool(USERS[uname].get("gmail_creds"))})

# ── DATA ──────────────────────────────────────────────────────────────────────
@app.route("/api/data")
def get_data():
    uname = get_current_user()
    if not uname:
        return jsonify({"error": "Unauthorized"}), 401
    all_data = load_data()
    role = USERS[uname]["role"]
    if role == "admin":
        return jsonify(all_data)
    return jsonify({uname: all_data.get(uname, {})})

# ── GMAIL OAUTH ───────────────────────────────────────────────────────────────
@app.route("/api/gmail/connect")
def gmail_connect():
    uname = get_current_user()
    if not uname:
        return jsonify({"error": "Unauthorized"}), 401
    state = f"{uname}:{secrets.token_hex(8)}"
    url = get_auth_url(state)
    return jsonify({"url": url})

@app.route("/oauth/callback")
def oauth_callback():
    code  = request.args.get("code")
    state = request.args.get("state", "")
    uname = state.split(":")[0] if ":" in state else ""
    if not code or uname not in USERS:
        return "Error: Invalid OAuth callback", 400
    try:
        creds = exchange_code(code)
        USERS[uname]["gmail_creds"] = creds
        return redirect("/?gmail=connected")
    except Exception as e:
        return f"Error: {e}", 500

@app.route("/api/gmail/sync", methods=["POST"])
def gmail_sync():
    uname = get_current_user()
    if not uname:
        return jsonify({"error": "Unauthorized"}), 401
    creds = USERS[uname].get("gmail_creds")
    if not creds:
        return jsonify({"error": "Gmail not connected"}), 400
    try:
        result = fetch_gmail_data(creds)
        all_data = load_data()
        all_data[uname] = {
            "last_updated": datetime.utcnow().isoformat(),
            "firms": {
                "lucid": {
                    "firm": "Lucid Trading",
                    "payouts":        [p for p in result["payouts"]  if p["firm"] == "Lucid Trading"],
                    "spending":       [s for s in result["spending"] if s["firm"] == "Lucid Trading"],
                    "total_payout":   round(sum(p["amount"] for p in result["payouts"]  if p["firm"] == "Lucid Trading"), 2),
                    "total_spending": round(sum(s["amount"] for s in result["spending"] if s["firm"] == "Lucid Trading"), 2),
                },
                "tpt": {
                    "firm": "Take Profit Trader",
                    "payouts":        [p for p in result["payouts"]  if p["firm"] == "Take Profit Trader"],
                    "spending":       [s for s in result["spending"] if s["firm"] == "Take Profit Trader"],
                    "total_payout":   round(sum(p["amount"] for p in result["payouts"]  if p["firm"] == "Take Profit Trader"), 2),
                    "total_spending": round(sum(s["amount"] for s in result["spending"] if s["firm"] == "Take Profit Trader"), 2),
                },
            }
        }
        save_data(all_data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── ADMIN ─────────────────────────────────────────────────────────────────────
@app.route("/api/admin/users")
def list_users():
    uname = get_current_user()
    if not uname or USERS[uname]["role"] != "admin":
        return jsonify({"error": "Forbidden"}), 403
    safe = {u: {"role": v["role"], "has_gmail": bool(v.get("gmail_creds"))} for u, v in USERS.items()}
    return jsonify(safe)

@app.route("/api/admin/users", methods=["POST"])
def create_user():
    uname = get_current_user()
    if not uname or USERS[uname]["role"] != "admin":
        return jsonify({"error": "Forbidden"}), 403
    body  = request.json or {}
    new_u = body.get("username", "").strip()
    if not new_u or new_u in USERS:
        return jsonify({"error": "Username missing or already exists"}), 400
    USERS[new_u] = {
        "password":    hash_pw(body.get("password", "changeme")),
        "role":        "user",
        "gmail_creds": None,
        "firms":       {}
    }
    return jsonify({"ok": True})

@app.route("/api/admin/users/<username>", methods=["DELETE"])
def delete_user(username):
    uname = get_current_user()
    if not uname or USERS[uname]["role"] != "admin":
        return jsonify({"error": "Forbidden"}), 403
    USERS.pop(username, None)
    return jsonify({"ok": True})

@app.route("/api/admin/scrape", methods=["POST"])
def manual_scrape():
    uname = get_current_user()
    if not uname or USERS[uname]["role"] != "admin":
        return jsonify({"error": "Forbidden"}), 403
    run_daily_scrape()
    return jsonify({"ok": True})

seed_admin()
scheduler = BackgroundScheduler()
scheduler.add_job(run_daily_scrape, "cron", hour=6, minute=0)
scheduler.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
