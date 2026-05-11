"""
Gmail OAuth + email parser for payout and spending data.
Tuned for Lucid Trading, Take Profit Trader, and My Funded Futures email formats.
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

# ── Firm definitions ──────────────────────────────────────────────────────────
FIRMS = {
    "Lucid Trading": {
        "sender_keywords": ["lucidtrading", "lucid-trading", "lucid trading"],
        "payout_subjects": ["payout", "withdrawal", "payment sent", "profit", "your payment has been sent"],
        "spending_subjects": ["subscription", "fee", "purchase", "invoice", "reset", "order"],
        "amount_patterns": [
            r"payment amount[:\s]+\$?([\d,]+\.?\d*)",
            r"profit share[:\s]+\$?([\d,]+\.?\d*)",
            r"amount requested[:\s]+\$?([\d,]+\.?\d*)",
            r"amount[:\s]+\$?([\d,]+\.?\d*)",
        ]
    },
    "Take Profit Trader": {
        "sender_keywords": ["takeprofittrader", "take profit trader", "tpt"],
        "payout_subjects": ["payout", "withdrawal", "payment sent", "profit"],
        "spending_subjects": ["subscription", "fee", "purchase", "invoice", "reset", "order"],
        "amount_patterns": [
            r"profit share[:\s]+\$?([\d,]+\.?\d*)",
            r"amount requested[:\s]+\$?([\d,]+\.?\d*)",
            r"amount[:\s]+\$?([\d,]+\.?\d*)",
            r"\$\s*([\d,]+\.?\d*)",
        ]
    },
    "My Funded Futures": {
        "sender_keywords": ["myfundedfutures", "my funded futures", "mff"],
        "payout_subjects": ["payout request has been received", "payout", "withdrawal", "profit"],
        "spending_subjects": ["subscription", "fee", "purchase", "invoice", "reset", "order"],
        "amount_patterns": [
            r"profit share[:\s]+\$?([\d,]+\.?\d*)",  # Use profit share as the real payout
            r"amount requested[:\s]+\$?([\d,]+\.?\d*)",
        ]
    },
}


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


def parse_amount(text: str, patterns: list) -> float:
    """Try each pattern in order, return first match."""
    lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lower)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except:
                continue
    return 0.0


def get_email_body(msg: dict) -> str:
    payload = msg.get("payload", {})
    parts   = payload.get("parts", [])
    body    = ""
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


def match_firm(sender: str) -> tuple:
    """Return (firm_name, firm_config) or (None, None)."""
    sender_lower = sender.lower()
    for firm_name, config in FIRMS.items():
        if any(kw in sender_lower for kw in config["sender_keywords"]):
            return firm_name, config
    return None, None


def classify_email(subject: str, firm_config: dict) -> str:
    subject_lower = subject.lower()
    for kw in firm_config["payout_subjects"]:
        if kw in subject_lower:
            return "payout"
    for kw in firm_config["spending_subjects"]:
        if kw in subject_lower:
            return "spending"
    return "unknown"


def fetch_gmail_data(creds_dict: dict) -> dict:
    creds   = Credentials(**{k: v for k, v in creds_dict.items() if k != "scopes"})
    service = build("gmail", "v1", credentials=creds)

    payouts  = []
    spending = []

    # Search all known firm emails
    query = "from:(lucidtrading OR takeprofittrader OR myfundedfutures OR \"lucid trading\" OR \"take profit trader\" OR \"my funded futures\")"
    results  = service.users().messages().list(userId="me", q=query, maxResults=200).execute()
    messages = results.get("messages", [])

    for m in messages:
        msg     = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "")
        date    = headers.get("Date", "")
        sender  = headers.get("From", "")

        firm_name, firm_config = match_firm(sender)
        if not firm_name:
            continue

        body   = get_email_body(msg)
        kind   = classify_email(subject, firm_config)
        amount = parse_amount(subject + " " + body, firm_config["amount_patterns"])

        if kind == "unknown" or amount == 0:
            continue

        entry = {
            "id":      m["id"],
            "date":    date,
            "subject": subject,
            "amount":  amount,
            "firm":    firm_name,
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
