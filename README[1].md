# PropTrack — Prop Firm Dashboard

Multi-user dashboard to track payouts and spending from Lucid Trading and Take Profit Trader. Automatically scrapes data daily.

## Stack
- **Backend**: Python + Flask + APScheduler
- **Scraping**: requests + BeautifulSoup
- **Frontend**: Vanilla HTML/CSS/JS (no framework needed)
- **Hosting**: Render.com (free tier)

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run locally
```bash
cd propdash
python app.py
```

### 3. Open dashboard
Open `frontend/index.html` in browser, or serve it via any static host.

Default admin login:
- Username: `admin`
- Password: `admin123`

**Change this immediately after first login.**

## How it works
1. Admin adds users with their Lucid Trading + TPT credentials
2. Scraper runs daily at 6:00 AM UTC automatically
3. Admin can trigger manual sync anytime
4. Each user logs in and sees ONLY their own data
5. Admin sees all users' data

## Deploy to Render (free)
1. Push code to GitHub
2. Create new Web Service on render.com
3. Build command: `pip install -r requirements.txt`
4. Start command: `python app.py`
5. Done — free hosting, auto-deploys on push

## Files
- `app.py` — Flask backend + scheduler
- `scraper.py` — Lucid Trading + TPT scrapers
- `frontend/index.html` — Full dashboard UI
- `users.json` — User accounts (auto-created)
- `data.json` — Scraped data (auto-created)
