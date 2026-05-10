from flask import Flask, jsonify, request, session, send_from_directory
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import json, os, hashlib, secrets
from datetime import datetime
from scraper import scrape_lucid, scrape_tpt

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app, supports_credentials=True, origins="*")

DATA_FILE  = "data.json"
USERS_FILE = "users.json"

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)

def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def seed_admin():
    users = load_json(USERS_FILE, {})
    if "admin" not in users:
        users["admin"] = {
            "password": hash_pw("admin123"),
            "role": "admin",
            "firms": {
                "lucid": {"username": "", "password": ""},
                "tpt":   {"username": "", "password": ""},
            }
        }
        save_json(USERS_FILE, users)
        print("✅ Admin seeded — login: admin / admin123")

def run_daily_scrape():
    users = load_json(USERS_FILE, {})
    all_data = load_json(DATA_FILE, {})
    for username, info in users.items():
        firms = info.get("firms", {})
        results = {}
        if firms.get("lucid", {}).get("username"):
            results["lucid"] = scrape_lucid(firms["lucid"]["username"], firms["lucid"]["password"])
        if firms.get("tpt", {}).get("username"):
            results["tpt"] = scrape_tpt(firms["tpt"]["username"], firms["tpt"]["password"])
        all_data[username] = {"last_updated": datetime.utcnow().isoformat(), "firms": results}
    save_json(DATA_FILE, all_data)
    print(f"✅ Daily scrape complete at {datetime.utcnow().isoformat()}")

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/api/login", methods=["POST"])
def login():
    body  = request.json or {}
    users = load_json(USERS_FILE, {})
    user  = users.get(body.get("username", ""))
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
    all_data = load_json(DATA_FILE, {})
    username = session["user"]
    role     = session["role"]
    if role == "admin":
        return jsonify(all_data)
    return jsonify({username: all_data.get(username, {})})

@app.route("/api/admin/users")
def list_users():
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    users = load_json(USERS_FILE, {})
    safe  = {u: {"role": v["role"], "firms": list(v.get("firms", {}).keys())} for u, v in users.items()}
    return jsonify(safe)

@app.route("/api/admin/users", methods=["POST"])
def create_user():
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    body  = request.json or {}
    users = load_json(USERS_FILE, {})
    uname = body.get("username", "").strip()
    if not uname or uname in users:
        return jsonify({"error": "Username missing or already exists"}), 400
    users[uname] = {
        "password": hash_pw(body.get("password", "changeme")),
        "role": "user",
        "firms": {
            "lucid": {"username": body.get("lucid_user", ""), "password": body.get("lucid_pass", "")},
            "tpt":   {"username": body.get("tpt_user",   ""), "password": body.get("tpt_pass",   "")},
        }
    }
    save_json(USERS_FILE, users)
    return jsonify({"ok": True})

@app.route("/api/admin/users/<username>", methods=["DELETE"])
def delete_user(username):
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    users = load_json(USERS_FILE, {})
    users.pop(username, None)
    save_json(USERS_FILE, users)
    return jsonify({"ok": True})

@app.route("/api/admin/scrape", methods=["POST"])
def manual_scrape():
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    run_daily_scrape()
    return jsonify({"ok": True, "message": "Scrape complete"})

# Run seed and scheduler at module level so Railway picks it up
seed_admin()
scheduler = BackgroundScheduler()
scheduler.add_job(run_daily_scrape, "cron", hour=6, minute=0)
scheduler.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
