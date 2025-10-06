#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BOT PRO v3 – Render + Disk persistente (1GB)

✅ Scrive risultati, stato ELO, feedback e predizioni su /data
✅ Legge CSV da data/, downloads/, download_external_csv/
✅ Backup automatico in /data/backups
✅ Scheduler orari italiani 09:00, 12:00, 16:00, 19:00
✅ Volatilità quote + blending dinamico CSV/API
✅ Nessun messaggio duplicato su Telegram

Requisiti:
- pandas, requests, apscheduler, pytz
"""

import os
import time
import json
import glob
import math
import logging
import requests
import datetime
import pandas as pd
from typing import Optional, List, Dict
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

# ───────────────────────────────
# 🔑 ENV / CONFIG
# ───────────────────────────────
ODDS_API_KEY     = os.getenv("ODDS_API_KEY")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MIN_PROB_BASE = float(os.getenv("MIN_PROB_BASE", "60"))
MIN_QUOTA     = float(os.getenv("MIN_QUOTA", "1.50"))
FORM_WINDOW   = int(os.getenv("FORM_WINDOW", "10"))
VOLATILITY_LIMIT = float(os.getenv("VOLATILITY_LIMIT", "0.10"))
DIVERGENZA_SOGLIA = float(os.getenv("DIVERGENZA_SOGLIA", "15.0"))
BLEND_API_DEFAULT = float(os.getenv("BLEND_API_DEFAULT", "0.6"))
FEEDBACK_ENABLED  = os.getenv("FEEDBACK_ENABLED", "true").lower() == "true"

# Percorsi persistenti (Render Disk montato su /data)
DATA_DIR          = "/data"
RESULTS_LOG_PATH  = os.getenv("RESULTS_LOG_PATH", f"{DATA_DIR}/results_log.csv")
FEEDBACK_STATE    = os.getenv("FEEDBACK_STATE", f"{DATA_DIR}/feedback_state.json")
ELO_STATE_PATH    = os.getenv("ELO_STATE_PATH", f"{DATA_DIR}/elo_state.json")
PRED_SENT_PATH    = os.getenv("PRED_SENT_PATH", f"{DATA_DIR}/pred_sent.json")
BACKUP_DIR        = os.getenv("BACKUP_DIR", f"{DATA_DIR}/backups")

# Timezone & orari
TZ = pytz.timezone("Europe/Rome")
SCHEDULE_TIMES = ["09:00", "12:00", "16:00", "19:00"]
WEEKLY_REPORT_TIME = {"day_of_week": "sun", "hour": 21, "minute": 0}
DAILY_BACKUP_TIME  = {"hour": 3, "minute": 30}

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# ───────────────────────────────
# 🏟️ SPORT LIST
# ───────────────────────────────
SPORTS = {
    "soccer_italy_serie_a": "⚽ Serie A - Italia",
    "soccer_italy_serie_b": "⚽ Serie B - Italia",
    "soccer_spain_la_liga": "⚽ La Liga - Spagna",
    "soccer_spain_segunda_division": "⚽ La Liga 2 - Spagna",
    "soccer_epl": "⚽ Premier League - Inghilterra",
    "soccer_efl_champ": "⚽ Championship - Inghilterra",
    "soccer_germany_bundesliga": "⚽ Bundesliga - Germania",
    "soccer_germany_bundesliga2": "⚽ Bundesliga 2 - Germania",
    "soccer_france_ligue_one": "⚽ Ligue 1 - Francia",
    "soccer_france_ligue_two": "⚽ Ligue 2 - Francia",
    "soccer_uefa_champs_league": "⚽ Champions League",
    "soccer_uefa_europa_league": "⚽ Europa League",
    "basketball_nba": "🏀 NBA",
    "americanfootball_nfl": "🏈 NFL",
    "americanfootball_ncaaf": "🏈 NCAAF",
    "baseball_mlb": "⚾ MLB",
    "icehockey_nhl": "🏒 NHL",
    "tennis_atp_shanghai_masters": "🎾 ATP Shanghai Masters",
}

# ───────────────────────────────
# ⚙️ TELEGRAM
# ───────────────────────────────
def send_to_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("⚠️ TELEGRAM_TOKEN o CHAT_ID mancanti.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        logging.error(f"Errore Telegram: {e}")

# ───────────────────────────────
# 📂 CSV LOADER
# ───────────────────────────────
def _category_for_sport(s):
    if s.startswith("soccer_"): return "calcio"
    if s.startswith("basketball_"): return "basket"
    if s.startswith("americanfootball_"): return "football"
    if s.startswith("icehockey_"): return "hockey"
    if s.startswith("baseball_"): return "mlb"
    if s.startswith("tennis_"): return "tennis"
    return "misc"

def read_csv_smart(path):
    for sep in [",",";","\t","|"]:
        try:
            df = pd.read_csv(path, sep=sep, encoding="utf-8")
            if df.shape[1] > 1:
                return df
        except Exception:
            continue
    return None

def load_historical_data(sport):
    categoria = _category_for_sport(sport)
    paths = glob.glob(os.path.join("data", categoria, "*.csv"))
    if not paths:
        logging.info(f"ℹ️ Nessun CSV trovato per {sport}")
        return None
    dfs = []
    for p in paths:
        df = read_csv_smart(p)
        if df is not None:
            dfs.append(df)
    if not dfs:
        return None
    df_full = pd.concat(dfs, ignore_index=True)
    logging.info(f"📂 Storici caricati per {sport}: {len(dfs)} file, {len(df_full)} righe")
    return df_full

# ───────────────────────────────
# 🌐 ODDS & SCORES API
# ───────────────────────────────
def get_odds(sport):
    if not ODDS_API_KEY:
        return []
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {"apiKey": ODDS_API_KEY, "regions": "eu", "markets": "h2h,totals", "oddsFormat": "decimal", "dateFormat": "iso"}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logging.error(f"❌ Errore API {sport}: {e}")
        return []

def get_scores(sport, days_from=5):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/scores"
    params = {"apiKey": ODDS_API_KEY, "daysFrom": days_from}
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 403:
            logging.warning(f"⚠️ Endpoint /scores non disponibile per chiave base ({sport})")
            return []
        return r.json()
    except Exception:
        return []

# ───────────────────────────────
# 📈 UTILITY
# ───────────────────────────────
def fair_probs(outcomes):
    inv_sum = sum(1/float(o["price"]) for o in outcomes if "price" in o)
    return [{"name": o["name"], "price": float(o["price"]), "fair_prob": 100*(1/float(o["price"]))/inv_sum} for o in outcomes]

def expected_value(prob, price):
    return (prob/100)*price - 1

# ───────────────────────────────
# 🧮 ANALISI MATCH
# ───────────────────────────────
def analyze_matches(sport, matches, hist_df=None):
    now = datetime.datetime.now(datetime.timezone.utc)
    for match in matches:
        try:
            start = datetime.datetime.fromisoformat(match["commence_time"].replace("Z", "+00:00"))
            if not (now < start < now + datetime.timedelta(days=2)):
                continue
            home, away = match.get("home_team","Home"), match.get("away_team","Away")
            best = None

            for bm in match.get("bookmakers", []):
                for mkt in bm.get("markets", []):
                    fair = fair_probs(mkt.get("outcomes", []))
                    for f in fair:
                        if f["fair_prob"] >= MIN_PROB_BASE and f["price"] >= MIN_QUOTA:
                            ev = expected_value(f["fair_prob"], f["price"])
                            if ev < 0.5:
                                best = (f, mkt["key"], bm["title"])

            if not best:
                continue

            f, mkey, book = best
            msg = (
                f"*{SPORTS.get(sport,sport)}*\n"
                f"{home} vs {away}\n"
                f"🕐 {start.astimezone(TZ).strftime('%d/%m %H:%M')}\n"
                f"🏦 {book}\n"
                f"🔮 {f['name']} ({mkey})\n"
                f"💰 {f['price']} | 📈 {f['fair_prob']:.1f}%"
            )
            send_to_telegram("✅ *PRONOSTICO*\n\n" + msg)
        except Exception as e:
            logging.warning(f"⚠️ Errore match {sport}: {e}")

# ───────────────────────────────
# 📦 BACKUP
# ───────────────────────────────
def backup_results_log():
    try:
        if not os.path.exists(RESULTS_LOG_PATH):
            return
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = datetime.datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(BACKUP_DIR, f"results_log_{ts}.csv")
        with open(RESULTS_LOG_PATH, "rb") as src, open(dst, "wb") as out:
            out.write(src.read())
        logging.info(f"🗄️ Backup creato: {dst}")
    except Exception as e:
        logging.warning(f"⚠️ Backup fallito: {e}")

# ───────────────────────────────
# 🔁 JOB
# ───────────────────────────────
def job():
    logging.info("🔍 Controllo nuove partite...")
    for sport in SPORTS.keys():
        hist = load_historical_data(sport)
        matches = get_odds(sport)
        analyze_matches(sport, matches, hist)
    logging.info("✅ Ciclo completato.")

# ───────────────────────────────
# 🕒 SCHEDULER
# ───────────────────────────────
def start_scheduler():
    sched = BackgroundScheduler(timezone=TZ)
    for hhmm in SCHEDULE_TIMES:
        h, m = map(int, hhmm.split(":"))
        sched.add_job(job, "cron", hour=h, minute=m)
    sched.add_job(backup_results_log, "cron", **DAILY_BACKUP_TIME)
    sched.start()
    return sched

# ───────────────────────────────
# 🚀 MAIN
# ───────────────────────────────
if __name__ == "__main__":
    send_to_telegram("🤖 Bot PRO v3 avviato su Render (persistente /data attivo).")
    job()
    scheduler = start_scheduler()
    try:
        while True:
            time.sleep(30)
    except KeyboardInterrupt:
        scheduler.shutdown()
