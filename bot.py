import os
import requests
import logging
import schedule
import time
import datetime
import pandas as pd

# === Configurazione ===
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MIN_ODDS = 1.70
MIN_PROB = 0.70
EDGE_MIN = 0.0

# === Logger ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# === Funzioni helper ===
def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Telegram non configurato")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        logging.error(f"Errore Telegram: {e}")

def fetch_odds_for_sport(sport_key, markets="h2h,totals,spreads"):
    if not ODDS_API_KEY:
        logging.error("ODDS_API_KEY non impostata")
        return []
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": markets,
        "oddsFormat": "decimal"
    }
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"Odds fetch error {sport_key}/{markets}: {e}")
        return []

def valid_future_match(start):
    try:
        dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
        return dt > datetime.datetime.now(datetime.timezone.utc)
    except:
        return False

# === Stima probabilità (dummy, usa CSV se disponibile) ===
def estimate_probability(event, market, outcome):
    # Da migliorare con modelli sui CSV
    return 0.75  # baseline 75%

# === Genera pronostici ===
def generate_picks():
    sports = [
        "soccer_italy_serie_a",
        "soccer_epl",
        "basketball_nba",
        "americanfootball_nfl"
    ]

    picks = []
    for sport in sports:
        events = fetch_odds_for_sport(sport)
        for ev in events:
            start = ev.get("commence_time")
            if not valid_future_match(start):
                continue

            for bm in ev.get("bookmakers", []):
                for mk in bm.get("markets", []):
                    for o in mk.get("outcomes", []):
                        try:
                            price = float(o.get("price", 0))
                        except:
                            continue
                        if price < MIN_ODDS:
                            continue

                        implied = 1 / price
                        model_prob = estimate_probability(ev, mk, o)
                        if model_prob < MIN_PROB:
                            continue

                        edge = model_prob - implied
                        if edge > EDGE_MIN:
                            picks.append({
                                "sport": ev.get("sport_title", sport),
                                "home": ev.get("home_team"),
                                "away": ev.get("away_team"),
                                "start": start,
                                "market": mk.get("key"),
                                "selection": o.get("name"),
                                "odds": price,
                                "model_prob": round(model_prob, 3),
                                "implied": round(implied, 3),
                                "edge": round(edge, 3),
                                "bookmaker": bm.get("title", "")
                            })
    return picks

def job():
    picks = generate_picks()
    if not picks:
        logging.info("Nessun pronostico trovato")
        return
    best = sorted(picks, key=lambda x: x["edge"], reverse=True)[:3]
    for p in best:
        msg = (
            f"🏆 {p['sport']}\n"
            f"👥 {p['home']} vs {p['away']}\n"
            f"⏰ {p['start']}\n"
            f"🛒 Mercato: {p['market']}\n"
            f"✅ Selezione: {p['selection']}\n"
            f"💰 Quota: {p['odds']}\n"
            f"📈 Prob modello: {p['model_prob']} | 📉 Implicita: {p['implied']}\n"
            f"🔺 Edge: {p['edge']}\n"
            f"🏷️ Book: {p['bookmaker']}"
        )
        send_telegram_message(msg)

# Scheduler ogni 30 minuti
schedule.every(30).minutes.do(job)

logging.info("🤖 Bot avviato, in ascolto...")

while True:
    schedule.run_pending()
    time.sleep(10)
