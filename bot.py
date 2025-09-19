import requests
import time
import datetime
import schedule
import logging

# 🔑 Chiavi integrate
ODDS_API_KEY = "INSERISCI_API_KEY"
TELEGRAM_TOKEN = "INSERISCI_TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = "INSERISCI_TELEGRAM_CHAT_ID"

# Logging
logging.basicConfig(level=logging.INFO)

# Endpoint Odds API (principali campionati)
SPORTS = {
    "Calcio": "soccer_italy_serie_a",
    "Basket": "basketball_nba",
    "Football": "americanfootball_nfl"
}

# Anti-duplicati
sent_matches = set()

def send_to_telegram(message):
    """Invia messaggio su Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            logging.error(f"Errore Telegram: {r.text}")
    except Exception as e:
        logging.error(f"Errore Telegram: {e}")

def get_matches(sport_key):
    """Recupera partite dalle Odds API"""
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "eu",
            "markets": "h2h,totals",
            "oddsFormat": "decimal",
            "dateFormat": "iso"
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error(f"{sport_key} error: {e}")
        return []

def analyze_match(match):
    """Analizza match e calcola probabilità stimata"""
    if "bookmakers" not in match or not match["bookmakers"]:
        return None

    bookmaker = match["bookmakers"][0]
    markets = bookmaker.get("markets", [])
    if not markets:
        return None

    outcomes = markets[0]["outcomes"]
    if len(outcomes) != 2:
        return None

    team1 = outcomes[0]["name"]
    odds1 = float(outcomes[0]["price"])
    team2 = outcomes[1]["name"]
    odds2 = float(outcomes[1]["price"])

    winner = team1 if odds1 < odds2 else team2
    probability = round(1 / min(odds1, odds2), 2)

    return {
        "id": match.get("id", f"{team1}-{team2}"),
        "teams": f"{team1} vs {team2}",
        "winner": winner,
        "odds": min(odds1, odds2),
        "probability": probability,
        "start_time": match["commence_time"]
    }

def job():
    """Job pianificato: recupero + analisi + invio"""
    logging.info("🔍 Controllo nuove partite...")

    for sport_name, sport_key in SPORTS.items():
        matches = get_matches(sport_key)

        for match in matches:
            analysis = analyze_match(match)
            if not analysis:
                continue

            # DEBUG log per ogni candidato
            logging.info(f"🎯 {sport_name} candidato: {analysis['teams']} | Prob: {analysis['probability']*100:.1f}%")

            if analysis["id"] in sent_matches:
                logging.info(f"⏭️ Scartato {sport_name}: {analysis['teams']} (già inviato)")
                continue

            if analysis["probability"] >= 0.75:  # filtro 75%
                message = (
                    f"📊 Pronostico {sport_name}\n"
                    f"⚡ {analysis['teams']}\n"
                    f"📅 {analysis['start_time']}\n"
                    f"🔮 Vincente probabile: <b>{analysis['winner']}</b>\n"
                    f"💰 Quota stimata: {analysis['odds']}\n"
                    f"📈 Probabilità stimata: {analysis['probability']*100:.1f}%"
                )
                send_to_telegram(message)
                logging.info(f"✅ Inviato {sport_name}: {analysis['teams']}")
                sent_matches.add(analysis["id"])
            else:
                logging.info(f"❌ Scartato {sport_name}: {analysis['teams']} (Prob {analysis['probability']*100:.1f}% < 75%)")

def schedule_jobs():
    """Esegue il job ogni 2 ore"""
    schedule.every(2).hours.do(job)

if __name__ == "__main__":
    # Test iniziale
    send_to_telegram("✅ Bot avviato su Render e pronto a cercare pronostici!")
    schedule_jobs()
    logging.info("🤖 Bot avviato. In attesa di invio pronostici...")

    while True:
        schedule.run_pending()
        time.sleep(30)
