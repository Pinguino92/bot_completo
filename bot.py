import requests
import time
import datetime
import schedule
import logging
import pandas as pd

# 🔑 Chiavi integrate
ODDS_API_KEY = "INSERISCI_API_KEY"
TELEGRAM_TOKEN = "INSERISCI_TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = "INSERISCI_CHAT_ID"

# Logging
logging.basicConfig(level=logging.INFO)

# Intervallo controllo
INTERVAL_HOURS = 2

# === FUNZIONI BASE ===
def send_to_telegram(message: str):
    """Invia messaggio a Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Errore Telegram: {e}")

def load_csv(path: str, sport: str):
    """Carica un CSV e filtra match futuri"""
    try:
        df = pd.read_csv(path)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            now = datetime.datetime.utcnow()
            futuri = df[df["Date"] > now]
            logging.info(f"{sport}: trovati {len(futuri)} match futuri")
            return futuri
        else:
            logging.warning(f"{sport}: CSV senza colonna Date valida")
            return pd.DataFrame()
    except Exception as e:
        logging.error(f"{sport}: errore lettura CSV {path}: {e}")
        return pd.DataFrame()

def job():
    """Job principale: controlla CSV e genera eventuali pronostici"""
    logging.info("🔍 Avvio controllo eventi...")

    # Carico esempi CSV (modifica con i tuoi path)
    calcio = load_csv("downloads/calcio/1IwH4OWw8K7d6lA6L_yOHDv0sPWzAjB7R.csv", "Calcio")
    basket = load_csv("downloads/basket/1jW1s1ZsMPG9nqRSv7eMncSeYxGl7zaJ1.csv", "Basket")
    football = load_csv("downloads/football/1M49rGXflx9jX5PnDP87JvI145f2lNEuU.csv", "Football")

    totale_eventi = len(calcio) + len(basket) + len(football)

    if totale_eventi == 0:
        logging.info("❌ Nessun evento futuro trovato nei CSV.")
        send_to_telegram("❌ Nessun evento futuro trovato nei CSV.")
    else:
        send_to_telegram(f"📊 Trovati {totale_eventi} eventi futuri nei CSV!")
        # Qui puoi aggiungere logica di pronostici + Odds API

# === SCHEDULAZIONE ===
def schedule_jobs():
    schedule.every(INTERVAL_HOURS).hours.do(job)

if __name__ == "__main__":
    schedule_jobs()
    logging.info("🤖 Bot avviato. In attesa di invio pronostici...")

    # 👇 Test immediato
    send_to_telegram("✅ Bot collegato correttamente")
    job()

    while True:
        schedule.run_pending()
        time.sleep(30)


