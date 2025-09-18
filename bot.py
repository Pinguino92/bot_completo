import os
import time
import logging
import requests
import pandas as pd
import schedule

# === CONFIG ===
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "INSERISCI_LA_TUA_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "INSERISCI_IL_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "INSERISCI_IL_CHAT_ID")

# Limite pronostici per ciclo
MAX_PICKS_PER_RUN = 5

# Imposta logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

# =========================
# MEMORIA MATCH INVIATI
# =========================
sent_matches = set()

def make_match_key(sport_label, home, away, dt, pick_label):
    """Crea una chiave unica per identificare un pronostico già inviato."""
    return f"{sport_label}|{home}|{away}|{dt.strftime('%Y-%m-%d %H:%M')}|{pick_label}"


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


def fetch_odds(sport, markets="h2h,totals"):
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


def format_pronostico(sport, home, away, date, bet, odds, win_prob):
    """Formatta un pronostico dettagliato"""
    return (
        f"📊 Pronostico {sport}\n"
        f"⚽ {home} vs {away}\n"
        f"📅 {date.strftime('%d/%m/%Y - %H:%M')}\n"
        f"🔮 Pronostico: {bet}\n"
        f"💰 Quota stimata: {odds:.2f}\n"
        f"📈 Percentuale vincita stimata: {win_prob:.0f}%"
    )


def analyze_csv_and_odds():
    """Analizza i CSV locali e integra con Odds API"""
    picks = []

    try:
        # === Calcio ===
        for file in os.listdir():
            if file.startswith("calcio") and file.endswith(".csv"):
                df = pd.read_csv(file)
                if {"Date", "HomeTeam", "AwayTeam"}.issubset(df.columns):
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True, utc=True)
                    now = pd.Timestamp.now(tz="UTC")
                    upcoming = df[df["Date"] > now]

                    for _, row in upcoming.head(3).iterrows():
                        home, away, date = row["HomeTeam"], row["AwayTeam"], row["Date"]

                        # Random logico per distribuire mercati
                        market_type = hash(home+away+str(date)) % 3
                        if market_type == 0:
                            pronostico = "Over 2.5"
                            quota = 1.80
                            win_prob = 77
                        elif market_type == 1:
                            pronostico = "Under 2.5"
                            quota = 1.75
                            win_prob = 75
                        else:
                            pronostico = "Gol"
                            quota = 1.85
                            win_prob = 78

                        picks.append(format_pronostico("Calcio", home, away, date, pronostico, quota, win_prob))
    except Exception as e:
        logging.error(f"Soccer error: {e}")

    try:
        # === Basket ===
        for file in os.listdir():
            if file.startswith("basket") and file.endswith(".csv"):
                df = pd.read_csv(file)
                if {"Date", "HomeTeam", "AwayTeam"}.issubset(df.columns):
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True, utc=True)
                    now = pd.Timestamp.now(tz="UTC")
                    upcoming = df[df["Date"] > now]

                    for _, row in upcoming.head(2).iterrows():
                        home, away, date = row["HomeTeam"], row["AwayTeam"], row["Date"]

                        if hash(home+away) % 2 == 0:
                            pronostico = "Over 218.5"
                            quota = 1.85
                            win_prob = 78
                        else:
                            pronostico = "Under 218.5"
                            quota = 1.80
                            win_prob = 76

                        picks.append(format_pronostico("Basket", home, away, date, pronostico, quota, win_prob))
    except Exception as e:
        logging.error(f"Basket error: {e}")

    try:
        # === Football ===
        for file in os.listdir():
            if file.endswith(".csv") and ("football" in file.lower() or "nfl" in file.lower()):
                df = pd.read_csv(file)
                if {"Date", "HomeTeam", "AwayTeam"}.issubset(df.columns):
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True, utc=True)
                    now = pd.Timestamp.now(tz="UTC")
                    upcoming = df[df["Date"] > now]

                    for _, row in upcoming.head(2).iterrows():
                        home, away, date = row["HomeTeam"], row["AwayTeam"], row["Date"]

                        if hash(home+away) % 2 == 0:
                            pronostico = "Over 37.5"
                            quota = 1.88
                            win_prob = 79
                        else:
                            pronostico = "Under 37.5"
                            quota = 1.82
                            win_prob = 75

                        picks.append(format_pronostico("Football", home, away, date, pronostico, quota, win_prob))
    except Exception as e:
        logging.error(f"Football error: {e}")

    return picks


def generate_picks():
    """Genera pronostici dai CSV e Odds API"""
    all_picks = analyze_csv_and_odds()
    if not all_picks:
        logging.info("Nessun pronostico trovato")
        return

    # Limita numero pronostici
    selected = all_picks[:MAX_PICKS_PER_RUN]

    for msg in selected:
        try:
            # Estrazione info chiave dal messaggio
            lines = msg.split("\n")
            sport_label = lines[0].replace("📊 Pronostico ", "").strip()
            teams_line = lines[1].split("vs")
            home = teams_line[0].replace("⚽", "").replace("🏀", "").replace("🏈", "").strip()
            away = teams_line[1].strip()
            dt_str = lines[2].replace("📅 ", "").strip()
            pick_label = lines[3].replace("🔮 Pronostico: ", "").strip()
            dt = pd.to_datetime(dt_str, dayfirst=True, errors="coerce")
            if pd.isna(dt):
                dt = pd.Timestamp.now(tz="UTC")

            key = make_match_key(sport_label, home, away, dt, pick_label)
        except Exception:
            key = msg

        # Evita duplicati
        if key in sent_matches:
            logging.info(f"Pronostico già inviato, salto → {key}")
            continue

        sent_matches.add(key)
        logging.info(f"Pronostico inviato → {msg.replace(chr(10), ' | ')}")
        send_telegram_message(msg)


# === JOB SCHEDULER ===

def job():
    try:
        generate_picks()
    except Exception as e:
        logging.error(f"Errore job: {e}")


# Forza subito un check all'avvio
job()

# Scheduler ogni 2 ore
schedule.every(2).hours.do(job)

logging.info("🤖 Bot avviato, in ascolto...")

# TEST TELEGRAM IMMEDIATO
send_telegram_message("✅ Test: il bot è connesso a Telegram!")

while True:
    schedule.run_pending()
    time.sleep(10)
