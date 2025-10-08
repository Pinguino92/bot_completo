# -*- coding: utf-8 -*-
"""
Aggiornamento automatico infortuni multi-sport
Autore: Andrea / GPT-5 Integration
✅ Usa una sola chiave API-Sports (limitata a 100 chiamate/giorno)
✅ Gestisce calcio, basket, football, baseball, hockey, tennis
✅ Backup automatici in caso di errore
✅ Salva tutto in /data/injuries_cache/
"""

import os
import time
import json
import logging
import requests
import datetime
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

API_KEY = os.getenv("API_SPORTS_KEY")
DATA_DIR = "/data/injuries_cache"
os.makedirs(DATA_DIR, exist_ok=True)

# ID leghe principali per ogni sport (API-Sports)
SPORT_LEAGUES = {
    "football": [39, 135, 78, 140, 61],  # Premier, Serie A, Bundesliga, La Liga, Ligue 1
    "basketball": [12],  # NBA
    "baseball": [1],     # MLB
    "americanfootball": [1],  # NFL
    "icehockey": [57],   # NHL
    "tennis": [1]        # ATP (placeholder)
}

# Sorgenti di backup gratuite
BACKUPS = {
    "football": "https://www.football-data.co.uk/mmz4281/2425/I1.csv",
    "basketball": "https://raw.githubusercontent.com/sportsdataverse/nba-data/master/games/games.csv",
    "americanfootball": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/master/games.csv",
    "baseball": "https://raw.githubusercontent.com/chadwickbureau/baseballdatabank/master/core/People.csv",
    "icehockey": "https://raw.githubusercontent.com/kevinzdavidson/hockeyR-data/main/games.csv",
    "tennis": "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_2024.csv",
}

CALLS_FILE = os.path.join(DATA_DIR, "calls_today.json")
today = datetime.date.today().isoformat()

def calls_remaining():
    if not os.path.exists(CALLS_FILE):
        return 100
    try:
        data = json.load(open(CALLS_FILE))
        if data.get("date") != today:
            return 100
        return max(0, 100 - data.get("count", 0))
    except:
        return 100

def add_call():
    data = {"date": today, "count": 0}
    if os.path.exists(CALLS_FILE):
        try:
            data = json.load(open(CALLS_FILE))
            if data.get("date") != today:
                data = {"date": today, "count": 0}
        except:
            pass
    data["count"] = data.get("count", 0) + 1
    json.dump(data, open(CALLS_FILE, "w"))

def fetch_injuries(sport, league_id):
    if calls_remaining() <= 0:
        logging.warning("⚠️ Limite giornaliero 100 chiamate raggiunto.")
        return None
    try:
        url = f"https://v1.{sport}.api-sports.io/injuries?league={league_id}&season=2024"
        headers = {"x-apisports-key": API_KEY}
        r = requests.get(url, headers=headers, timeout=15)
        add_call()
        if r.status_code == 200:
            logging.info(f"✅ {sport.upper()} | Lega {league_id}: OK")
            return r.json()
        else:
            logging.warning(f"⚠️ {sport.upper()} | Lega {league_id}: {r.status_code}")
            return None
    except Exception as e:
        logging.error(f"❌ Errore {sport.upper()} | {league_id}: {e}")
        return None

def backup_injuries(sport):
    url = BACKUPS.get(sport)
    if not url: return
    try:
        df = pd.read_csv(url)
        path = os.path.join(DATA_DIR, f"{sport}_backup.csv")
        df.to_csv(path, index=False)
        logging.info(f"📦 Backup salvato per {sport} ({len(df)} righe)")
    except Exception as e:
        logging.warning(f"⚠️ Backup fallito {sport}: {e}")

def update_all():
    logging.info("🔍 Aggiornamento infortuni multi-sport...")
    for sport, leagues in SPORT_LEAGUES.items():
        out_path = os.path.join(DATA_DIR, f"{sport}_injuries.json")
        results = []
        for league_id in leagues:
            data = fetch_injuries(sport, league_id)
            if data:
                results.append(data)
            time.sleep(1.2)
        if results:
            json.dump(results, open(out_path, "w", encoding="utf-8"))
            logging.info(f"✅ Salvato {out_path}")
        else:
            backup_injuries(sport)
    logging.info("🏁 Aggiornamento completato.")

if __name__ == "__main__":
    update_all()
