import os
import time
import logging
import requests
import pandas as pd
import schedule
from datetime import datetime, timezone

# === CONFIG ===
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "INSERISCI_LA_TUA_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "INSERISCI_IL_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "INSERISCI_IL_CHAT_ID")

# Imposta logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

# === FUNZIONI ===

def send_telegram_message(message: str):
    """Invia un messaggio su Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        r = requests.post(url, json=payload)
        r.raise_for_status()
    except Exception as e:
        logging.error(f"Errore invio Telegram: {e}")


def fetch_odds(sport, markets="h2h,totals,spreads"):
    """Recupera quote dall'API Odds"""
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": markets,
        "oddsFormat": "decimal"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"Odds fetch error {sport}: {e}")
        return []


def analyze_csv_and_odds():
    """Analizza i CSV locali e integra con Odds API"""
    picks = []

    try:
        # === Esempio calcio ===
        for file in os.listdir():
            if file.startswith("calcio") and file.endswith(".csv"):
                df = pd.read_csv(file)
                if "Date" in df.columns:
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                    upcoming = df[df["Date"] > datetime.now(timezone.utc)]
                    if not upcoming.empty:
                        picks.append(f"Calcio: trovato {len(upcoming)} match futuri in {file}")
    except Exception as e:
        logging.error(f"Soccer error: {e}")

    try:
        # === Basket ===
        for file in os.listdir():
            if file.startswith("basket") and file.endswith(".csv"):
                df = pd.read_csv(file)
                if "Date" in df.columns:
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                    upcoming = df[df["Date"] > datetime.now(timezone.utc)]
                    if not upcoming.empty:
                        picks.append(f"Basket: trovato {len(upcoming)} match futuri in {file}")
    except Exception as e:
        logging.error(f"Basket error: {e}")

    try:
        # === Football ===
        for file in os.listdir():
            if file.endswith(".csv") and "football" in file.lower() or "nfl" in file.lower():
                df = pd.read_csv(file)
                if "Date" in df.columns:
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                    upcoming = df[df["Date"] > datetime.now(timezone.utc)]
                    if not upcoming.empty:
                        picks.append(f"Football: trovato {len(upcoming)} match futuri in {file}")
    except Exception as e:
        logging.error(f"Football error: {e}")

    return picks


def generate_picks():
    """Genera pronostici dai CSV e Odds API"""
    picks = analyze_csv_and_odds()

    if picks:
        for p in picks:
            logging.info(f"Pronostico generato → {p}")
            send_telegram_message(f"📊 Pronostico: {p}")
    else:
        logging.info("Nessun pronostico trovato")


# === JOB SCHEDULER ===

def job():
    try:
        generate_picks()
    except Exception as e:
        logging.error(f"Errore job: {e}")


# 🔥 Forza subito un check all'avvio
job()

# Scheduler ogni 2 ore
schedule.every(2).hours.do(job)

logging.info("🤖 Bot avviato, in ascolto...")

while True:
    schedule.run_pending()
    time.sleep(10)

