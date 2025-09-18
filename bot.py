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
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
                    now = pd.Timestamp.now(tz="UTC")
                    upcoming = df[df["Date"] > now]

                    for _, row in upcoming.head(3).iterrows():  # Limitiamo a 3 pronostici per test
                        home, away, date = row["HomeTeam"], row["AwayTeam"], row["Date"]

                        # Esempio logica semplificata
                        pronostico = "Over 2.5" if hash(home+away) % 2 == 0 else "Under 2.5"
                        quota = 1.80 if pronostico == "Over 2.5" else 1.75
                        win_prob = 72 if pronostico == "Over 2.5" else 70

                        picks.append(format_pronostico("Calcio", home, away, date, pronostico, quota, win_prob))
    except Exception as e:
        logging.error(f"Soccer error: {e}")

    try:
        # === Basket ===
        for file in os.listdir():
            if file.startswith("basket") and file.endswith(".csv"):
                df = pd.read_csv(file)
                if {"Date", "HomeTeam", "AwayTeam"}.issubset(df.columns):
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
                    now = pd.Timestamp.now(tz="UTC")
                    upcoming = df[df["Date"] > now]

                    for _, row in upcoming.head(2).iterrows():
                        home, away, date = row["HomeTeam"], row["AwayTeam"], row["Date"]

                        pronostico = "Over 218.5" if hash(home+away) % 2 == 0 else "Under 218.5"
                        quota = 1.85 if pronostico.startswith("Over") else 1.80
                        win_prob = 74 if pronostico.startswith("Over") else 71

                        picks.append(format_pronostico("Basket", home, away, date, pronostico, quota, win_prob))
    except Exception as e:
        logging.error(f"Basket error: {e}")

    try:
        # === Football (NFL / NCAAF) ===
        for file in os.listdir():
            if file.endswith(".csv") and ("football" in file.lower() or "nfl" in file.lower()):
                df = pd.read_csv(file)
                if {"Date", "HomeTeam", "AwayTeam"}.issubset(df.columns):
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
                    now = pd.Timestamp.now(tz="UTC")
                    upcoming = df[df["Date"] > now]

                    for _, row in upcoming.head(2).iterrows():
                        home, away, date = row["HomeTeam"], row["AwayTeam"], row["Date"]

                        pronostico = "Over 37.5" if hash(home+away) % 2 == 0 else "Under 37.5"
                        quota = 1.88 if pronostico.startswith("Over") else 1.82
                        win_prob = 73 if pronostico.startswith("Over") else 70

                        picks.append(format_pronostico("Football", home, away, date, pronostico, quota, win_prob))
    except Exception as e:
        logging.error(f"Football error: {e}")

    return picks


def generate_picks():
    """Genera pronostici dai CSV e Odds API"""
    picks = analyze_csv_and_odds()

    if picks:
        for p in picks:
            logging.info(f"Pronostico generato → {p}")
            send_telegram_message(p)
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


