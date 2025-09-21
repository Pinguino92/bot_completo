import os
import time
import logging
import requests
import datetime
import schedule
import pandas as pd
import glob
import os

# 🔑 Variabili ambiente (Render → Environment)
ODDS_API_KEY   = os.getenv("ODDS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

sent_predictions = set()  # evita duplicati

# Logging
logging.basicConfig(level=logging.INFO)

# Sports da analizzare
SPORTS = {
    "soccer_italy_serie_a": "⚽ Serie A - Italia",
    "soccer_italy_serie_b": "⚽ Serie B - Italia",
    "soccer_spain_la_liga": "⚽ La Liga - Spagna",
    "soccer_spain_segunda_division": "⚽ La Liga 2 - Spagna",
    "soccer_epl": "⚽ Premier League - Inghilterra",
    "soccer_championship": "⚽ Championship - Inghilterra",
    "soccer_germany_bundesliga": "⚽ Bundesliga - Germania",
    "soccer_germany_bundesliga2": "⚽ Bundesliga 2 - Germania",
    "soccer_france_ligue_one": "⚽ Ligue 1 - Francia",
    "soccer_france_ligue_two": "⚽ Ligue 2 - Francia",
    "basketball_nba": "🏀 NBA",
    "americanfootball_nfl": "🏈 NFL",
    "americanfootball_ncaaf": "🏈 NCAA Football"
}

# 📂 Caricamento CSV storici (data/ + downloads/)
def load_csv_data():
    csv_data = {}
    paths = glob.glob("data/*.csv") + glob.glob("downloads/**/*.csv", recursive=True)
    for path in paths:
        try:
            df = pd.read_csv(path)
            csv_data[os.path.basename(path)] = df
        except Exception:
            continue
    return csv_data

CSV_DATA = load_csv_data()

def _category_for_sport(sport_key: str) -> str:
    if sport_key.startswith("soccer_"):
        return "calcio"
    if sport_key.startswith("basketball_"):
        return "basket"
    if sport_key.startswith("americanfootball_"):
        return "football"
    return "misc"

def load_historical_data(sport_key: str):
    try:
        import pandas as pd
    except Exception:
        logging.warning("ℹ️ pandas non disponibile: salto caricamento storici.")
        return None

    categoria = _category_for_sport(sport_key)

    paths = []
    paths.extend(glob.glob(os.path.join("downloads", categoria, "*.csv")))
    paths.extend(glob.glob(os.path.join("data", categoria, "*.csv")))

    if not paths:
        logging.info(f"ℹ️ Nessun CSV storico trovato per {sport_key}.")
        return None

    dfs = []
    for p in paths:
        try:
            df = pd.read_csv(p)
            if not df.empty:
                dfs.append(df)
        except Exception as e:
            logging.warning(f"⚠️ Impossibile leggere {p}: {e}")

    if not dfs:
        logging.info(f"ℹ️ Nessun CSV valido per {sport_key}.")
        return None

    full = pd.concat(dfs, ignore_index=True)
    logging.info(f"📂 Storici caricati per {sport_key}: {len(paths)} file, {len(full)} righe totali.")
    return full
    
# Parametri filtro
MIN_PROB  = 60.0   # %
MIN_QUOTA = 1.50   # decimale

# Funzione invio Telegram
def send_to_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("⚠️ TELEGRAM_TOKEN o TELEGRAM_CHAT_ID mancanti.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            logging.error(f"Errore Telegram: {r.text}")
    except Exception as e:
        logging.error(f"Errore Telegram: {e}")

# Recupero odds dalle API
def get_odds(sport: str):
    if not ODDS_API_KEY:
        logging.error("⚠️ ODDS_API_KEY mancante.")
        return []

    if sport.startswith("soccer_"):
        markets = "h2h,btts,totals"
    else:
        markets = "h2h,totals"

    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": markets,
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
def analyze_matches(sport: str, matches: list, hist_df=None):
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
                continue

            home = match.get("home_team", "Home")
            away = match.get("away_team", "Away")

            any_market_found = False

            for bookmaker in match.get("bookmakers", []):
                bookmaker_name = bookmaker.get("title", "Sconosciuto")

                for market in bookmaker.get("markets", []):
                    outcomes = market.get("outcomes", [])
                    if len(outcomes) < 2:
                        continue

                    market_key = market.get("key", "")
                    if sport.startswith("soccer_"):
                        if market_key == "totals":
                            outcomes = [o for o in outcomes if str(o.get("point")) == "2.5"]

                    any_market_found = True
                    try:
                        best_outcome = min(outcomes, key=lambda x: float(x["price"]))
                        quota = float(best_outcome["price"])
                        prob_api = round((1.0 / quota) * 100.0, 1)
                    except Exception:
                        continue

                    # 🔹 Calcolo prob_csv dai dati storici
                    prob_csv = None
                    if hist_df is not None:
                        try:
                            team_matches = hist_df[
                                (hist_df['HomeTeam'] == home) | (hist_df['AwayTeam'] == away)
                            ]
                            if not team_matches.empty:
                                total_matches = len(team_matches)
                                home_wins = len(team_matches[(team_matches['HomeTeam'] == home) & (team_matches['FTR'] == 'H')])
                                away_wins = len(team_matches[(team_matches['AwayTeam'] == away) & (team_matches['FTR'] == 'A')])

                                home_win_rate = (home_wins / total_matches) * 100 if total_matches > 0 else 0
                                away_win_rate = (away_wins / total_matches) * 100 if total_matches > 0 else 0

                                home_goals_scored = team_matches.loc[team_matches['HomeTeam'] == home, 'FTHG'].mean()
                                home_goals_conceded = team_matches.loc[team_matches['HomeTeam'] == home, 'FTAG'].mean()
                                away_goals_scored = team_matches.loc[team_matches['AwayTeam'] == away, 'FTAG'].mean()
                                away_goals_conceded = team_matches.loc[team_matches['AwayTeam'] == away, 'FTHG'].mean()

                                prob_csv = (
                                    (home_win_rate * 0.4) +
                                    ((100 - away_win_rate) * 0.2) +
                                    ((home_goals_scored - home_goals_conceded) * 5) +
                                    ((away_goals_conceded - away_goals_scored) * 5)
                                )
                                prob_csv = max(0, min(100, prob_csv))
                        except Exception as e:
                            logging.warning(f"⚠️ Errore calcolo prob CSV per {home} vs {away}: {e}")

                    # 🔹 Combina API + CSV
                    if prob_csv is not None:
                        probability = round((prob_api * 0.5) + (prob_csv * 0.5), 1)
                    else:
                        probability = prob_api

                    prediction_id = f"{sport}{home}{away}{market_key}{best_outcome.get('name','N/D')}"
                    base_msg = (
                        f"{SPORTS.get(sport, sport)}\n"
                        f"📌 {home} vs {away}\n"
                        f"📅 {start_time.strftime('%d/%m/%Y %H:%M')}\n"
                        f"🏦 Bookmaker: {bookmaker_name}\n"
                        f"🔮 Pronostico: {best_outcome.get('name','N/D')} ({market_key})\n"
                        f"💰 Quota: {quota}\n"
                        f"📈 Probabilità stimata: {probability}%"
                    )

                    if prediction_id not in sent_predictions:
                        sent_predictions.add(prediction_id)
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
        hist_df = load_historical_data(sport)
        matches = get_odds(sport)
        accettati, rifiutati = analyze_matches(sport, matches, hist_df)

        for msg in accettati:
            send_to_telegram(msg)

        tot_ok += len(accettati)
        tot_ko += len(rifiutati)

    logging.info(f"📊 Totale pronostici inviati: {tot_ok}")
    logging.info(f"❌ Eventi scartati: {tot_ko}")
    if tot_ok == 0 and tot_ko == 0:
        send_to_telegram("ℹ️ Nessun match disponibile entro 48h (nessuna quota).")

# --- Schedule fisso ---
schedule_times = ["07:00", "11:00", "17:00"]
for t in schedule_times:
    schedule.every().day.at(t).do(job)

if __name__ == "__main__":
    send_to_telegram("✅ Bot avviato su Render e pronto a cercare pronostici!")
    logging.info("🤖 Bot avviato. In attesa di invio pronostici...")
    job()
    while True:
        schedule.run_pending()
        time.sleep(30)
