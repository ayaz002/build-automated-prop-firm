"""
Scraper module for Lucid Trading and Take Profit Trader.
Uses requests + BeautifulSoup with session-based login.
Falls back to placeholder data if scraping fails (for demo/dev).
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def scrape_lucid(username: str, password: str) -> dict:
    """Scrape payout and spending data from Lucid Trading dashboard."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    try:
        # Step 1: Get login page for CSRF token
        login_page = session.get("https://lucidtrading.com/my-account/", timeout=15)
        soup = BeautifulSoup(login_page.text, "html.parser")

        # Step 2: Extract nonce/token if present
        nonce = ""
        nonce_field = soup.find("input", {"name": "woocommerce-login-nonce"})
        if nonce_field:
            nonce = nonce_field.get("value", "")

        # Step 3: Login POST
        payload = {
            "username": username,
            "password": password,
            "woocommerce-login-nonce": nonce,
            "_wp_http_referer": "/my-account/",
            "login": "Log in",
        }
        login_resp = session.post(
            "https://lucidtrading.com/my-account/",
            data=payload,
            timeout=15,
            allow_redirects=True,
        )

        if "my-account" not in login_resp.url and "dashboard" not in login_resp.url:
            log.warning("Lucid login may have failed.")

        # Step 4: Scrape orders/payouts page
        orders_page = session.get("https://lucidtrading.com/my-account/orders/", timeout=15)
        soup = BeautifulSoup(orders_page.text, "html.parser")

        payouts = []
        spending = []

        # Parse WooCommerce order table
        rows = soup.select("table.woocommerce-orders-table tbody tr")
        for row in rows:
            cols = row.select("td")
            if len(cols) >= 4:
                order_num = cols[0].get_text(strip=True)
                date_str  = cols[1].get_text(strip=True)
                status    = cols[2].get_text(strip=True)
                total_str = cols[3].get_text(strip=True)

                # Clean amount
                amount = float(total_str.replace("$", "").replace(",", "").strip() or 0)

                entry = {
                    "id": order_num,
                    "date": date_str,
                    "amount": amount,
                    "status": status,
                }

                # Classify: payouts vs spending (fees/subscriptions)
                if "payout" in status.lower() or "completed" in status.lower():
                    payouts.append(entry)
                else:
                    spending.append(entry)

        return {
            "firm": "Lucid Trading",
            "scraped_at": datetime.utcnow().isoformat(),
            "payouts": payouts,
            "spending": spending,
            "total_payout": round(sum(p["amount"] for p in payouts), 2),
            "total_spending": round(sum(s["amount"] for s in spending), 2),
            "error": None,
        }

    except Exception as e:
        log.error(f"Lucid scrape error: {e}")
        return {
            "firm": "Lucid Trading",
            "scraped_at": datetime.utcnow().isoformat(),
            "payouts": [],
            "spending": [],
            "total_payout": 0,
            "total_spending": 0,
            "error": str(e),
        }


def scrape_tpt(username: str, password: str) -> dict:
    """Scrape payout and spending data from Take Profit Trader dashboard."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    try:
        # Step 1: Get login page
        login_page = session.get("https://takeprofittrader.com/my-account/", timeout=15)
        soup = BeautifulSoup(login_page.text, "html.parser")

        nonce = ""
        nonce_field = soup.find("input", {"name": "woocommerce-login-nonce"})
        if nonce_field:
            nonce = nonce_field.get("value", "")

        # Step 2: Login
        payload = {
            "username": username,
            "password": password,
            "woocommerce-login-nonce": nonce,
            "_wp_http_referer": "/my-account/",
            "login": "Log in",
        }
        session.post(
            "https://takeprofittrader.com/my-account/",
            data=payload,
            timeout=15,
            allow_redirects=True,
        )

        # Step 3: Orders page
        orders_page = session.get(
            "https://takeprofittrader.com/my-account/orders/", timeout=15
        )
        soup = BeautifulSoup(orders_page.text, "html.parser")

        payouts = []
        spending = []

        rows = soup.select("table.woocommerce-orders-table tbody tr")
        for row in rows:
            cols = row.select("td")
            if len(cols) >= 4:
                order_num = cols[0].get_text(strip=True)
                date_str  = cols[1].get_text(strip=True)
                status    = cols[2].get_text(strip=True)
                total_str = cols[3].get_text(strip=True)

                amount = float(total_str.replace("$", "").replace(",", "").strip() or 0)

                entry = {
                    "id": order_num,
                    "date": date_str,
                    "amount": amount,
                    "status": status,
                }

                if "payout" in status.lower() or "completed" in status.lower():
                    payouts.append(entry)
                else:
                    spending.append(entry)

        return {
            "firm": "Take Profit Trader",
            "scraped_at": datetime.utcnow().isoformat(),
            "payouts": payouts,
            "spending": spending,
            "total_payout": round(sum(p["amount"] for p in payouts), 2),
            "total_spending": round(sum(s["amount"] for s in spending), 2),
            "error": None,
        }

    except Exception as e:
        log.error(f"TPT scrape error: {e}")
        return {
            "firm": "Take Profit Trader",
            "scraped_at": datetime.utcnow().isoformat(),
            "payouts": [],
            "spending": [],
            "total_payout": 0,
            "total_spending": 0,
            "error": str(e),
        }
