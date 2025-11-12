#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BOT PRO v2 – pronto per Render/GitHub con persistente /data

✅ Aggiunto supporto a Render Disk:
   - Tutti i file di log, feedback, elo, dedup e backup ora vengono salvati in /data/

✅ Patch integrate (richieste):
   (2) Blending adattivo API/CSV/MODEL per sport (+ stato su /data/feedback_state.json)
   (3) Filtri qualità addizionali: bookmaker minimi
   (4) Modelli sport-specifici (calcio/tennis/basket) per prob_model
   (7) Stake consigliato con Kelly cappato
   +  log_prediction estesa con prob_api/prob_csv/prob_model/prob_final/ev
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
from statistical_predictions import run_statistical_batch

# ── i tuoi import invariati ───────────────────────────────────
from context_engine.context_manager import context_adjustment, update_context_data
from learning_engine.train_model import ai_correction, train_model
from context_updater.update_injuries import update_all as update_injuries
from context_updater.update_weather import update_weather

# Scheduler TZ
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

# ──────────────────────────────────────────────────────────────
# 🔑 ENV / PARAMETRI
# ──────────────────────────────────────────────────────────────

# ✅ Directory persistente Render Disk
DATA_DIR = "/data"

ODDS_API_KEY     = os.getenv("ODDS_API_KEY")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Soglie globali (modificabili via ENV)
MIN_PROB_BASE = float(os.getenv("MIN_PROB_BASE", "60"))       # %
MIN_QUOTA     = float(os.getenv("MIN_QUOTA", "1.40"))         # decimale
FORM_WINDOW   = int(os.getenv("FORM_WINDOW", "5"))           # ultime N partite
VOLATILITY_LIMIT = float(os.getenv("VOLATILITY_LIMIT", "0.50"))  # 50%

# blending e divergenze (legacy tuoi)
DIVERGENZA_SOGLIA = float(os.getenv("DIVERGENZA_SOGLIA", "15.0"))  # punti %
BLEND_API_DEFAULT = float(os.getenv("BLEND_API_DEFAULT", "0.6"))   # peso API

# feedback / risultati (✅ ora su /data/)
FEEDBACK_ENABLED  = os.getenv("FEEDBACK_ENABLED", "true").lower() == "true"
RESULTS_LOG_PATH  = os.getenv("RESULTS_LOG_PATH",  f"{DATA_DIR}/results_log.csv")
FEEDBACK_STATE    = os.getenv("FEEDBACK_STATE",   f"{DATA_DIR}/feedback_state.json")
ELO_STATE_PATH    = os.getenv("ELO_STATE_PATH",   f"{DATA_DIR}/elo_state.json")

# backup (✅ ora su /data/backups)
BACKUP_DIR        = os.getenv("BACKUP_DIR", f"{DATA_DIR}/backups")

# dedup persistente (✅ ora su /data/)
PRED_SENT_PATH = f"{DATA_DIR}/sent_predictions.json"

# timezone & orari
TZ = pytz.timezone("Europe/Rome")
SCHEDULE_TIMES = ["09:00", "11:00", "13:00", "15:00", "17:00", "19:00", "21:00", "22:00"]  # invio pronostici
WEEKLY_REPORT_TIME = {"day_of_week": "sun", "hour": 22, "minute": 5}  # domenica 22:05
DAILY_BACKUP_TIME  = {"hour": 3, "minute": 30}  # tutti i giorni 03:30

# 💰 Stake management (punto 7)
BANKROLL = float(os.getenv("BANKROLL", "1000.0"))  # capitale per calcolo stake
KELLY_CAP = float(os.getenv("KELLY_CAP", "0.10"))  # cap frazione Kelly (5% default)

# log
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# dedup persistente
def pred_load() -> set:
    try:
        return set(json.load(open(PRED_SENT_PATH, "r", encoding="utf-8")))
    except:
        return set()

def pred_save(s: set):
    try:
        json.dump(list(s), open(PRED_SENT_PATH, "w", encoding="utf-8"))
    except:
        pass

sent_predictions = pred_load()

# ──────────────────────────────────────────────────────────────
# 🏟️ SPORT (mantiene quelli del tuo bot attuale)
# ──────────────────────────────────────────────────────────────
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
    "tennis_atp_paris_masters": "🎾 ATP Paris Masters",
    "basketball_nba_preseason": "🏀 NBA Preseason"
}

# Affidabilità relativa per sport (moltiplicatore)
SPORT_RELIABILITY = {
    "basketball_": 1.00,
    "baseball_":   1.00,
    "americanfootball_": 0.90,
    "icehockey_":  0.90,
    "tennis_":     0.85,
    "soccer_":     0.80,
}

# Soglie per sport
SPORT_THRESHOLDS = {
    "soccer_": {"prob": 60.0, "quota": 1.30},              # calcio
    "basketball_": {"prob": 67.0, "quota": 1.40},           # NBA
    "americanfootball_nfl": {"prob": 65.0, "quota": 1.50},  # NFL
    "americanfootball_ncaaf": {"prob": 62.0, "quota": 1.50},# NCAAF
    "baseball_mlb": {"prob": 65.0, "quota": 1.50},          # MLB
    "icehockey_nhl": {"prob": 60.0, "quota": 1.40},         # NHL
    "tennis_atp_paris_masters": {"prob": 65.0, "quota": 1.32},
}

# ────────────────────────────────────────────────
# ⚙️ MINIMO BOOKMAKER PER SPORT (filtri dinamici)
# ────────────────────────────────────────────────
MIN_BOOKMAKERS_BY_SPORT = {
    "soccer_": 2,        # calcio: 2 bookmaker bastano
    "basketball_": 2,    # NBA, Eurolega ecc.
    "icehockey_": 2,     # NHL: 2 bookmaker bastano
    "tennis_": 1,        # tennis: 1 solo
}
DEFAULT_MIN_BOOKMAKERS = 3

# ──────────────────────────────────────────────────────────────
# 📬 TELEGRAM
# ──────────────────────────────────────────────────────────────
def send_to_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("⚠️ TELEGRAM_TOKEN o TELEGRAM_CHAT_ID mancanti.")
        return
    try:
        # Escapa tutti i caratteri speciali per MarkdownV2
        safe_msg = (
            message.replace("\\", "\\\\")
                   .replace("_", "\\_")
                   .replace("*", "\\*")
                   .replace("[", "\\[")
                   .replace("]", "\\]")
                   .replace("(", "\\(")
                   .replace(")", "\\)")
                   .replace("~", "\\~")
                   .replace("`", "\\`")
                   .replace(">", "\\>")
                   .replace("#", "\\#")
                   .replace("+", "\\+")
                   .replace("-", "\\-")
                   .replace("=", "\\=")
                   .replace("|", "\\|")
                   .replace("{", "\\{")
                   .replace("}", "\\}")
                   .replace(".", "\\.")
                   .replace("!", "\\!")
        )

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": safe_msg,
            "parse_mode": "MarkdownV2"
        }, timeout=12)

        if r.status_code != 200:
            logging.error(f"Errore Telegram: {r.text}")
    except Exception as e:
        logging.error(f"Errore Telegram: {e}")


