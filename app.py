from flask import Flask, jsonify, request, session, send_from_directory
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import json, os, hashlib, secrets
from datetime import datetime
from scraper import scrape_lucid, scrape_tpt

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
CORS(app, supports_credentials=True, origins="*")

DATA_FILE  = "data.json"

# ── In-memory user store (persists as long as server runs) ───────────────────
USERS = {}

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def seed_admin():
    global USERS
    admin_pw = os.environ.get("ADMIN_PASSWORD", "admin123")
    USERS["admin"] = {
        "password": hash_pw(admin_pw),
        "role": "admin",
        "firms": {
            "lucid": {"username": "", "password": ""},
            "tpt":   {"username": "", "password": ""},
        }
    }
    print(f"✅ Admin seeded")

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
        firms = info.get("firms", {})
        results = {}
        if firms.get("lucid", {}).get("username"):
            results["lucid"] = scrape_lucid(firms["lucid"]["username"], firms["lucid"]["password"])
        if firms.get("tpt", {}).get("username"):
            results["tpt"] = scrape_tpt(firms["tpt"]["username"], firms["tpt"]["password"])
        all_data[username] = {"last_updated": datetime.utcnow().isoformat(), "firms": results}
    save_data(all_data)
    print(f"✅ Daily scrape complete at {datetime.utcnow().isoformat()}")

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/api/login", methods=["POST"])
def login():
    body = request.json or {}
    user = USERS.get(body.get("username", ""))
    if user and user["password"] == hash_pw(body.get("password", "")):
        session["user"] = body["username"]
        session["role"] = user["role"]
        return jsonify({"ok": True, "role": user["role"]})
    return jsonify({"ok": False, "error": "Invalid credentials"}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/me")
def me():
    if "user" not in session:
        return jsonify({"ok": False}), 401
    return jsonify({"ok": True, "username": session["user"], "role": session["role"]})

@app.route("/api/data")
def get_data():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    all_data = load_data()
    username = session["user"]
    role     = session["role"]
    if role == "admin":
        return jsonify(all_data)
    return jsonify({username: all_data.get(username, {})})

@app.route("/api/admin/users")
def list_users():
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    safe = {u: {"role": v["role"], "firms": list(v.get("firms", {}).keys())} for u, v in USERS.items()}
    return jsonify(safe)

@app.route("/api/admin/users", methods=["POST"])
def create_user():
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    body  = request.json or {}
    uname = body.get("username", "").strip()
    if not uname or uname in USERS:
        return jsonify({"error": "Username missing or already exists"}), 400
    USERS[uname] = {
        "password": hash_pw(body.get("password", "changeme")),
        "role": "user",
        "firms": {
            "lucid": {"username": body.get("lucid_user", ""), "password": body.get("lucid_pass", "")},
            "tpt":   {"username": body.get("tpt_user",   ""), "password": body.get("tpt_pass",   "")},
        }
    }
    return jsonify({"ok": True})

@app.route("/api/admin/users/<username>", methods=["DELETE"])
def delete_user(username):
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    USERS.pop(username, None)
    return jsonify({"ok": True})

@app.route("/api/admin/scrape", methods=["POST"])
def manual_scrape():
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    run_daily_scrape()
    return jsonify({"ok": True, "message": "Scrape complete"})

seed_admin()
scheduler = BackgroundScheduler()
scheduler.add_job(run_daily_scrape, "cron", hour=6, minute=0)
scheduler.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
