import requests
import time
import datetime
import schedule
import logging

# 🔑 Chiavi integrate (da sostituire con ENV su Render/GitHub se necessario)
ODDS_API_KEY = "INSERISCI_API_KEY"
TELEGRAM_TOKEN = "INSERISCI_TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = "INSERISCI_CHAT_ID"

# Logging
logging.basicConfig(level=logging.INFO)

# Orari invio
START_HOUR = 8
END_HOUR = 23
INTERVAL_MINUTES = 120   # ogni 2 ore

# Cache per evitare pronostici doppi
sent_predictions = set()

def get_odds(sport_key, markets="h2h,totals,spreads"):
    """Recupera quote aggiornate solo se necessario"""
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "eu",
            "markets": markets,
            "oddsFormat": "decimal",
            "dateFormat": "iso"
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error(f"Errore API {sport_key}: {e}")
        return []

def analyze_and_filter(matches, sport_name):
    """Analizza partite e filtra quelle con prob ≥75%"""
    results = []
    now = datetime.datetime.utcnow()

    for match in matches:
        if "commence_time" not in match:
            continue

        start_time = datetime.datetime.fromisoformat(
            match["commence_time"].replace("Z", "+00:00")
        )
        if start_time <= now + datetime.timedelta(hours=1):
            continue  # partita troppo vicina o già iniziata

        if "bookmakers" not in match or not match["bookmakers"]:
            continue

        bookmaker = match["bookmakers"][0]
        markets = bookmaker.get("markets", [])
        if not markets:
            continue

        for market in markets:
            outcomes = market.get("outcomes", [])
            if len(outcomes) < 2:
                continue

            # esempio su vincitore (h2h)
            if market["key"] == "h2h":
                player1, player2 = outcomes[0], outcomes[1]
                odds1, odds2 = float(player1["price"]), float(player2["price"])
                winner = player1["name"] if odds1 < odds2 else player2["name"]
                best_odds = min(odds1, odds2)
                prob = round(1 / best_odds, 2)

                if prob >= 0.75:
                    results.append({
                        "sport": sport_name,
                        "match": f"{player1['name']} vs {player2['name']}",
                        "start_time": start_time,
                        "prediction": f"Vincente: {winner}",
                        "odds": best_odds,
                        "probability": prob
                    })

    return results

def send_to_telegram(prediction):
    """Invia pronostico su Telegram se non già inviato"""
    unique_id = f"{prediction['sport']}_{prediction['match']}_{prediction['prediction']}"
    if unique_id in sent_predictions:
        logging.info(f"⏩ Pronostico già inviato, salto: {unique_id}")
        return

    sent_predictions.add(unique_id)

    message = (
        f"📊 Pronostico {prediction['sport']}\n"
        f"⚔️ {prediction['match']}\n"
        f"📅 {prediction['start_time'].strftime('%d/%m/%Y - %H:%M')}\n"
        f"🔮 {prediction['prediction']}\n"
        f"💰 Quota stimata: {prediction['odds']}\n"
        f"📈 Probabilità stimata: {prediction['probability']*100:.1f}%"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
        logging.info(f"✅ Inviato su Telegram: {unique_id}")
    except Exception as e:
        logging.error(f"Errore Telegram: {e}")

def job():
    """Ciclo principale: legge dai CSV → se trova candidati chiama API"""
    logging.info("🔍 Controllo nuove partite...")

    # 🔹 Qui va l'integrazione con i tuoi CSV caricati
    # Simulazione di un candidato trovato → fa chiamata API
    sports_to_check = {
        "soccer_italy_serie_a": "Calcio",
        "basketball_nba": "Basket",
        "americanfootball_nfl": "Football"
    }

    for sport_key, sport_name in sports_to_check.items():
        matches = get_odds(sport_key)
        candidates = analyze_and_filter(matches, sport_name)

        if not candidates:
            logging.info(f"Nessun pronostico valido per {sport_name}")
        else:
            for prediction in candidates:
                send_to_telegram(prediction)

def schedule_jobs():
    for hour in range(START_HOUR, END_HOUR + 1):
        for minute in range(0, 60, INTERVAL_MINUTES):
            schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(job)

if __name__ == "__main__":
    schedule_jobs()
    logging.info("🤖 Bot avviato. In attesa di invio pronostici...")
    while True:
        schedule.run_pending()
        time.sleep(30)