# ──────────────────────────────────────────────────────────────
# 🗂️ CSV LOADER (data/, downloads/, download_external_csv/)
# ──────────────────────────────────────────────────────────────
def _category_for_sport(sport_key: str) -> str:
    if sport_key.startswith("soccer_"): return "calcio"
    if sport_key.startswith("basketball_"): return "basket"
    if sport_key.startswith("americanfootball_"): return "football"
    if sport_key.startswith("icehockey_"): return "hockey"
    if sport_key.startswith("baseball_"): return "baseball"
    if sport_key.startswith("tennis_"): return "tennis"
    return "misc"

def read_csv_smart(path_or_url: str) -> Optional[pd.DataFrame]:
    seps = [",",";","\t","|"]
    encs = ["utf-8","latin1","cp1252"]
    for enc in encs:
        for sep in seps:
            try:
                df = pd.read_csv(path_or_url, sep=sep, encoding=enc)
                if df.shape[1] == 1 and any(ch in str(df.columns[0]) for ch in [",",";","\t","|"]):
                    continue
                df.columns = [str(c).strip() for c in df.columns]
                return df
            except Exception:
                continue
    return None

def _iter_external_sources(folder: str) -> List[str]:
    urls = []
    if not os.path.isdir(folder):
        return urls
    # file .csv locali
    urls.extend(glob.glob(os.path.join(folder, "*.csv")))
    # liste URL in .txt o .csv (una riga = un URL)
    for p in glob.glob(os.path.join(folder, "*.*")):
        ext = os.path.splitext(p)[1].lower()
        if ext in [".txt", ".list", ".urls", ".csv"]:
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        s = line.strip()
                        if s.startswith("http://") or s.startswith("https://"):
                            urls.append(s)
            except Exception:
                continue
    return urls

def load_historical_data(sport_key: str) -> Optional[pd.DataFrame]:
    categoria = _category_for_sport(sport_key)
    paths = []
    # locali
    for base in ["data", "downloads"]:
        paths.extend(glob.glob(os.path.join(base, categoria, "*.csv")))
    # esterni (file locali + liste URL)
    external_folder = os.path.join("download_external_csv", categoria)
    ext_sources = _iter_external_sources(external_folder)

    dfs = []
    if not paths and not ext_sources:
        logging.info(f"ℹ️ Nessun CSV trovato per {sport_key}.")
        return None

    for p in paths:
        df = read_csv_smart(p)
        if df is not None and not df.empty:
            dfs.append(df)
        else:
            logging.warning(f"⚠️ Errore lettura file locale {p}")

    for url in ext_sources:
        try:
            df = read_csv_smart(url)
            if df is not None and not df.empty:
                dfs.append(df)
            else:
                logging.warning(f"⚠️ Errore lettura URL {url}")
        except Exception as e:
            logging.warning(f"⚠️ Download fallito {url}: {e}")

    if not dfs:
        logging.info(f"ℹ️ Nessun dato storico valido per {sport_key}.")
        return None

    full = pd.concat(dfs, ignore_index=True, sort=False)
    logging.info(f"📂 Storici caricati per {sport_key}: {len(dfs)} sorgenti, {len(full)} righe.")
    return full

