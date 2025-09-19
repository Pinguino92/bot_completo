import os
import requests
import time
import datetime
import schedule
import logging
import pandas as pd

# 🔑 Lettura dalle Environment Variables (Render → Environment)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

# Logging
logging.basicConfig(level=logging.INFO)

# Endpoint Odds API
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports"

# Intervallo richieste (ogni 2 ore)
CHECK_INTERVAL = 120  # minuti
PROB_THRESHOLD = 0.75  # 75% minimo

# Set pronostici già inviati (per evitare duplicati)
sent_predictions = set()

def send_to_telegram(message: str):
    """Invia messaggi a Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            logging.error(f"Errore Telegram: {r.text}")
    except Exception as e:
        logging.error(f"Errore Telegram: {e}")

def check_csv_matches():
    """Legge i CSV locali e filtra le partite future"""
    all_matches = []
    today = datetime.datetime.now()

    folders = ["downloads/calcio", "downloads/basket", "downloads/football"]
    for folder in folders:
        if not os.path.exists(folder):
            continue

        for f in os.listdir(folder):
            if not f.endswith(".csv"):
                continue
            try:
                df = pd.read_csv(os.path.join(folder, f))
                if "Date" in df.columns:
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                    fut = df[df["Date"] >= today]
                    if not fut.empty:
                        all_matches.extend(fut.to_dict("records"))
            except Exception as e:
                logging.error(f"Errore lettura {f}: {e}")
    return all_matches

def get_odds(sport_key):
    """Scarica quote dalle Odds API SOLO se serve"""
    url = f"{ODDS_API_URL}/{sport_key}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "h2h,totals,spreads",
        "oddsFormat": "decimal",
        "dateFormat": "iso"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"{sport_key} error: {e}")
        return []

def analyze_and_send():
    """Analizza i match e invia pronostici"""
    logging.info("🔍 Controllo nuove partite...")

    upcoming = check_csv_matches()
    logging.info(f"📊 Partite future trovate nei CSV: {len(upcoming)}")

    sports = ["soccer_italy_serie_a", "basketball_nba", "americanfootball_nfl"]

    for sport in sports:
        odds_data = get_odds(sport)
        for match in odds_data:
            if "id" not in match or match["id"] in sent_predictions:
                continue
            if "bookmakers" not in match or not match["bookmakers"]:
                continue

            bookmaker = match["bookmakers"][0]
            markets = bookmaker.get("markets", [])
            if not markets:
                continue

            for market in markets[:4]:  # primi 4 mercati
                outcomes = market.get("outcomes", [])
                if len(outcomes) < 2:
                    continue

                try:
                    odds_values = [float(o["price"]) for o in outcomes]
                    best_outcome = outcomes[odds_values.index(min(odds_values))]
                    probability = 1 / min(odds_values)

                    if probability >= PROB_THRESHOLD:
                        start_time = match.get("commence_time", "N/D")
                        message = (
                            f"📊 <b>Pronostico {sport.upper()}</b>\n"
                            f"🕒 Data: {start_time}\n"
                            f"🎯 Mercato: {market['key']}\n"
                            f"✅ Esito: {best_outcome['name']}\n"
                            f"💰 Quota: {best_outcome['price']}\n"
                            f"📈 Probabilità stimata: {probability*100:.1f}%"
                        )
                        send_to_telegram(message)
                        sent_predictions.add(match["id"])
                except Exception as e:
                    logging.error(f"Errore analisi {sport}: {e}")

def job():
    analyze_and_send()

if __name__ == "__main__":
    # Messaggio test all’avvio
    send_to_telegram("✅ Bot avviato su Render e pronto a cercare pronostici!")

    schedule.every(CHECK_INTERVAL).minutes.do(job)

    logging.info("🤖 Bot avviato. In attesa di invio pronostici...")
    while True:
        schedule.run_pending()
        time.sleep(30)
