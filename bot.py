import os
import time
import logging
import requests
import datetime
import schedule

# 🔑 Variabili ambiente (Render → Environment)
ODDS_API_KEY   = os.getenv("ODDS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Logging
logging.basicConfig(level=logging.INFO)

# Sports da analizzare (puoi aggiungere altri se vuoi)
SPORTS = {
    "soccer_italy_serie_a": "⚽ Serie A - Italia",
    "soccer_italy_serie_b": "⚽ Serie B - Italia",
    "soccer_spain_la_liga": "⚽ La Liga - Spagna",
    "soccer_spain_segunda_division": "⚽ La Liga 2 - Spagna",
    "soccer_england_epl": "⚽ Premier League - Inghilterra",
    "soccer_england_championship": "⚽ Championship - Inghilterra",
    "soccer_germany_bundesliga": "⚽ Bundesliga - Germania",
    "soccer_germany_bundesliga2": "⚽ Bundesliga 2 - Germania",
    "soccer_france_ligue_one": "⚽ Ligue 1 - Francia",
    "soccer_france_ligue_two": "⚽ Ligue 2 - Francia",
    "basketball_nba": "🏀 NBA",
    "americanfootball_nfl": "🏈 NFL",
    "americanfootball_ncaaf": "🏈 NCAA Football"
}

# Parametri filtro
MIN_PROB  = 55.0   # %
MIN_QUOTA = 1.40   # decimale

# Funzione invio Telegram
def send_to_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("⚠️ TELEGRAM_TOKEN o TELEGRAM_CHAT_ID mancanti nelle Environment Variables.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            logging.error(f"Errore Telegram: {r.text}")
    except Exception as e:
        logging.error(f"Errore Telegram: {e}")

# Recupero odds dalle API
def get_odds(sport: str):
    if not ODDS_API_KEY:
        logging.error("⚠️ ODDS_API_KEY mancante nelle Environment Variables.")
        return []
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "h2h,totals",
        "oddsFormat": "decimal",
        "dateFormat": "iso"
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"{sport} error: {e}")
        return []

# Analisi dei match
def analyze_matches(sport: str, matches: list):
    pronostici = []
    scartati   = []
    now = datetime.datetime.now(datetime.timezone.utc)

    for match in matches:
        try:
            ct = match.get("commence_time")
            if not ct:
                continue
            start_time = datetime.datetime.fromisoformat(ct.replace("Z", "+00:00"))
            if not (now < start_time < now + datetime.timedelta(days=2)):
                continue  # solo partite entro 48h

            home = match.get("home_team", "Home")
            away = match.get("away_team", "Away")

            any_market_found = False

            for bookmaker in match.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    outcomes = market.get("outcomes", [])
                    if len(outcomes) < 2:
                        continue

                    any_market_found = True
                    try:
                        best_outcome = min(outcomes, key=lambda x: float(x["price"]))
                        quota = float(best_outcome["price"])
                        if quota <= 1.0:
                            continue
                        probability = round((1.0 / quota) * 100.0, 1)
                    except Exception:
                        continue

                    base_msg = (
                        f"{SPORTS.get(sport, sport)}\n"
                        f"📌 {home} vs {away}\n"
                        f"📅 {start_time.strftime('%d/%m/%Y %H:%M')}\n"
                        f"🔮 Pronostico: {best_outcome.get('name','N/D')}\n"
                        f"💰 Quota: {quota}\n"
                        f"📈 Probabilità stimata: {probability}%"
                    )

                    if probability >= MIN_PROB and quota >= MIN_QUOTA:
                        pronostici.append("✅ PRONOSTICO TROVATO\n\n" + base_msg)
                    else:
                        motivo = []
                        if probability < MIN_PROB:
                            motivo.append(f"prob {probability}% < {MIN_PROB}%")
                        if quota < MIN_QUOTA:
                            motivo.append(f"quota {quota} < {MIN_QUOTA}")
                        scartati.append("❌ SCARTATO\n\n" + base_msg + f"\n🚫 Motivo: {', '.join(motivo)}")

            if not any_market_found:
                scartati.append(
                    "❌ SCARTATO\n\n"
                    f"{SPORTS.get(sport, sport)}\n"
                    f"📌 {home} vs {away}\n"
                    f"📅 {start_time.strftime('%d/%m/%Y %H:%M')}\n"
                    "🚫 Motivo: nessuna quota disponibile"
                )

        except Exception:
            scartati.append(f"❌ SCARTATO\n\n{SPORTS.get(sport, sport)}\n⚠️ Errore parsing match.")
            continue

    return pronostici, scartati

# Job principale
def job():
    logging.info("🔍 Controllo nuove partite...")
    tot_ok, tot_ko = 0, 0

    for sport in SPORTS.keys():
        matches = get_odds(sport)
        accettati, rifiutati = analyze_matches(sport, matches)

        for msg in accettati:
            send_to_telegram(msg)
        for msg in rifiutati:
            send_to_telegram(msg)

        tot_ok += len(accettati)
        tot_ko += len(rifiutati)

    logging.info(f"📊 Totale pronostici inviati: {tot_ok}")
    logging.info(f"❌ Eventi scartati (con motivo): {tot_ko}")
    if tot_ok == 0 and tot_ko == 0:
        send_to_telegram("ℹ️ Nessun match disponibile entro 48h (nessuna quota).")

# --- Schedule fisso ---
schedule_times = ["08:00", "13:00", "17:00", "22:00"]
for t in schedule_times:
    schedule.every().day.at(t).do(job)

if _name_ == "_main_":
    send_to_telegram("✅ Bot avviato su Render e pronto a cercare pronostici!")
    logging.info("🤖 Bot avviato. In attesa di invio pronostici...")
    job()  # lancio immediato al deploy
    while True:
        schedule.run_pending()
        time.sleep(30)