# ──────────────────────────────────────────────────────────────
# 🧾 ODDS & SCORES API (con retry/backoff)
# ──────────────────────────────────────────────────────────────
def _http_get(url, params, max_attempts=3, timeout=20):
    for attempt in range(max_attempts):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code in (422, 429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt == max_attempts - 1:
                logging.error(f"❌ GET fallita: {e}")
                return None
            time.sleep(2 ** attempt)
    return None

    # ────────────────────────────────────────────────
    # 📈 MERCATI PERSONALIZZATI PER SPORT
    # ────────────────────────────────────────────────
def fetch_odds(sport: str): 
    if sport.startswith("soccer_"):
        markets = "h2h,totals,spreads"
    elif sport.startswith("basketball_"):
        markets = "h2h,totals,spreads"
    elif sport.startswith("icehockey_"):
        markets = "h2h,totals,spreads"
    else:
        markets = "h2h,totals"

    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    r = _http_get(url, params)
    if not r:
        return []
    try:
        data = r.json()
        if isinstance(data, list):
            logging.info(f"📡 Quote ricevute per {sport}: {len(data)} eventi.")
        else:
            logging.warning(f"⚠️ Risposta inattesa per {sport}: {data}")
        return data if isinstance(data, list) else []
    except Exception as e:
        logging.error(f"❌ Errore parsing odds {sport}: {e}")
        return []

def get_scores(sport: str, days_from: int = 5):
    if not (ODDS_API_KEY and FEEDBACK_ENABLED):
        return []
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/scores"
    params = {"apiKey": ODDS_API_KEY, "daysFrom": days_from}
    r = _http_get(url, params)
    if not r:
        return []
    try:
        return r.json() if r.text else []
    except Exception as e:
        logging.warning(f"⚠️ get_scores json error {sport}: {e}")
        return []

# ──────────────────────────────────────────────────────────────
# 📐 FAIR ODDS / EV / UTIL
# ──────────────────────────────────────────────────────────────
def fair_probs_from_outcomes(outcomes: List[Dict]) -> List[Dict]:
    inv_sum = 0.0
    vals = []
    for o in outcomes:
        try:
            price = float(o["price"])
            inv = 1.0 / max(price, 1e-9)
            vals.append((o, price, inv))
            inv_sum += inv
        except Exception:
            continue
    fair_list = []
    if inv_sum <= 0:
        return fair_list
    for o, price, inv in vals:
        fair_p = (inv / inv_sum) * 100.0
        fair_list.append({"name": o.get("name",""), "price": price, "fair_prob": round(fair_p, 2), "point": o.get("point")})
    return fair_list

def expected_value(prob_percent: float, price: float) -> float:
    return (prob_percent/100.0) * price - 1.0

def get_thresholds(sport_key: str):
    # esatti
    for exact in ("americanfootball_nfl", "americanfootball_ncaaf", "baseball_mlb", "icehockey_nhl", "tennis_atp_shanghai_masters"):
        if sport_key == exact:
            t = SPORT_THRESHOLDS[exact]
            return t["prob"], max(t["quota"], MIN_QUOTA)
    # prefissi
    if sport_key.startswith("soccer_"):
        t = SPORT_THRESHOLDS["soccer_"]; return t["prob"], max(t["quota"], MIN_QUOTA)
    if sport_key.startswith("basketball_"):
        t = SPORT_THRESHOLDS["basketball_"]; return t["prob"], max(t["quota"], MIN_QUOTA)
    # fallback
    return MIN_PROB_BASE, MIN_QUOTA

def sport_reliability_weight(sport_key: str) -> float:
    for pref, w in SPORT_RELIABILITY.items():
        if sport_key.startswith(pref):
            return w
    return 1.0

# ──────────────────────────────────────────────────────────────
# 🔥 FORMA RECENTE
# ──────────────────────────────────────────────────────────────
def recent_form_rate_tennis(df: pd.DataFrame, player: str) -> Optional[float]:
    try:
        if {"player1","player2","winner"}.issubset(df.columns):
            sub = df[(df["player1"]==player)|(df["player2"]==player)].tail(FORM_WINDOW)
            if sub.empty: return None
            return 100.0*(sub["winner"]==player).sum()/len(sub)
        elif {"winner_name","loser_name"}.issubset(df.columns):
            sub = df[(df["winner_name"]==player)|(df["loser_name"]==player)].tail(FORM_WINDOW)
            if sub.empty: return None
            return 100.0*(sub["winner_name"]==player).sum()/len(sub)
        return None
    except Exception:
        return None

def recent_form_rate_team(df: pd.DataFrame, team: str) -> Optional[float]:
    try:
        if "FTR" not in df.columns:
            return None
        sub = df[(df.get("HomeTeam","")==team)|(df.get("AwayTeam","")==team)].tail(FORM_WINDOW)
        if sub.empty: return None
        wins = 0
        for _, row in sub.iterrows():
            if row.get("HomeTeam","")==team and row.get("FTR")== "H": wins+=1
            elif row.get("AwayTeam","")==team and row.get("FTR")== "A": wins+=1
        return 100.0*wins/len(sub)
    except Exception:
        return None

# ──────────────────────────────────────────────────────────────
# 📊 PROBABILITÀ DA CSV (per blending)
# ──────────────────────────────────────────────────────────────
def csv_prob_for_event(sport: str, hist_df: pd.DataFrame, home: str, away: str) -> Optional[float]:
    try:
        if sport.startswith("tennis_"):
            if {"player1","player2","winner"}.issubset(hist_df.columns):
                df = hist_df[(hist_df["player1"].isin([home,away]))|(hist_df["player2"].isin([home,away]))]
                if df.empty: return None
                home_win = (df["winner"]==home).sum()
                away_win = (df["winner"]==away).sum()
            elif {"winner_name","loser_name"}.issubset(hist_df.columns):
                df = hist_df[(hist_df["winner_name"].isin([home,away]))|(hist_df["loser_name"].isin([home,away]))]
                if df.empty: return None
                home_win = (df["winner_name"]==home).sum()
                away_win = (df["winner_name"]==away).sum()
            else:
                return None
            fh = recent_form_rate_tennis(hist_df, home) or 50
            fa = recent_form_rate_tennis(hist_df, away) or 50
            total = home_win + away_win + 1
            prob = 0.6*(home_win/total*100) + 0.25*fh + 0.15*(100-fa)
            return round(max(0,min(100,prob)),1)

        if {"HomeTeam","AwayTeam","FTR"}.issubset(hist_df.columns):
            df = hist_df[(hist_df["HomeTeam"].isin([home, away])) | (hist_df["AwayTeam"].isin([home, away]))].copy()
            if df.empty: return None

            h2h = df[((df["HomeTeam"]==home)&(df["AwayTeam"]==away)) | ((df["HomeTeam"]==away)&(df["AwayTeam"]==home))]
            fh = recent_form_rate_team(hist_df, home) or 50
            fa = recent_form_rate_team(hist_df, away) or 50

            home_wins = ((df["HomeTeam"]==home) & (df["FTR"]=="H")).sum()
            away_losses_as_away = ((df["AwayTeam"]==away) & (df["FTR"]=="H")).sum()
            total = max(1, len(df))

            base = (home_wins/total)*100
            anti_away = (1 - away_losses_as_away/total)*100

            h2h_bonus = 50
            if not h2h.empty:
                h2h_home = ((h2h["HomeTeam"]==home) & (h2h["FTR"]=="H")).sum() + ((h2h["AwayTeam"]==home) & (h2h["FTR"]=="A")).sum()
                h2h_rate = 100 * h2h_home / len(h2h)
                h2h_bonus = h2h_rate

            prob = 0.35*base + 0.15*anti_away + 0.25*fh + 0.15*(100-fa) + 0.10*h2h_bonus
            return round(min(100, max(0, prob)), 1)
    except Exception as e:
        logging.warning(f"CSV prob exception for {sport} {home} vs {away}: {e}")
        return None
    return None

# ──────────────────────────────────────────────────────────────
# 📉 VOLATILITÀ QUOTE (range percentuale tra bookmaker)
# ──────────────────────────────────────────────────────────────
def compute_market_volatility(bookmakers: List[Dict]) -> Dict[str, Dict[str, float]]:
    vol = {}
    for bk in bookmakers or []:
        for m in bk.get("markets", []):
            mkey = m.get("key","")
            for o in m.get("outcomes", []):
                name = o.get("name","")
                try:
                    price = float(o["price"])
                except Exception:
                    continue
                vol.setdefault(mkey, {}).setdefault(name, {"min": price, "max": price})
                vol[mkey][name]["min"] = min(vol[mkey][name]["min"], price)
                vol[mkey][name]["max"] = max(vol[mkey][name]["max"], price)
    out = {}
    for mkey, outcomes in vol.items():
        out[mkey] = {}
        for name, mm in outcomes.items():
            mn, mx = mm["min"], mm["max"]
            pct = 0.0 if mn <= 0 else (mx - mn) / mn
            out[mkey][name] = pct
    return out

# ──────────────────────────────────────────────────────────────
# 🧠 FEEDBACK / ELO STATE
# ──────────────────────────────────────────────────────────────
def load_feedback_state() -> Dict[str, float]:
    try:
        if os.path.exists(FEEDBACK_STATE):
            with open(FEEDBACK_STATE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_feedback_state(state: Dict[str, float]):
    try:
        with open(FEEDBACK_STATE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        logging.warning(f"⚠️ save_feedback_state: {e}")

# ──────────────────────────────────────────────────────────────
# (2) BLENDING ADATTIVO API/CSV/MODEL – pesi per sport
# ──────────────────────────────────────────────────────────────
def _get_blend_weights_for_sport(sport: str):
    """
    Restituisce (w_api, w_csv, w_model) in [0..1] che sommano ~1.
    Se assenti, default conservativo: API 0.5, CSV 0.4, MODEL 0.1
    """
    state = load_feedback_state()
    wk = state.get(f"blend_weights__{sport}")
    if isinstance(wk, list) and len(wk) == 3:
        return tuple(wk)
    return (0.5, 0.4, 0.1)

def _save_blend_weights_for_sport(sport: str, w_api: float, w_csv: float, w_model: float):
    state = load_feedback_state()
    state[f"blend_weights__{sport}"] = [round(w_api,3), round(w_csv,3), round(w_model,3)]
    save_feedback_state(state)

def blend_predict(prob_api: Optional[float], prob_csv: Optional[float], prob_model: Optional[float], sport: str) -> float:
    """
    Combina le probabilità (in %) pesate. Se una manca, ripesa le altre.
    """
    if prob_api is None and prob_csv is None and prob_model is None:
        return 0.0
    w_api, w_csv, w_model = _get_blend_weights_for_sport(sport)
    parts = []
    weights = []
    if prob_api is not None:   parts.append(prob_api); weights.append(w_api)
    if prob_csv is not None:   parts.append(prob_csv); weights.append(w_csv)
    if prob_model is not None: parts.append(prob_model); weights.append(w_model)
    sw = sum(weights) or 1.0
    val = sum(p * (w/sw) for p, w in zip(parts, weights))
    return float(max(0.0, min(100.0, val)))

# ──────────────────────────────────────────────────────────────
# (4) MODELLI SPORT-SPECIFICI → prob_model (semplici)
# ──────────────────────────────────────────────────────────────
def soccer_model_prob(home: str, away: str, hist_df: Optional[pd.DataFrame]) -> Optional[float]:
    try:
        fh = recent_form_rate_team(hist_df, home) if hist_df is not None else None
        fa = recent_form_rate_team(hist_df, away) if hist_df is not None else None
        fh = 50 if fh is None else fh
        fa = 50 if fa is None else fa
        diff = fh - fa
        prob_home = 50 + 0.25 * diff + 5.0  # bonus casa
        return max(0.0, min(100.0, prob_home))
    except Exception:
        return None

def tennis_model_prob(home: str, away: str, hist_df: Optional[pd.DataFrame]) -> Optional[float]:
    try:
        fh = recent_form_rate_tennis(hist_df, home) if hist_df is not None else None
        fa = recent_form_rate_tennis(hist_df, away) if hist_df is not None else None
        fh = 50 if fh is None else fh
        fa = 50 if fa is None else fa
        prob_home = 50 + 0.4 * (fh - fa)
        return max(0.0, min(100.0, prob_home))
    except Exception:
        return None

def basketball_model_prob(home: str, away: str, hist_df: Optional[pd.DataFrame]) -> Optional[float]:
    try:
        fh = recent_form_rate_team(hist_df, home) if hist_df is not None else None
        fa = recent_form_rate_team(hist_df, away) if hist_df is not None else None
        fh = 50 if fh is None else fh
        fa = 50 if fa is None else fa
        prob_home = 50 + 0.3 * (fh - fa) + 3.0
        return max(0.0, min(100.0, prob_home))
    except Exception:
        return None

def sport_model_predict(sport: str, home: str, away: str, hist_df: Optional[pd.DataFrame]) -> Optional[float]:
    if sport.startswith("soccer_"):      return soccer_model_prob(home, away, hist_df)
    if sport.startswith("tennis_"):      return tennis_model_prob(home, away, hist_df)
    if sport.startswith("basketball_"):  return basketball_model_prob(home, away, hist_df)
    return None

# ──────────────────────────────────────────────────────────────
# 🧮 KELLY (punto 7)
# ──────────────────────────────────────────────────────────────
def kelly_fraction(prob_percent: float, price: float) -> float:
    p = prob_percent / 100.0
    b = price - 1.0
    if b <= 0: return 0.0
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, min(KELLY_CAP, f))

# ──────────────────────────────────────────────────────────────
# 🧠 ELO + RISULTATI
# ──────────────────────────────────────────────────────────────
def elo_load():
    try:
        if os.path.exists(ELO_STATE_PATH):
            return json.load(open(ELO_STATE_PATH, "r", encoding="utf-8"))
    except: pass
    return {}

def elo_save(state):
    try:
        json.dump(state, open(ELO_STATE_PATH, "w", encoding="utf-8"))
    except: pass

def elo_get(state, key, default=1500):
    return float(state.get(key, default))

def elo_expected(Ra, Rb):
    return 1.0 / (1.0 + 10 ** ((Rb - Ra)/400.0))

def elo_update(Ra, Rb, outcome, K=24):
    Ea = elo_expected(Ra, Rb)
    Ra_new = Ra + K * (outcome - Ea)
    Rb_new = Rb + K * ((1-outcome) - (1-Ea))
    return Ra_new, Rb_new

def elo_prob(state, a, b):
    return elo_expected(elo_get(state, a), elo_get(state, b)) * 100.0

def update_results_with_scores():
    if not (FEEDBACK_ENABLED and os.path.exists(RESULTS_LOG_PATH)):
        return
    try:
        df = pd.read_csv(RESULTS_LOG_PATH, on_bad_lines="skip")
    except Exception as e:
        logging.warning(f"⚠️ Impossibile leggere {RESULTS_LOG_PATH}: {e}")
        return
    if df.empty or "outcome_result" not in df.columns:
        return

    updated = 0
    es = elo_load()
    for sport in df["sport"].dropna().unique():
        scores = get_scores(sport, days_from=5)
        if not scores:
            continue
        score_map = {s.get("id"): s for s in scores if isinstance(s, dict) and s.get("id")}
        rows_idx = df.index[df["sport"]==sport].tolist()
        for i in rows_idx:
            row = df.loc[i]
            if row.get("outcome_result") in ("W","L"):  # già valutato
                continue
            mid = row.get("match_id")
            sc = score_map.get(mid)
            if not sc or not sc.get("completed"):
                continue
            home_t = sc.get("home_team")
            away_t = sc.get("away_team")
            scores_list = sc.get("scores") or []
            try:
                h_score = next((int(x["score"]) for x in scores_list if x.get("name")==home_t), None)
                a_score = next((int(x["score"]) for x in scores_list if x.get("name")==away_t), None)
            except Exception:
                h_score = a_score = None
            outcome = row.get("outcome","")
            result = ""
            if h_score is not None and a_score is not None:
                if outcome.lower() in ("home","home team","1","home win"):
                    result = "W" if h_score > a_score else "L"
                    Ra, Rb = elo_get(es, home_t), elo_get(es, away_t)
                    Ra, Rb = elo_update(Ra, Rb, 1.0 if result=="W" else 0.0)
                    es[home_t], es[away_t] = Ra, Rb
                elif outcome.lower() in ("away","away team","2","away win"):
                    result = "W" if a_score > h_score else "L"
                    Ra, Rb = elo_get(es, home_t), elo_get(es, away_t)
                    Ra, Rb = elo_update(Ra, Rb, 0.0 if result=="W" else 1.0)
                    es[home_t], es[away_t] = Ra, Rb
                elif outcome.lower() in ("draw","x"):
                    result = "W" if h_score == a_score else "L"
                    Ra, Rb = elo_get(es, home_t), elo_get(es, away_t)
                    Ra, Rb = elo_update(Ra, Rb, 0.5)
                    es[home_t], es[away_t] = Ra, Rb
            if result:
                df.at[i,"outcome_result"] = result
                updated += 1

    if updated > 0:
        try:
            df.to_csv(RESULTS_LOG_PATH, index=False)
            elo_save(es)
            logging.info(f"✅ Aggiornati {updated} esiti in {RESULTS_LOG_PATH}.")
        except Exception as e:
            logging.warning(f"⚠️ Salvataggio risultati fallito: {e}")

# ──────────────────────────────────────────────────────────────
# (2) ADAPT BLEND WEIGHTS – ora usa grid-search se disponibili prob_api/csv/model
# ──────────────────────────────────────────────────────────────
def adapt_blend_weights():
    if not os.path.exists(RESULTS_LOG_PATH): return
    try:
        df = pd.read_csv(RESULTS_LOG_PATH)
    except Exception:
        return
    if df.empty or "outcome_result" not in df.columns:
        return

    state = load_feedback_state()
    for sport in df["sport"].dropna().unique():
        sub = df[df["sport"]==sport].tail(200).copy()
        if sub.empty: 
            continue

        # accuracy rolling
        acc = 0.0
        sub_eval = sub[sub["outcome_result"].isin(["W","L"])]
        if not sub_eval.empty:
            wins = (sub_eval["outcome_result"]=="W").sum()
            total = len(sub_eval)
            acc = wins/total if total else 0.0
            state[f"acc__{sport}"] = round(acc, 3)

        # se non abbiamo le 3 colonne, fallback al tuo schema legacy (varia peso API globale)
        if not {"prob_api","prob_csv","prob_model","price","outcome_result"}.issubset(sub.columns):
            current = float(state.get(sport, BLEND_API_DEFAULT))
            if acc >= 0.60:
                current = max(0.40, current - 0.05)
            else:
                current = min(0.85, current + 0.05)
            state[sport] = round(current, 2)
            continue

        # grid search su pesi che sommano a 1 (step 0.1)
        rows = sub_eval.to_dict("records")
        best_profit = -1e9
        best = _get_blend_weights_for_sport(sport)
        steps = [i/10.0 for i in range(0, 11)]
        for wa in steps:
            for wc in steps:
                wm = 1.0 - wa - wc
                if wm < 0: 
                    continue
                profit = 0.0
                for r in rows:
                    try:
                        p_api   = float(r["prob_api"])
                        p_csv   = float(r["prob_csv"])
                        p_model = float(r["prob_model"])
                        price   = float(r["price"])
                        outcome = r["outcome_result"]
                    except Exception:
                        continue
                    prob_final = wa*p_api + wc*p_csv + wm*p_model
                    # simulazione flat stake 1
                    profit += (price - 1.0) if outcome=="W" else -1.0
                if profit > best_profit:
                    best_profit = profit
                    best = (wa, wc, wm)
        _save_blend_weights_for_sport(sport, *best)

    save_feedback_state(state)

def get_sport_blend_api(sport: str) -> float:
    state = load_feedback_state()
    return float(state.get(sport, BLEND_API_DEFAULT))

# ──────────────────────────────────────────────────────────────
# 🌦️ METEO & 🩹 INFORTUNI CONTEXT
# ──────────────────────────────────────────────────────────────
def load_context_data():
    base = "/data"
    ctx = {"weather": {}, "injuries": {}}
    try:
        # Meteo
        wdir = os.path.join(base, "weather_cache")
        for f in glob.glob(os.path.join(wdir, "*_weather.json")):
            sport = os.path.basename(f).replace("_weather.json", "")
            with open(f, "r", encoding="utf-8") as fp:
                ctx["weather"][sport] = json.load(fp)
        # Infortuni
        idir = os.path.join(base, "injuries_cache")
        for f in glob.glob(os.path.join(idir, "*_injuries.json")):
            sport = os.path.basename(f).replace("_injuries.json", "")
            with open(f, "r", encoding="utf-8") as fp:
                ctx["injuries"][sport] = json.load(fp)
        total_weather_entries = sum(len(json.load(open(f"/data/weather_cache/{f}", encoding="utf-8"))) for f in os.listdir("/data/weather_cache") if f.endswith(".json"))
        logging.info(f"📊 Contesto aggiornato: {len(os.listdir('/data/weather_cache'))} sport meteo, {total_weather_entries} località totali, {len(injury_data)} infortuni")

    except Exception as e:
        logging.warning(f"⚠️ Context load fallito: {e}")
    return ctx

CONTEXT_DATA = load_context_data()

# ──────────────────────────────────────────────
# 🧮 ANALISI MATCH (+ filtri bookmaker minimi + blend + modelli + stake)
# ──────────────────────────────────────────────────────────────
def most_common_point(outcomes: List[Dict]) -> Optional[float]:
    pts = [o.get("point") for o in outcomes if o.get("point") is not None]
    if not pts:
        return None
    try:
        from statistics import multimode, median
        modes = multimode(pts)
        if len(modes) == 1:
            return modes[0]
        return float(median(pts))
    except Exception:
        avg = sum([float(p) for p in pts]) / len(pts)
        return round(avg*2)/2.0

def confidence_bucket(prob, vol, ev):
    # score 0..1
    score = (prob/100.0)*0.6 + (1.0 - min(1.0, vol))*0.25 + min(0.5, max(0.0, ev))/0.5*0.15
    if score >= 0.75: return "🟢 Alta"
    if score >= 0.60: return "🔵 Media"
    return "🟠 Bassa"

def analyze_matches(sport: str, matches: list, hist_df=None):
    pronostici, scartati = [], []
    now = datetime.datetime.now(datetime.timezone.utc)

    state_acc = load_feedback_state()
    recent_acc = float(state_acc.get(f"acc__{sport}", 0.55))

    logging.debug(f"[DEBUG] Inizio analisi per {sport}: {len(matches)} eventi ricevuti")

    for match in matches:
        try:
            ct = match.get("commence_time")
            if not ct:
                logging.debug(f"[DEBUG] {sport}: match senza commence_time")
                continue
            start_time = datetime.datetime.fromisoformat(ct.replace("Z","+00:00"))
            if not (now < start_time < now + datetime.timedelta(days=2)):
                logging.debug(f"[DEBUG] {sport}: {match.get('home_team')} vs {match.get('away_team')} fuori intervallo 48h")
                continue

            home = match.get("home_team","Home")
            away = match.get("away_team","Away")

            # (3) FILTRO: numero minimo bookmaker aggregati
            bookmakers = match.get("bookmakers", []) or []
            bk_count = len(bookmakers)
            min_bk = DEFAULT_MIN_BOOKMAKERS
            for prefix, req in MIN_BOOKMAKERS_BY_SPORT.items():
                if sport.startswith(prefix):
                   min_bk = req
                   break
                  
            if bk_count < min_bk:
                logging.debug(f"[DEBUG] {sport} | {home} vs {away} | insufficient bookmakers: {bk_count} < {min_bk}")
                scartati.append("insufficient_bookmakers")
                continue

            vol_map = compute_market_volatility(bookmakers)
            best_pick = None
            best_point  = None
            best_vol    = None
            best_ev     = None
            best_book   = None

            for bookmaker in bookmakers:
                bookmaker_name = bookmaker.get("title","Sconosciuto")
                for market in bookmaker.get("markets", []):
                    outcomes = market.get("outcomes", [])
                    if len(outcomes) < 2:
                        logging.debug(f"[DEBUG] {sport} | {home} vs {away} | mercato vuoto ({market.get('key')})")
                        continue

                    mkey = market.get("key","")

                    # Per calcio: 'totals' fissato a 2.5
                    if sport.startswith("soccer_") and mkey == "totals":
                        outcomes = [o for o in outcomes if str(o.get("point")) == "2.5"]
                        if not outcomes:
                            logging.debug(f"[DEBUG] {sport} | {home} vs {away} | nessuna linea 2.5 trovata per totals")
                            continue

                    # Per altri sport: seleziona linea principale (point)
                    line_point_to_show = None
                    if not sport.startswith("soccer_") and mkey == "totals":
                        main_point = most_common_point(outcomes)
                        if main_point is not None:
                            outcomes = [o for o in outcomes if o.get("point")==main_point]
                            line_point_to_show = main_point
                        if not outcomes:
                            logging.debug(f"[DEBUG] {sport} | {home} vs {away} | nessuna linea principale trovata ({mkey})")
                            continue

                    fair = fair_probs_from_outcomes(outcomes)
                    if not fair:
                        logging.debug(f"[DEBUG] {sport} | {home} vs {away} | fair odds vuote ({mkey})")
                        continue

                    for item in fair:
                        name = item["name"]
                        price = float(item["price"])
                        fair_p = float(item["fair_prob"])
                        point  = item.get("point", None)

                        vol_pct = vol_map.get(mkey, {}).get(name, 0.0)
                        if vol_pct > VOLATILITY_LIMIT:
                            logging.debug(f"[DEBUG] {sport} | {home} vs {away} | volatilità alta {vol_pct:.2f} > {VOLATILITY_LIMIT}")
                            continue

                        # p_api / p_csv / p_model
                        prob_api   = fair_p
                        prob_csv   = csv_prob_for_event(sport, hist_df, home, away) if hist_df is not None else None
                        prob_model = sport_model_predict(sport, home, away, hist_df)

                        # conf legacy per divergenze (mantengo la tua idea)
                        confidence_api = max(1e-6, 1.0 - min(1.0, vol_pct))
                        confidence_csv = 0.50 + 0.50*(recent_acc)

                        # blend moderno a 3 componenti
                        prob_blend = blend_predict(prob_api, prob_csv, prob_model, sport)

                        # se niente csv/model, manteniamo correzione legacy API/CSV
                        if prob_csv is not None and prob_model is None:
                            diff = abs(fair_p - prob_csv)
                            if diff >= DIVERGENZA_SOGLIA:
                                confidence_api *= 1.25
                            legacy = (confidence_api*fair_p + confidence_csv*prob_csv) / (confidence_api+confidence_csv)
                            prob_final = (prob_blend + legacy) / 2.0
                        else:
                            prob_final = prob_blend

                        prob_final *= sport_reliability_weight(sport)
                        prob_final = max(0.0, min(100.0, round(prob_final, 1)))

                        # 🔧 Infortuni (come nel tuo codice, con piccole cautele)
                        try:
                            idata = CONTEXT_DATA["injuries"].get(sport, [])
                            if idata:
                                team_injuries = {}
                                for dataset in idata:
                                    for record in dataset.get("response", []):
                                        team = record.get("team", {}).get("name")
                                        if not team:
                                            continue
                                        team_injuries[team] = team_injuries.get(team, 0) + 1

                                inj_home = team_injuries.get(home, 0)
                                inj_away = team_injuries.get(away, 0)
                                if inj_home > inj_away:
                                    penalty = min(10, inj_home - inj_away) * 0.5
                                    prob_final -= penalty
                                elif inj_away > inj_home:
                                    bonus = min(10, inj_away - inj_home) * 0.5
                                    prob_final += bonus
                        except Exception as e:
                            logging.debug(f"[DEBUG] injury correction skipped {sport}: {e}")

                        # Context Engine + AI correction (tuoi)
                        context_bonus = context_adjustment(sport, home, away)
                        prob_final = max(0, min(100, prob_final + context_bonus))
                        prob_final = ai_correction(prob_final, price)
                       # ⚽ Bonus/Malus standings + forma recente (solo per calcio)
                        prob_final = ai_correction(prob_final, price)

                        # ⚽ Bonus/Malus standings + forma recente (solo per calcio)
                        try:
                            if sport.startswith("soccer_"):
                                standings_path = "/data/injuries_cache/football_standings.json"
                                form_path = "/data/injuries_cache/football_recent_form.json"

                                bonus_malus = 0.0

                                # --- CLASSIFICA (motivazione)
                                if os.path.exists(standings_path):
                                    with open(standings_path, "r", encoding="utf-8") as f:
                                        standings_data = json.load(f)
                                    for dataset in standings_data:
                                        for league in dataset.get("response", []):
                                            for table in league.get("league", {}).get("standings", [[]])[0]:
                                                team_name = table.get("team", {}).get("name", "")
                                                rank = table.get("rank", 10)
                                                if team_name.lower() == home.lower():
                                                    if rank <= 3:       # top 3
                                                        bonus_malus += 2.0
                                                    elif rank >= 18:    # zona retrocessione
                                                        bonus_malus -= 2.0
                                                elif team_name.lower() == away.lower():
                                                    if rank <= 3:
                                                        bonus_malus -= 2.0
                                                    elif rank >= 18:
                                                        bonus_malus += 2.0

                                # --- FORMA RECENTE (ultime 5 partite)
                                if os.path.exists(form_path):
                                    with open(form_path, "r", encoding="utf-8") as f:
                                        form_data = json.load(f)
                                    for dataset in form_data:
                                        for matchset in dataset.get("response", []):
                                            team_home = matchset.get("teams", {}).get("home", {}).get("name", "")
                                            team_away = matchset.get("teams", {}).get("away", {}).get("name", "")
                                            winner = matchset.get("teams", {}).get("winner", None)

                                            if winner and team_home.lower() == home.lower():
                                                bonus_malus += 0.3
                                            elif winner and team_away.lower() == home.lower():
                                                bonus_malus -= 0.3
                                            if winner and team_home.lower() == away.lower():
                                                bonus_malus -= 0.3
                                            elif winner and team_away.lower() == away.lower():
                                                bonus_malus += 0.3

                                # Applica bonus/malus cumulativo limitato a ±5%
                                prob_final = max(0, min(100, prob_final + max(-5, min(5, bonus_malus))))
                        except Exception as e:
                            logging.debug(f"[DEBUG] bonus/malus standings-form skipped {sport}: {e}")


                        min_prob, min_quota = get_thresholds(sport)
                        ev = expected_value(prob_final, price)

                        if not (prob_final >= min_prob):
                            logging.debug(f"[DEBUG] {sport} | {home} vs {away} | prob {prob_final:.1f}% < soglia {min_prob}")
                            continue
                        if not (price >= min_quota):
                            logging.debug(f"[DEBUG] {sport} | {home} vs {away} | quota {price:.2f} < soglia {min_quota}")
                            continue
                        if ev > 0.75:
                            logging.debug(f"[DEBUG] {sport} | {home} vs {away} | EV {ev:.2f} > 0.75 (anomalo)")
                            continue

                        # (7) Stake consigliato (Kelly cappato)
                        f = kelly_fraction(prob_final, price)
                        suggested_stake = round(BANKROLL * f, 2)

                        logging.debug(f"[DEBUG] ✅ VALIDO {sport} | {home} vs {away} | {name} | prob={prob_final:.1f}% quota={price} ev={ev:.2f} stake={suggested_stake}")

                        cand = {
                            "name": name,
                            "market": mkey,
                            "price": price,
                            "prob_final": prob_final,
                            "prob_api": prob_api,
                            "prob_csv": prob_csv,
                            "prob_model": prob_model,
                            "ev": ev,
                            "stake": suggested_stake,
                            "point": line_point_to_show if line_point_to_show is not None else point,
                        }
                        if (best_pick is None) or (ev > (best_ev if best_ev is not None else -999)):
                            best_pick = cand
                            best_ev = ev
                            best_vol = vol_pct
                            best_book = bookmaker_name
                            best_point = cand["point"]

            if not best_pick:
                logging.debug(f"[DEBUG] {sport} | {home} vs {away} | nessun candidato valido dopo filtri")
                continue

            # Messaggio Telegram – con linea per sport ≠ calcio + stake
            point_line = ""
            if best_pick["market"] == "totals":
                if sport.startswith("soccer_"):
                    point_line = "\n📏 Linea: 2.5"
                else:
                    if best_point is not None:
                        point_line = f"\n📏 Linea: {best_point}"

            stake_line = f"\n💵 Stake suggerito: *{best_pick['stake']}€* (cap Kelly {int(KELLY_CAP*100)}%)" if best_pick["stake"] > 0 else ""

            msg = (
                f"*{SPORTS.get(sport, sport)}*\n"
                f"📌 *{home}* vs *{away}*\n"
                f"📅 {start_time.astimezone(TZ).strftime('%d/%m/%Y %H:%M')}\n"
                f"🏦 Bookmaker: {best_book}\n"
                f"🔮 Esito: *{best_pick['name']}* ({best_pick['market']}){point_line}\n"
                f"💰 Quota: *{best_pick['price']}*\n"
                f"📈 Probabilità: *{best_pick['prob_final']}%*{stake_line}\n"
            )

            badge = confidence_bucket(best_pick['prob_final'], best_vol or 0.0, best_ev or 0.0)
            msg += f"🛡️ Confidenza: {badge}"

            prediction_id = f"{sport}|{home}|{away}|{best_pick['market']}|{best_pick['name']}|{best_point}"
            if prediction_id in sent_predictions:
                logging.debug(f"[DEBUG] {sport} | {home} vs {away} | duplicato già inviato")
                continue
            sent_predictions.add(prediction_id); pred_save(sent_predictions)

            send_to_telegram("✅ *PRONOSTICO*\n\n" + msg)
            pronostici.append(best_pick)

            try:
                match_id = prediction_id
                date_str = start_time.strftime("%Y-%m-%d")
                # 🧾 LOG ESTESO con prob_api/csv/model/final + ev
                log_prediction(
                    date_str, sport, match_id, home, away,
                    best_pick["market"], best_pick["name"], best_pick["price"],
                    best_pick["prob_final"], best_point,
                    prob_api=best_pick["prob_api"],
                    prob_csv=best_pick["prob_csv"],
                    prob_model=best_pick["prob_model"],
                    ev=best_pick["ev"]
                )
            except Exception as e:
                logging.warning(f"⚠️ log_prediction failed: {e}")

        except Exception as e:
            scartati.append(f"❌ Errore parsing {sport}: {e}")
            logging.warning(f"[DEBUG] Errore match {sport}: {e}")

    logging.debug(f"[DEBUG] Fine analisi {sport} | trovati {len(pronostici)} validi, {len(scartati)} errori")
    return pronostici, scartati

# ──────────────────────────────────────────────────────────────
# 📦 BACKUP results_log.csv
# ──────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────
# 🧾 LOG PREDICTION (ESTESA)
# ──────────────────────────────────────────────────────────────
def log_prediction(date_str: str, sport: str, match_id: str, home: str, away: str,
                   market_key: str, outcome_name: str, price: float, prob_final: float, point: Optional[float],
                   prob_api: Optional[float]=None, prob_csv: Optional[float]=None,
                   prob_model: Optional[float]=None, ev: Optional[float]=None):
    """
    Scrive una riga nel file results_log.csv con tutti i dati utili per feedback e training.
    (VERSIONE ESTESA)
    """
    cols = [
        "timestamp","date","sport","match_id","home","away","market","outcome","price",
        "prob_api","prob_csv","prob_model","prob_final","ev","point","outcome_result"
    ]
    row = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "date": date_str,
        "sport": sport,
        "match_id": match_id,
        "home": home,
        "away": away,
        "market": market_key,
        "outcome": outcome_name,
        "price": price,
        "prob_api": None if prob_api is None else round(float(prob_api),2),
        "prob_csv": None if prob_csv is None else round(float(prob_csv),2),
        "prob_model": None if prob_model is None else round(float(prob_model),2),
        "prob_final": round(float(prob_final),2),
        "ev": None if ev is None else round(float(ev),3),
        "point": point if point is not None else "",
        "outcome_result": ""
    }
    try:
        if not os.path.exists(RESULTS_LOG_PATH):
            pd.DataFrame([row], columns=cols).to_csv(RESULTS_LOG_PATH, index=False)
        else:
            pd.DataFrame([row])[cols].to_csv(RESULTS_LOG_PATH, mode="a", header=False, index=False)
        logging.debug(f"📝 log_prediction salvato: {sport} {home}-{away}")
    except Exception as e:
        logging.warning(f"⚠️ log_prediction error: {e}")

# ──────────────────────────────────────────────────────────────
# 🔁 JOB PRINCIPALE
# ──────────────────────────────────────────────────────────────
historical_cache = {}

def get_hist(sport):
    if sport not in historical_cache:
        historical_cache[sport] = load_historical_data(sport)
    return historical_cache[sport]

def job():
    logging.info("🔍 Controllo nuove partite...")
       # 🔁 Ricarica dinamica del contesto (meteo / infortuni)
    try:
        global CONTEXT_DATA
        CONTEXT_DATA = load_context_data()
        logging.debug(f"[DEBUG] CONTEXT_DATA ricaricato: {len(CONTEXT_DATA.get('weather',{}))} sport meteo, {len(CONTEXT_DATA.get('injuries',{}))} infortuni")
    except Exception as e:
        logging.warning(f"⚠️ Impossibile ricaricare CONTEXT_DATA all'avvio del job: {e}")

    try:
        update_results_with_scores()
        adapt_blend_weights()
    except Exception as e:
        logging.warning(f"⚠️ feedback update skipped: {e}")

    tot_ok, tot_ko = 0, 0
    for sport in SPORTS.keys():
        hist_df = get_hist(sport)
        matches = fetch_odds(sport)
        accettati, rifiutati = analyze_matches(sport, matches, hist_df)
        # i messaggi vengono inviati direttamente in analyze_matches
        tot_ok += len(accettati)
        tot_ko += len(rifiutati)

    logging.info(f"📊 Pronostici (slot): {tot_ok} inviati | {tot_ko} scartati")

    # 🔁 Messaggio finale intelligente
    if tot_ok == 0:
        msg = "ℹ️ Nessun pronostico valido trovato in nessuno sport nelle prossime 48h."
        send_to_telegram(msg)
        logging.info(msg)
    else:
        msg = f"✅ Pronostici totali inviati: {tot_ok}"
        send_to_telegram(msg)
        logging.info(msg)

# ──────────────────────────────────────────────────────────────
# 📈 REPORT SETTIMANALE (domenica 21:00 IT)
# ──────────────────────────────────────────────────────────────
def weekly_report():
    if not os.path.exists(RESULTS_LOG_PATH):
        return
    try:
        df = pd.read_csv(RESULTS_LOG_PATH)
    except Exception:
        return
    if df.empty or "outcome_result" not in df.columns:
        return

    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)
    last7 = df[df["date"] >= week_ago.isoformat()].copy()
    if last7.empty:
        return

    def acc_of(s):
        s = s.dropna()
        if s.empty: return 0.0
        wins = (s=="W").sum()
        tot  = (s.isin(["W","L"])).sum()
        return 0.0 if tot==0 else wins/tot

    by_sport = last7.groupby("sport")["outcome_result"].apply(acc_of).sort_values(ascending=False)

    global_acc = acc_of(last7["outcome_result"])
    state = load_feedback_state()
    blend_avg = sum(float(state.get(s, BLEND_API_DEFAULT)) for s in SPORTS.keys()) / max(1, len(SPORTS))

    top_lines = "\n".join([f"• {SPORTS.get(k,k)}: {v*100:.1f}%" for k,v in by_sport.head(6).items()])
    trend_emoji = "🟢" if global_acc >= 0.60 else ("🟡" if global_acc >= 0.53 else "🔴")

    msg = (
        f"📊 *Report settimanale* ({(week_ago).strftime('%d/%m')}–{today.strftime('%d/%m')})\n"
        f"Tot pronostici: {len(last7)}\n"
        f"Accuracy 7d: *{global_acc*100:.1f}%* {trend_emoji}\n"
        f"Blend medio API: {blend_avg:.2f}\n\n"
        f"🏆 *Top sport:*\n{top_lines}"
    )
    send_to_telegram(msg)
