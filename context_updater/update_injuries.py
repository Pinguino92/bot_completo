# -*- coding: utf-8 -*-
"""
✅ CHECK INJURY + DATI ESTESI MULTISPORT (REV 2025)
- Supporta: calcio, basket, tennis, NFL, NCAA, MLB
- Limite 100 chiamate/giorno gestito via file
- Dati estesi (forma, standings, stats) solo per calcio
- Stagione rilevata automaticamente (2025/26)
"""

import os
import json
import time
import logging
import requests
import pandas as pd
from datetime import datetime

# ──────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

DATA_DIR = "/data/injuries_cache"
os.makedirs(DATA_DIR, exist_ok=True)

API_SPORTS_KEY = os.getenv("API_SPORTS_KEY")
if not API_SPORTS_KEY:
    logging.warning("⚠️ Nessuna API_SPORTS_KEY trovata. Il modulo non verrà eseguito.")
    exit()

HEADERS = {"x-apisports-key": API_SPORTS_KEY}

# ⚽🏈🏀🎾⚾ Leghe principali (limitate per non superare 100 chiamate totali)
SPORT_LEAGUES = {
    "football": [39, 135, 140, 78, 61],      # Premier, Serie A, LaLiga, Bundesliga, Ligue 1
    "americanfootball": [1, 2],              # NFL, NCAA
    "baseball": [1],                         # MLB
    "basketball": [12, 2],                   # NBA, Euroleague
    "tennis": [52, 23, 5]                    # ATP, WTA, Challenger
}

MAX_API_CALLS = 100
API_COUNTER_PATH = f"{DATA_DIR}/api_call_count.json"


# ──────────────────────────────────────────────────────────────
# 📆 STAGIONE CORRENTE AUTOMATICA
# ──────────────────────────────────────────────────────────────
def current_season():
    """Restituisce l'anno della stagione attuale in base alla data (es. 2025 per stagione 2025/26)"""
    today = datetime.utcnow()
    year = today.year
    return year if today.month >= 7 else year - 1


