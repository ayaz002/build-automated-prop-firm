"""
Gmail OAuth + email parser for payout and spending data.
Searches for emails from Lucid Trading and Take Profit Trader.
"""

import os, base64, re
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CLIENT_CONFIG = {
    "web": {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["https://build-automated-prop-firm-production.up.railway.app/oauth/callback"],
    }
}

REDIRECT_URI = "https://build-automated-prop-firm-production.up.railway.app/oauth/callback"

# Keywords to identify payout vs spending emails
PAYOUT_KEYWORDS  = ["payout", "withdrawal", "payment sent", "funds sent", "profit share"]
SPENDING_KEYWORDS = ["subscription", "fee", "purchase", "charge", "invoice", "reset", "order confirmation"]

FIRM_SENDERS = [
    "lucidtrading", "lucid trading", "lucid-trading",
    "takeprofittrader", "take profit trader", "tpt"
]


def get_auth_url(state: str) -> str:
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, state=state)
    flow.redirect_uri = REDIRECT_URI
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return auth_url


def exchange_code(code: str) -> dict:
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "token":         creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri":     creds.token_uri,
        "client_id":     creds.client_id,
        "client_secret": creds.client_secret,
        "scopes":        list(creds.scopes),
    }


def parse_amount(text: str) -> float:
    match = re.search(r"\$\s*([\d,]+\.?\d*)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return 0.0


def classify_email(subject: str, body: str) -> str:
    combined = (subject + " " + body).lower()
    for kw in PAYOUT_KEYWORDS:
        if kw in combined:
            return "payout"
    for kw in SPENDING_KEYWORDS:
        if kw in combined:
            return "spending"
    return "unknown"


def get_email_body(msg: dict) -> str:
    payload = msg.get("payload", {})
    parts = payload.get("parts", [])
    body = ""
    if parts:
        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                break
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    return body


def fetch_gmail_data(creds_dict: dict) -> dict:
    creds = Credentials(**{k: v for k, v in creds_dict.items() if k != "scopes"})
    service = build("gmail", "v1", credentials=creds)

    payouts  = []
    spending = []

    # Search for emails from prop firms
    query = "from:(lucidtrading OR takeprofittrader OR lucid OR tpt)"
    results = service.users().messages().list(userId="me", q=query, maxResults=100).execute()
    messages = results.get("messages", [])

    for m in messages:
        msg = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "")
        date    = headers.get("Date", "")
        sender  = headers.get("From", "").lower()

        # Only process emails from known firms
        if not any(firm in sender for firm in FIRM_SENDERS):
            continue

        body   = get_email_body(msg)
        amount = parse_amount(subject + " " + body)
        kind   = classify_email(subject, body)

        # Determine firm name
        firm = "Lucid Trading" if any(x in sender for x in ["lucid"]) else "Take Profit Trader"

        entry = {
            "id":      m["id"],
            "date":    date,
            "subject": subject,
            "amount":  amount,
            "firm":    firm,
            "status":  kind,
        }

        if kind == "payout":
            payouts.append(entry)
        elif kind == "spending":
            spending.append(entry)

    return {
        "payouts":        payouts,
        "spending":       spending,
        "total_payout":   round(sum(p["amount"] for p in payouts),  2),
        "total_spending": round(sum(s["amount"] for s in spending), 2),
    }
