import requests
import time
import datetime
import schedule
import logging

# 🔑 Configurazioni
ODDS_API_KEY = "INSERISCI_API_KEY"
TELEGRAM_TOKEN = "INSERISCI_TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = "INSERISCI_CHAT_ID"

# Logging
logging.basicConfig(level=logging.INFO)

# Sports monitorati
SPORTS = {
    "soccer_italy_serie_a": "Serie A - Italia",
    "soccer_italy_serie_b": "Serie B - Italia",
    "soccer_spain_la_liga": "La Liga - Spagna",
    "soccer_spain_segunda_division": "Segunda Division - Spagna",
    "soccer_england_epl": "Premier League - Inghilterra",
    "soccer_england_championship": "Championship - Inghilterra",
    "soccer_germany_bundesliga": "Bundesliga - Germania",
    "soccer_germany_bundesliga2": "Bundesliga 2 - Germania",
    "soccer_france_ligue_one": "Ligue 1 - Francia",
    "soccer_france_ligue_two": "Ligue 2 - Francia",
    "americanfootball_nfl": "NFL - Football Americano",
    "americanfootball_ncaaf": "NCAA - Football Americano",
    "basketball_nba": "NBA - Basket",
}

# Parametri
MIN_PROB = 55.0
MIN_QUOTA = 1.40
sent_predictions = set()  # per evitare doppioni


# --- Funzioni ---
def send_to_telegram(message: str):
    """Invia messaggi su Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Errore Telegram: {e}")


def get_odds(sport: str):
    """Recupera quote dalle Odds API"""
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "eu",
            "markets": "h2h,totals",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error(f"{sport} error: {e}")
        return []


def analyze_matches(sport: str, matches: list):
    """Analizza i match e produce pronostici + scartati"""
    pronostici = []
    scartati = []
    now = datetime.datetime.utcnow()

    for match in matches:
        try:
            start_time = datetime.datetime.fromisoformat(
                match["commence_time"].replace("Z", "+00:00")
            )
            if not (now < start_time < now + datetime.timedelta(days=2)):
                continue  # solo entro 48h

            for bookmaker in match.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    for outcome in market.get("outcomes", []):
                        try:
                            quota = float(outcome["price"])
                            probability = round((1 / quota) * 100, 1)

                            match_id = f"{sport}{match['id']}{outcome['name']}"
                            info_base = (
                                f"🏟️ {SPORTS.get(sport, sport)}\n"
                                f"{match['home_team']} vs {match['away_team']}\n"
                                f"📅 {start_time.strftime('%d/%m/%Y %H:%M')}\n"
                                f"🔮 Pronostico: {outcome['name']}\n"
                                f"💰 Quota: {quota}\n"
                                f"📈 Probabilità stimata: {probability}%"
                            )

                            # Accettato
                            if (
                                probability >= MIN_PROB
                                and quota >= MIN_QUOTA
                                and match_id not in sent_predictions
                            ):
                                pronostici.append(info_base)
                                sent_predictions.add(match_id)
                            # Scartato
                            else:
                                motivo = []
                                if probability < MIN_PROB:
                                    motivo.append(f"probabilità {probability}% < {MIN_PROB}%")
                                if quota < MIN_QUOTA:
                                    motivo.append(f"quota {quota} < {MIN_QUOTA}")
                                scartati.append(info_base + f"\n❌ SCARTATO ({', '.join(motivo)})")

                        except Exception:
                            continue
        except Exception:
            continue

    return pronostici, scartati


def job():
    """Job schedulato"""
    logging.info("🔍 Controllo nuove partite...")
    all_pronostici, all_scartati = [], []

    for sport in SPORTS:
        matches = get_odds(sport)
        pronostici, scartati = analyze_matches(sport, matches)
        all_pronostici.extend(pronostici)
        all_scartati.extend(scartati)

    if all_pronostici:
        for p in all_pronostici:
            send_to_telegram("✅ PRONOSTICO TROVATO\n\n" + p)
    if all_scartati:
        for s in all_scartati:
            send_to_telegram(s)

    if not all_pronostici and not all_scartati:
        send_to_telegram("ℹ️ Nessun match disponibile entro 48h.")


# --- Schedule ---
schedule_times = ["08:00", "13:00", "17:00", "22:00"]
for t in schedule_times:
    schedule.every().day.at(t).do(job)


if __name__ == "__main__":
    send_to_telegram("🤖 Bot avviato su Render e pronto a cercare pronostici!")
    job()  # lancio immediato al deploy
    while True:
        schedule.run_pending()
        time.sleep(30)