# ──────────────────────────────────────────────────────────────
# 📊 GESTIONE LIMITE GIORNALIERO
# ──────────────────────────────────────────────────────────────
def load_api_count():
    """Carica o inizializza il contatore giornaliero"""
    if not os.path.exists(API_COUNTER_PATH):
        return {"date": datetime.utcnow().strftime("%Y-%m-%d"), "count": 0}

    try:
        with open(API_COUNTER_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # reset se giorno diverso
        if data.get("date") != datetime.utcnow().strftime("%Y-%m-%d"):
            data = {"date": datetime.utcnow().strftime("%Y-%m-%d"), "count": 0}
        return data
    except Exception:
        return {"date": datetime.utcnow().strftime("%Y-%m-%d"), "count": 0}


def save_api_count(data):
    """Salva contatore su file"""
    with open(API_COUNTER_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


api_data = load_api_count()
api_call_count = api_data["count"]


# ──────────────────────────────────────────────────────────────
# SAFE REQUEST CON LIMITO
# ──────────────────────────────────────────────────────────────
def safe_get(url, params=None):
    """Esegue GET rispettando limite giornaliero e rate limit"""
    global api_call_count, api_data
    if api_call_count >= MAX_API_CALLS:
        logging.warning("🚫 Limite giornaliero di 100 chiamate API raggiunto.")
        return None

    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        api_call_count += 1
        api_data["count"] = api_call_count
        save_api_count(api_data)

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 429:
            logging.warning("⏳ Troppe richieste, attesa 60s...")
            time.sleep(60)
            return safe_get(url, params)
        else:
            logging.error(f"❌ Errore HTTP {resp.status_code} su {url}")
            return None
    except Exception as e:
        logging.error(f"Errore connessione: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# LIVELLI API:
# v3 → sport recenti (football, basketball, tennis)
# v1 → sport legacy (americanfootball, baseball)
# ──────────────────────────────────────────────────────────────
def fetch_injuries(sport, league_id):
    """Recupera infortuni da API diversi in base allo sport"""
    if sport in ["football", "basketball", "tennis"]:
        url = f"https://v3.{sport}.api-sports.io/injuries"
    elif sport in ["americanfootball", "baseball"]:
        url = f"https://v1.{sport}.api-sports.io/injuries"
    else:
        logging.warning(f"Sport non riconosciuto per infortuni: {sport}")
        return []

    data = safe_get(url, {"league": league_id, "season": current_season()})
    if not data or "response" not in data:
        return []
    return data["response"]


# ──────────────────────────────────────────────────────────────
# FETCH STANDINGS / FORMA / TEAM STATS (solo calcio)
# ──────────────────────────────────────────────────────────────
def fetch_standings(league_id):
    url = "https://v3.football.api-sports.io/standings"
    data = safe_get(url, {"league": league_id, "season": current_season()})
    return data.get("response", []) if data else []


def fetch_recent_form(league_id):
    url = "https://v3.football.api-sports.io/fixtures"
    data = safe_get(url, {"league": league_id, "season": current_season(), "last": 5})
    return data.get("response", []) if data else []


def fetch_team_stats_all(league_id):
    """Recupera statistiche per tutte le squadre di una lega di calcio"""
    base_url = "https://v3.football.api-sports.io"
    teams_data = safe_get(f"{base_url}/teams", {"league": league_id, "season": current_season()})
    if not teams_data or "response" not in teams_data:
        return []

    team_ids = [t["team"]["id"] for t in teams_data["response"] if "team" in t]
    results = []

    for tid in team_ids:
        if api_call_count >= MAX_API_CALLS:
            logging.warning("⚠️ Stop: limite chiamate raggiunto durante team stats.")
            break

        stats_data = safe_get(f"{base_url}/teams/statistics", {"league": league_id, "team": tid, "season": current_season()})
        if stats_data and "response" in stats_data:
            results.append(stats_data["response"])
        time.sleep(0.3)

    return results


# ──────────────────────────────────────────────────────────────
# MAIN UPDATE (evita file vuoti)
# ──────────────────────────────────────────────────────────────
def update_all():
    global api_call_count
    for sport, leagues in SPORT_LEAGUES.items():
        all_injuries = []

        for lid in leagues:
            if api_call_count >= MAX_API_CALLS:
                break

            logging.info(f"🔎 {sport.upper()} | LEAGUE {lid} | SEASON {current_season()}")

            injuries = fetch_injuries(sport, lid)
            if injuries:
                all_injuries.extend(injuries)
            else:
                logging.warning(f"⚠️ Nessun dato ricevuto per {sport} - League {lid}")

            # Solo calcio → extra data
            if sport == "football":
                standings = fetch_standings(lid)
                recent_form = fetch_recent_form(lid)
                team_stats = fetch_team_stats_all(lid)

                if any([standings, recent_form, team_stats]):
                    pd.DataFrame(standings).to_json(f"{DATA_DIR}/football_standings_{lid}.json", orient="records", force_ascii=False, indent=2)
                    pd.DataFrame(recent_form).to_json(f"{DATA_DIR}/football_recent_form_{lid}.json", orient="records", force_ascii=False, indent=2)
                    pd.DataFrame(team_stats).to_json(f"{DATA_DIR}/football_team_stats_{lid}.json", orient="records", force_ascii=False, indent=2)
                    logging.info(f"⚽ Salvati dati estesi calcio (lega {lid})")

        # Salva infortuni per sport solo se non vuoto
        if all_injuries:
            out_path = f"{DATA_DIR}/{sport}_injuries.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(all_injuries, f, indent=2, ensure_ascii=False)
            logging.info(f"💾 Salvati infortuni {sport} ({len(all_injuries)} elementi)")
        else:
            logging.warning(f"⚠️ Nessun dato salvato per {sport}")

    logging.info(f"✅ Update completato con {api_call_count} chiamate totali.")

    return injuries_data



# ──────────────────────────────────────────────────────────────
# ESECUZIONE
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    update_all()