# ──────────────────────────────────────────────────────────────
# 📊 REPORT GIORNALIERO AUTOMATICO (22:00 IT)
# ──────────────────────────────────────────────────────────────
def daily_report():
    try:
        if not os.path.exists(RESULTS_LOG_PATH):
            send_to_telegram("📊 Nessun dato disponibile per il report giornaliero.")
            return

        df = pd.read_csv(RESULTS_LOG_PATH, on_bad_lines="skip", engine="python")
        if df.empty or "outcome_result" not in df.columns:
            send_to_telegram("📊 Nessun pronostico registrato oggi.")
            return

        today = datetime.date.today().isoformat()

        # ✅ Considera SOLO i pronostici effettivamente INVIATI (incrocio con sent_predictions.json)
        sent_path = f"{DATA_DIR}/sent_predictions.json"
        sent_ids = set()
        if os.path.exists(sent_path):
            try:
                with open(sent_path, "r", encoding="utf-8") as f:
                    sent_ids = set(json.load(f))
            except Exception:
                pass

        # assicuriamoci che 'timestamp' esista e lo convertiamo in data (YYYY-MM-DD)
        if "timestamp" in df.columns:
            try:
                df["sent_date"] = pd.to_datetime(df["timestamp"], errors="coerce").dt.date.astype(str)
            except Exception:
                df["sent_date"] = ""
        else:
            # fallback: se non c'è timestamp, prova con la colonna 'date' (meno precisa)
            df["sent_date"] = df.get("date", "")

        # seleziona righe inviate oggi E i cui match_id (che ora sono prediction_id) sono fra i sent_ids
        df_today = df[
            (df["sent_date"] == today) &
            (df["match_id"].astype(str).isin(sent_ids))
        ]

        if df_today.empty:
            send_to_telegram(f"📊 Nessun pronostico inviato oggi ({today}).")
            return

        total = len(df_today)
        won = (df_today["outcome_result"] == "W").sum()
        lost = (df_today["outcome_result"] == "L").sum()
        acc = (won / total * 100) if total else 0.0
        avg_odds = round(df_today["price"].mean(), 2) if "price" in df_today.columns else 0.0

        # Profitto stimato flat stake 1
        profit = 0.0
        for _, row in df_today.iterrows():
            if row.get("outcome_result") == "W":
                profit += (row.get("price", 1.0) - 1.0)
            elif row.get("outcome_result") == "L":
                profit -= 1.0

        # Miglior/Peggior sport
        perf_by_sport = (
            df_today.groupby("sport")["outcome_result"]
            .apply(lambda x: (x == "W").mean() * 100)
            .sort_values(ascending=False)
        )
        best_sport = perf_by_sport.index[0] if not perf_by_sport.empty else "-"
        worst_sport = perf_by_sport.index[-1] if len(perf_by_sport) > 1 else "-"

        msg = (
            f"📊 *Report giornaliero* ({today})\n\n"
            f"Totale pronostici: *{total}*\n"
            f"✅ Vinti: *{won}* | ❌ Persi: *{lost}*\n"
            f"🎯 Accuracy: *{acc:.1f}%*\n"
            f"💰 Quota media: *{avg_odds}*\n"
            f"📈 Profitto stimato: *{profit:+.2f} unità*\n\n"
            f"🏆 Miglior sport: *{best_sport}*\n"
            f"⚠️ Peggiore: *{worst_sport}*"
        )

        send_to_telegram(msg)
        logging.info("✅ Report giornaliero inviato.")

    except Exception as e:
        logging.warning(f"⚠️ Errore report giornaliero: {e}")
        send_to_telegram(f"⚠️ Errore generazione report giornaliero: {e}")


