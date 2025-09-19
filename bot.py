import requests
import time
import datetime
import schedule
import logging
import os
import pandas as pd

# 🔑 Variabili ambiente (Render → Environment)
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Logging
logging.basicConfig(level=logging.INFO)

# Sports da analizzare
SPORTS = {
    "soccer_italy_serie_a": "⚽ Calcio",
    "basketball_nba": "🏀 Basket NBA",
    "americanfootball_nfl": "🏈 American Football"
}

# Funzione invio Telegram
def send_to_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            logging.error(f"Errore Telegram: {r.text}")
    except Exception as e:
        logging.error(f"Errore Telegram: {e}")

# Recupero odds API
def get_odds(sport: str):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "h2h,totals",
        "oddsFormat": "decimal",
        "dateFormat": "iso"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"{sport} error: {e}")
        return []

# Analisi match
def analyze_matches(sport: str, matches: list):
    pronostici = []
    scartati = 0
    now = datetime.datetime.utcnow()

    for match in matches:
        try:
            start_time = datetime.datetime.fromisoformat(match["commence_time"].replace("Z", "+00:00"))
            if not (now < start_time < now + datetime.timedelta(days=2)):
                continue  # solo partite entro 48 ore

            for bookmaker in match.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    outcomes = market.get("outcomes", [])
                    if len(outcomes) < 2:
                        continue

                    # Trova quota più bassa → maggiore probabilità
                    best_outcome = min(outcomes, key=lambda x: float(x["price"]))
                    quota = float(best_outcome["price"])
                    probability = round((1 / quota) * 100, 1)

                    if probability >= 75:
                        pronostici.append({
                            "sport": sport,
                            "teams": match["home_team"] + " vs " + match["away_team"],
                            "start_time": start_time.strftime("%d/%m/%Y %H:%M"),
                            "prediction": best_outcome["name"],
                            "odds": quota,
                            "probability": probability
                        })
                    else:
                        scartati += 1
        except Exception:
            scartati += 1

    return pronostici, scartati

# Job principale
def job():
    logging.info("🔍 Controllo nuove partite...")

    total_pronostici = 0
    total_scartati = 0

    for sport, label in SPORTS.items():
        matches = get_odds(sport)
        pronostici, scartati = analyze_matches(sport, matches)
        total_pronostici += len(pronostici)
        total_scartati += scartati

        for p in pronostici:
            message = (
                f"📊 Pronostico {label}\n"
                f"📌 Match: {p['teams']}\n"
                f"📅 Data: {p['start_time']}\n"
                f"🔮 Pronostico: {p['prediction']}\n"
                f"💰 Quota stimata: {p['odds']}\n"
                f"📈 Probabilità: {p['probability']}%"
            )
            send_to_telegram(message)

    # Log riepilogo su Render
    logging.info(f"📊 Totale pronostici inviati: {total_pronostici}")
    logging.info(f"❌ Eventi scartati: {total_scartati}")

    if total_pronostici == 0:
        logging.info("⚠️ Nessun pronostico trovato per i prossimi 2 giorni.")

# Pianificazione → ogni 2 ore
schedule.every(2).hours.do(job)

if __name__ == "__main__":
    # Test iniziale Telegram
    send_to_telegram("✅ Bot avviato su Render e pronto a cercare pronostici!")
    logging.info("🤖 Bot avviato. In attesa di invio pronostici...")
    while True:
        schedule.run_pending()
        time.sleep(30)
