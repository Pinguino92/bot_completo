import requests
import time
import datetime
import schedule
import logging
import os
import pandas as pd

# ======================
# 🔑 CHIAVI E TOKEN
# ======================
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ======================
# 📂 PERCORSI CSV
# ======================
CSV_PATHS = {
    "calcio": "downloads/calcio/",
    "basket": "downloads/basket/",
    "football": "downloads/football/"
}

# ======================
# ⚙️ CONFIG
# ======================
MIN_PROBABILITY = 0.75  # percentuale minima vincita
CHECK_INTERVAL_HOURS = 2
sent_matches = set()  # per non inviare doppi pronostici

# Logging
logging.basicConfig(level=logging.INFO)

# ======================
# 📡 TELEGRAM
# ======================
def send_to_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Errore Telegram: {e}")

# ======================
# 📂 LETTURA CSV
# ======================
def load_csv_files(sport):
    path = CSV_PATHS.get(sport, "")
    if not os.path.exists(path):
        return pd.DataFrame()

    all_files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith(".csv")]
    if not all_files:
        return pd.DataFrame()

    dfs = []
    for file in all_files:
        try:
            df = pd.read_csv(file)
            dfs.append(df)
        except Exception as e:
            logging.error(f"Errore lettura {file}: {e}")
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

def filter_upcoming_matches(df, sport):
    now = datetime.datetime.utcnow()

    if sport == "calcio":
        if "date" in df.columns:
            df["match_date"] = pd.to_datetime(df["date"], errors="coerce")
            return df[df["match_date"] > now]

    elif sport == "basket":
        if "Date" in df.columns and "Start (ET)" in df.columns:
            df["match_date"] = pd.to_datetime(df["Date"] + " " + df["Start (ET)"], errors="coerce")
            return df[df["match_date"] > now]

    elif sport == "football":
        if "Date" in df.columns and "Time" in df.columns:
            df["match_date"] = pd.to_datetime(df["Date"] + " " + df["Time"], errors="coerce")
            if "Winner/tie" in df.columns:
                df["is_future"] = df["Winner/tie"].astype(str).str.contains("preview", case=False, na=False)
            else:
                df["is_future"] = False
            return df[(df["match_date"] > now) | (df["is_future"])]

    return pd.DataFrame()

# ======================
# 📡 ODDS API (solo se serve)
# ======================
def get_odds(sport_key, markets="h2h,totals,spreads"):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"Errore Odds API {sport_key}: {e}")
        return []

# ======================
# 🔮 ANALISI
# ======================
def analyze_match(match, sport):
    try:
        home = match.get("home_team", "Sconosciuto")
        away = match.get("away_team", "Sconosciuto")
        start_time = match.get("commence_time", "N/D")

        if "bookmakers" not in match or not match["bookmakers"]:
            return None
        bookmaker = match["bookmakers"][0]
        if not bookmaker.get("markets"):
            return None
        market = bookmaker["markets"][0]
        outcomes = market.get("outcomes", [])
        if len(outcomes) < 2:
            return None

        name1, odds1 = outcomes[0]["name"], float(outcomes[0]["price"])
        name2, odds2 = outcomes[1]["name"], float(outcomes[1]["price"])

        winner = name1 if odds1 < odds2 else name2
        probability = round((1 / min(odds1, odds2)), 2)

        return {
            "sport": sport,
            "teams": f"{home} vs {away}",
            "winner": winner,
            "odds": min(odds1, odds2),
            "probability": probability,
            "start_time": start_time
        }
    except Exception:
        return None

# ======================
# 📊 JOB PRINCIPALE
# ======================
def job():
    logging.info("🔍 Controllo nuovi eventi...")
    found_any = False

    for sport in ["calcio", "basket", "football"]:
        df = load_csv_files(sport)
        if df.empty:
            continue

        upcoming = filter_upcoming_matches(df, sport)
        if upcoming.empty:
            continue

        # chiamata API solo se ci sono eventi candidati
        odds_data = get_odds("soccer_epl" if sport=="calcio" else "basketball_nba" if sport=="basket" else "americanfootball_nfl")

        for match in odds_data:
            analysis = analyze_match(match, sport)
            if analysis and analysis["probability"] >= MIN_PROBABILITY:
                event_id = f"{analysis['teams']}_{analysis['start_time']}"
                if event_id in sent_matches:
                    continue  # evita doppi

                sent_matches.add(event_id)
                found_any = True

                msg = (
                    f"📊 <b>Pronostico {analysis['sport'].capitalize()}</b>\n"
                    f"⚔️ {analysis['teams']}\n"
                    f"📅 {analysis['start_time']}\n"
                    f"🔮 Vincente probabile: <b>{analysis['winner']}</b>\n"
                    f"💰 Quota stimata: {analysis['odds']}\n"
                    f"📈 Probabilità stimata: {analysis['probability']*100:.1f}%"
                )
                send_to_telegram(msg)

    if not found_any:
        logging.info("ℹ️ Nessun pronostico trovato")
        send_to_telegram("ℹ️ Nessun pronostico trovato in questa scansione.")

# ======================
# ▶️ AVVIO
# ======================
if __name__ == "__main__":
    send_to_telegram("✅ Bot avviato su Render e pronto a cercare pronostici!")
    schedule.every(CHECK_INTERVAL_HOURS).hours.do(job)
    logging.info("🤖 Bot avviato. In attesa di invio pronostici...")

    while True:
        schedule.run_pending()
        time.sleep(30)