# ──────────────────────────────────────────────────────────────
# 🕒 SCHEDULER Europe/Rome
# ──────────────────────────────────────────────────────────────
def start_scheduler():
    sched = BackgroundScheduler(timezone=TZ)
    # slot giornalieri
    for hhmm in SCHEDULE_TIMES:
        h, m = map(int, hhmm.split(":"))
        sched.add_job(job, "cron", hour=h, minute=m)
    # Aggiornamento giornaliero context
    sched.add_job(update_context_data, "cron", hour=4, minute=0)
    # Addestramento ML settimanale
    sched.add_job(train_model, "cron", day_of_week="sun", hour=3, minute=0)

    # Scheduler giornaliero
    sched.add_job(update_injuries, "cron", hour=8, minute=30)
    sched.add_job(update_weather, "cron", hour=8, minute=40)
    # report domenica 21:00
    sched.add_job(weekly_report, "cron", **WEEKLY_REPORT_TIME)
    # report giornaliero 22:00
    sched.add_job(daily_report, "cron", hour=22, minute=0)
    # backup giornaliero
    sched.add_job(backup_results_log, "cron", **DAILY_BACKUP_TIME)
    sched.add_job(update_results_with_scores, "cron", **DAILY_BACKUP_TIME)
       # pronostici statistici senza quota (CSV + API stats)
    sched.add_job(run_statistical_batch, "cron", hour=9,  minute=10)   # 09:10
    sched.add_job(run_statistical_batch, "cron", hour=19, minute=10)    # 19:10

    sched.start()
    return sched

# ──────────────────────────────────────────────────────────────
# 🚀 MAIN
# ──────────────────────────────────────────────────────────────
logging.getLogger().setLevel(logging.DEBUG)

if __name__ == "__main__":
    send_to_telegram("✅ Bot PRO v2 avviato (volatilità, blending dinamico, linea totals, report Domenica 21:00, backup 24h).")
    logging.info("🤖 Bot PRO v2 attivo. In attesa di invio pronostici...")
    # run immediato
    job()
    # avvia scheduler
    scheduler = start_scheduler()
    try:
        while True:
            time.sleep(30)
    except KeyboardInterrupt:
        scheduler.shutdown()
