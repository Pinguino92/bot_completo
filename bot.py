#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BOT V2 – Versione ottimizzata e più accurata per pronostici sportivi.

Migliorie:
- Calcolo “fair odds” corretto per margine bookmaker
- Filtro su valore atteso (Expected Value, EV)
- Blending dinamico tra API e CSV in base alla coerenza
- Analisi forma recente (ultimi 10 match)
- Lettura CSV robusta e compatibile con schemi diversi
- Orari italiani 09:00, 13:00, 19:00
- Telegram + Render completamente supportati
"""

import os
import time
import logging
import requests
import datetime
import schedule
import pandas as pd
import glob
from typing import Optional, List, Dict

# 🔑 Variabili ambiente
ODDS_API_KEY     = os.getenv("ODDS_API_KEY")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ⚙️ Parametri configurabili
MIN_PROB_BASE = float(os.getenv("MIN_PROB_BASE", "60"))   # % base minima
MIN_QUOTA     = float(os.getenv("MIN_QUOTA", "1.50"))     # quota minima
MIN_EV        = float(os.getenv("MIN_EV", "0.05"))        # valore atteso minimo (+5%)
FORM_WINDOW   = int(os.getenv("FORM_WINDOW", "10"))       # ultime 10 partite
DIVERGENZA_SOGLIA = float(os.getenv("DIVERGENZA_SOGLIA", "15.0"))
BLEND_API_DEFAULT = float(os.getenv("BLEND_API_DEFAULT", "0.6"))

sent_predictions = set()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# ⚽️ Sport da analizzare
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
    "americanfootball_ncaaf": "🏈 NCAA Football",
    "baseball_mlb": "⚾ MLB - Baseball",
    "icehockey_nhl": "🏒 NHL - Hockey",
    "tennis_atp_shanghai_masters": "🎾 ATP Shanghai Masters",
}

# ------------------------------------------------------------
# 📂 LETTURA CSV STORICI
# ------------------------------------------------------------
def _category_for_sport(sport_key: str) -> str:
    if sport_key.startswith("soccer_"): return "calcio"
    if sport_key.startswith("basketball_"): return "basket"
    if sport_key.startswith("americanfootball_"): return "football"
    if sport_key.startswith("icehockey_"): return "hockey"
    if sport_key.startswith("baseball_"): return "baseball"
    if sport_key.startswith("tennis_"): return "tennis"
    return "misc"

def read_csv_smart(path: str) -> Optional[pd.DataFrame]:
    """Lettura robusta multi-separatore/multi-encoding."""
    seps = [",", ";", "\t", "|"]
    encs = ["utf-8", "latin1", "cp1252"]
    for enc in encs:
        for sep in seps:
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc)
                if df.shape[1] == 1 and any(ch in str(df.columns[0]) for ch in [",",";","\t","|"]):
                    continue
                df.columns = [c.strip() for c in df.columns]
                return df
            except Exception:
                continue
    return None

def load_historical_data(sport_key: str) -> Optional[pd.DataFrame]:
    categoria = _category_for_sport(sport_key)
    paths = []
    for base in ["data", "downloads", "external_data"]:
        paths.extend(glob.glob(os.path.join(base, categoria, "*.csv")))
    if not paths:
        logging.info(f"ℹ️ Nessun CSV trovato per {sport_key}.")
        return None

    dfs = []
    for p in paths:
        df = read_csv_smart(p)
        if df is not None and not df.empty:
            dfs.append(df)
        else:
            logging.warning(f"⚠️ Errore lettura {p}")
    if not dfs: return None
    full = pd.concat(dfs, ignore_index=True, sort=False)
    logging.info(f"📂 Storici caricati per {sport_key}: {len(paths)} file, {len(full)} righe.")
    return full

# ------------------------------------------------------------
# 🎯 PARAMETRI SOGLIA SPORT
# ------------------------------------------------------------
SPORT_THRESHOLDS = {
    "soccer_": {"prob": 60.0, "quota": 1.35},
    "basketball_": {"prob": 62.0, "quota": 1.40},
    "americanfootball_nfl": {"prob": 65.0, "quota": 1.50},
    "americanfootball_ncaaf": {"prob": 65.0, "quota": 1.50},
    "baseball_mlb": {"prob": 66.0, "quota": 1.55},
    "icehockey_nhl": {"prob": 70.0, "quota": 1.35},
    "tennis_atp_shanghai_masters": {"prob": 72.0, "quota": 1.35},
}

def get_thresholds(sport_key: str):
    for exact in ("americanfootball_nfl","americanfootball_ncaaf","baseball_mlb","icehockey_nhl","tennis_atp_shanghai_masters"):
        if sport_key == exact:
            t = SPORT_THRESHOLDS[exact]
            return t["prob"], max(t["quota"], MIN_QUOTA)
    if sport_key.startswith("soccer_"):
        t = SPORT_THRESHOLDS["soccer_"]; return t["prob"], max(t["quota"], MIN_QUOTA)
    if sport_key.startswith("basketball_"):
        t = SPORT_THRESHOLDS["basketball_"]; return t["prob"], max(t["quota"], MIN_QUOTA)
    return MIN_PROB_BASE, MIN_QUOTA

# ------------------------------------------------------------
# ✉️ TELEGRAM
# ------------------------------------------------------------
def send_to_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("⚠️ TELEGRAM_TOKEN o TELEGRAM_CHAT_ID mancanti.")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=10
        )
        if r.status_code != 200:
            logging.error(f"Errore Telegram: {r.text}")
    except Exception as e:
        logging.error(f"Errore Telegram: {e}")

# ------------------------------------------------------------
# 📊 FAIR ODDS & EXPECTED VALUE
# ------------------------------------------------------------
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
    if inv_sum <= 0: return fair_list
    for o, price, inv in vals:
        fair_p = (inv / inv_sum) * 100.0
        fair_list.append({"name": o.get("name",""), "price": price, "fair_prob": round(fair_p, 2)})
    return fair_list

def expected_value(prob_percent: float, price: float) -> float:
    return (prob_percent/100.0) * price - 1.0

# ------------------------------------------------------------
# 🔍 FORMA RECENTE
# ------------------------------------------------------------
def recent_form_rate_tennis(df: pd.DataFrame, player: str) -> Optional[float]:
    try:
        if {"player1","player2","winner"}.issubset(set(df.columns)):
            sub = df[(df["player1"] == player) | (df["player2"] == player)].tail(FORM_WINDOW)
            if sub.empty: return None
            return 100 * (sub["winner"] == player).sum() / len(sub)
        elif {"winner_name","loser_name"}.issubset(set(df.columns)):
            sub = df[(df["winner_name"] == player) | (df["loser_name"] == player)].tail(FORM_WINDOW)
            if sub.empty: return None
            return 100 * (sub["winner_name"] == player).sum() / len(sub)
        return None
    except Exception:
        return None

def recent_form_rate_team(df: pd.DataFrame, team: str) -> Optional[float]:
    try:
        sub = df[(df.get("HomeTeam","") == team) | (df.get("AwayTeam","") == team)].tail(FORM_WINDOW)
        if sub.empty: return None
        wins = 0
        for _, row in sub.iterrows():
            if "FTR" in row:
                if row.get("HomeTeam","") == team and row["FTR"] == "H": wins += 1
                elif row.get("AwayTeam","") == team and row["FTR"] == "A": wins += 1
        return 100 * wins / len(sub)
    except Exception:
        return None

# ------------------------------------------------------------
# 🧮 CALCOLO CSV PROBABILITÀ
# ------------------------------------------------------------
def csv_prob_for_event(sport: str, hist_df: pd.DataFrame, home: str, away: str) -> Optional[float]:
    try:
        if sport.startswith("tennis_"):
            if {"player1","player2","winner"}.issubset(set(hist_df.columns)):
                df = hist_df[(hist_df["player1"].isin([home,away])) | (hist_df["player2"].isin([home,away]))]
                if df.empty: return None
                home_win = (df["winner"] == home).sum()
                away_win = (df["winner"] == away).sum()
            elif {"winner_name","loser_name"}.issubset(set(hist_df.columns)):
                df = hist_df[(hist_df["winner_name"].isin([home,away])) | (hist_df["loser_name"].isin([home,away]))]
                if df.empty: return None
                home_win = (df["winner_name"] == home).sum()
                away_win = (df["winner_name"] == away).sum()
            else:
                return None
            fh = recent_form_rate_tennis(hist_df, home) or 50
            fa = recent_form_rate_tennis(hist_df, away) or 50
            prob = 0.6*(home_win/(home_win+away_win+1)*100) + 0.25*fh + 0.15*(100-fa)
            return round(prob,1)

        if {"HomeTeam","AwayTeam","FTR"}.issubset(set(hist_df.columns)):
            df = hist_df[(hist_df["HomeTeam"] == home) | (hist_df["AwayTeam"] == away)]
            if df.empty: return None
            home_wins = len(df[(df["HomeTeam"] == home) & (df["FTR"] == "H")])
            away_wins = len(df[(df["AwayTeam"] == away) & (df["FTR"] == "A")])
            fh = recent_form_rate_team(hist_df, home) or 50
            fa = recent_form_rate_team(hist_df, away) or 50
            return round(0.4*home_wins + 0.2*(100-away_wins) + 0.2*fh + 0.2*(100-fa),1)
    except Exception:
        return None
    return None

# ------------------------------------------------------------
# 🤖 ANALISI MATCH
# ------------------------------------------------------------
def analyze_matches(sport: str, matches: list, hist_df=None):
    pronostici, scartati = [], []
    now = datetime.datetime.now(datetime.timezone.utc)

    for match in matches:
        try:
            ct = match.get("commence_time")
            if not ct: continue
            start_time = datetime.datetime.fromisoformat(ct.replace("Z", "+00:00"))
            if not (now < start_time < now + datetime.timedelta(days=2)): continue

            home = match.get("home_team", "Home")
            away = match.get("away_team", "Away")

            for bookmaker in match.get("bookmakers", []):
                bookmaker_name = bookmaker.get("title", "Sconosciuto")
                for market in bookmaker.get("markets", []):
                    outcomes = market.get("outcomes", [])
                    if len(outcomes) < 2: continue

                    fair = fair_probs_from_outcomes(outcomes)
                    if not fair: continue

                    best = None
                    for o in fair:
                        prob_api = o["fair_prob"]
                        quota = float(o["price"])
                        prob_csv = csv_prob_for_event(sport, hist_df, home, away) if hist_df is not None else None
                        if prob_csv is not None:
                            diff = abs(prob_api - prob_csv)
                            w_api = BLEND_API_DEFAULT if diff < DIVERGENZA_SOGLIA else min(0.9, BLEND_API_DEFAULT + 0.2)
                            w_csv = 1 - w_api
                            prob_final = round(prob_api*w_api + prob_csv*w_csv,1)
                        else:
                            prob_final = prob_api
                        EV = expected_value(prob_final, quota)
                        cand = {"name":o["name"],"prob_final":prob_final,"prob_api":prob_api,"price":quota,"EV":EV}
                        if best is None or cand["EV"] > best["EV"]: best = cand
                    if not best: continue

                    min_prob, min_quota = get_thresholds(sport)
                    ok = (best["prob_final"] >= min_prob and best["price"] >= min_quota and best["EV"] >= MIN_EV)
                    msg = (
                        f"{SPORTS.get(sport, sport)}\n"
                        f"📌 {home} vs {away}\n"
                        f"🏦 Bookmaker: {bookmaker_name}\n"
                        f"🔮 Esito: {best['name']}\n"
                        f"💰 Quota: {best['price']}\n"
                        f"📈 Probabilità finale: {best['prob_final']}%\n"
                        f"💎 EV: {round(best['EV']*100,1)}%"
                    )
                    pid = f"{sport}{home}{away}{best['name']}"
                    if pid not in sent_predictions:
                        sent_predictions.add(pid)
                        if ok: pronostici.append("✅ PRONOSTICO\n\n"+msg)
                        else: scartati.append("❌ SCARTATO\n\n"+msg)
        except Exception as e:
            scartati.append(f"❌ Errore parsing {sport}: {e}")
    return pronostici, scartati

# ------------------------------------------------------------
# 🔁 JOB PRINCIPALE
# ------------------------------------------------------------
def job():
    logging.info("🔍 Controllo nuove partite...")
    tot_ok, tot_ko = 0, 0
    for sport in SPORTS.keys():
        hist_df = load_historical_data(sport)
        matches = get_odds(sport)
        accettati, rifiutati = analyze_matches(sport, matches, hist_df)
        for msg in accettati: send_to_telegram(msg)
        tot_ok += len(accettati); tot_ko += len(rifiutati)
    logging.info(f"📊 Pronostici inviati: {tot_ok} | Scartati: {tot_ko}")
    if tot_ok == 0:
        send_to_telegram("ℹ️ Nessun match con valore entro 48h.")

# ------------------------------------------------------------
# 🕒 SCHEDULAZIONE
# ------------------------------------------------------------
schedule_times = ["09:00", "13:00", "19:00"]
for t in schedule_times:
    schedule.every().day.at(t).do(job)

if __name__ == "__main__":
    send_to_telegram("✅ Bot avviato (versione ottimizzata, alta accuratezza).")
    logging.info("🤖 Bot attivo e in attesa di invio pronostici...")
    job()
    while True:
        schedule.run_pending()
        time.sleep(30)
