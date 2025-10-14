# -*- coding: utf-8 -*-
"""
Pronostici statistici (senza quota) per:
- Calcio: 1st_half_result, 1st_half_over_1_5
- NHL:   1st_period_result
- NBA:   player_points, player_rebounds (con linea)

Fonti:
- CSV in /data/ (priorità)
- API opzionali:
  - API-Football (calcio) -> ENV: API_FOOTBALL_KEY (opzionale)
  - BallDontLie (NBA, free)
  - NHL Stats API (free)

Scrive su /data/results_log.csv (compatibile col bot) e invia su Telegram.
"""

import os, json, glob, logging, datetime, math, time
from typing import Optional, Dict, List, Tuple
import requests
import pandas as pd

# ─────────────────────────────────────────────────
# ENV & PATH
# ─────────────────────────────────────────────────
DATA_DIR = "/data"
RESULTS_LOG = f"{DATA_DIR}/results_log.csv"
SENT_PATH  = f"{DATA_DIR}/sent_predictions.json"

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ODDS_API_KEY     = os.getenv("ODDS_API_KEY", "")

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()  # opzionale

# Soglie invio (modificabili via ENV)
THRESH_SOCCER_HT_WIN   = float(os.getenv("THRESH_SOCCER_HT_WIN",   "0.60"))  # 60%
THRESH_SOCCER_HT_O15   = float(os.getenv("THRESH_SOCCER_HT_O15",   "0.68"))  # 68%
THRESH_NHL_P1_WIN      = float(os.getenv("THRESH_NHL_P1_WIN",      "0.58"))  # 58%
THRESH_NBA_POINTS      = float(os.getenv("THRESH_NBA_POINTS",      "0.70"))  # 70%
THRESH_NBA_REBOUNDS    = float(os.getenv("THRESH_NBA_REBOUNDS",    "0.70"))  # 70%

# Linee di default NBA (se non presenti nei CSV)
NBA_DEFAULT_POINTS_LINE   = float(os.getenv("NBA_DEFAULT_POINTS_LINE",   "20.5"))
NBA_DEFAULT_REBOUNDS_LINE = float(os.getenv("NBA_DEFAULT_REBOUNDS_LINE", "9.5"))

TZ = datetime.timezone(datetime.timedelta(hours=2))  # Europe/Rome semplificato

logging.getLogger().setLevel(logging.INFO)

# ─────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────
def _tg_escape(s: str) -> str:
    return (s.replace("\\","\\\\").replace("_","\\_").replace("*","\\*")
             .replace("[","\\[").replace("]","\\]").replace("(","\\(").replace(")","\\)")
             .replace("~","\\~").replace("`","\\`").replace(">","\\>").replace("#","\\#")
             .replace("+","\\+").replace("-","\\-").replace("=","\\=").replace("|","\\|")
             .replace("{","\\{").replace("}","\\}").replace(".","\\.").replace("!","\\!"))

def tg_send(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Telegram non configurato (TOKEN/CHAT_ID).")
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": _tg_escape(msg), "parse_mode": "MarkdownV2"},
                      timeout=12)
    except Exception as e:
        logging.error(f"Telegram error: {e}")

def _read_csv_smart(path: str) -> Optional[pd.DataFrame]:
    seps = [",",";","\t","|"]; encs=["utf-8","latin1","cp1252"]
    for enc in encs:
        for sep in seps:
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc)
                if df.shape[1]==1 and any(ch in str(df.columns[0]) for ch in [",",";","\t","|"]):
                    continue
                df.columns = [str(c).strip() for c in df.columns]
                return df
            except Exception:
                continue
    return None

def _concat(folder_glob: str) -> Optional[pd.DataFrame]:
    dfs=[]
    for p in glob.glob(folder_glob):
        df=_read_csv_smart(p)
        if df is not None and not df.empty:
            dfs.append(df)
    if not dfs: return None
    return pd.concat(dfs, ignore_index=True, sort=False)

def _append_log(row: Dict):
    cols=["timestamp","date","sport","match_id","home","away","market","outcome","price",
          "prob_api","prob_csv","prob_model","prob_final","ev","point","outcome_result"]
    df = pd.DataFrame([row], columns=cols)
    if not os.path.exists(RESULTS_LOG):
        df.to_csv(RESULTS_LOG, index=False)
    else:
        df.to_csv(RESULTS_LOG, mode="a", header=False, index=False)

def _sent_load() -> set:
    try:
        if os.path.exists(SENT_PATH):
            return set(json.load(open(SENT_PATH,"r",encoding="utf-8")))
    except: pass
    return set()

def _sent_save(s: set):
    try:
        json.dump(list(s), open(SENT_PATH,"w",encoding="utf-8"))
    except: pass

# Prossime partite (usiamo comunque The Odds API per calendario 48h)
def _upcoming(sport_key: str) -> List[Dict]:
    if not ODDS_API_KEY: return []
    url=f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params={"apiKey":ODDS_API_KEY,"regions":"eu","markets":"h2h","oddsFormat":"decimal","dateFormat":"iso"}
    try:
        r=requests.get(url, params=params, timeout=20); r.raise_for_status()
        data=r.json()
        now=datetime.datetime.now(datetime.timezone.utc)
        out=[]
        for ev in data:
            ct=ev.get("commence_time")
            if not ct: continue
            ts=datetime.datetime.fromisoformat(ct.replace("Z","+00:00"))
            if now < ts < (now+datetime.timedelta(days=2)):
                out.append(ev)
        return out
    except Exception as e:
        logging.warning(f"_upcoming {sport_key}: {e}")
        return []

# ─────────────────────────────────────────────────
# CALCIO – 1° TEMPO
# ─────────────────────────────────────────────────
def _soccer_load_hist() -> Optional[pd.DataFrame]:
    # es: /data/calcio/*.csv
    for folder in ["calcio","soccer","football"]:
        df=_concat(f"{DATA_DIR}/{folder}/*.csv")
        if df is not None: return df
    return None

def _soccer_ht_features(df: pd.DataFrame, team: str) -> Dict[str,float]:
    # prova a mappare colonne possibili (football-data.co.uk)
    cols = {c.lower(): c for c in df.columns}
    hthg=cols.get("hthg"); htag=cols.get("htag"); htr=cols.get("htr")
    hometeam=cols.get("hometeam") or cols.get("home") or "HomeTeam"
    awayteam=cols.get("awayteam") or cols.get("away") or "AwayTeam"

    sub = df[(df.get(hometeam,"")==team) | (df.get(awayteam,"")==team)].tail(20).copy()
    out={"lead_rate":0.5,"o15_rate":0.5}
    if sub.empty: return out

    if hthg and htag:
        sub["HT_TOTAL"] = pd.to_numeric(sub[hthg],errors="coerce").fillna(0) + \
                          pd.to_numeric(sub[htag],errors="coerce").fillna(0)
        # guida al 45’ per team
        lead=0
        for _,r in sub.iterrows():
            ht_home = r.get(hthg,0); ht_away = r.get(htag,0)
            is_home = (r.get(hometeam,"")==team)
            diff = (ht_home - ht_away) if is_home else (ht_away - ht_home)
            if diff>0: lead+=1
        out["lead_rate"]=lead/max(1,len(sub))
        out["o15_rate"]=(sub["HT_TOTAL"]>=2).mean()
        return out

    # fallback con HTR (H/A/D)
    if htr:
        lead=0; o15=0
        for _,r in sub.iterrows():
            res=str(r.get(htr,"")).upper()  # H/A/D
            if (r.get(hometeam,"")==team and res=="H") or (r.get(awayteam,"")==team and res=="A"):
                lead+=1
            # senza gol numerici non possiamo o15 con certezza -> usa media 0.45
        out["lead_rate"]=lead/max(1,len(sub))
        out["o15_rate"]=0.45
    return out

def _combine_probs(p_csv: Optional[float], p_api: Optional[float]) -> float:
    # combinazione semplice: se entrambe presenti -> media pesata (CSV 0.6, API 0.4)
    if p_csv is None and p_api is None: return 0.0
    if p_csv is None: return float(p_api)
    if p_api is None: return float(p_csv)
    return float(0.6*p_csv + 0.4*p_api)

def _soccer_api_ht(team_home: str, team_away: str) -> Tuple[Optional[float],Optional[float]]:
    """Se disponibile API-Football, stima HT-lead e HT over1.5 dagli ultimi 10 match (grezza)."""
    if not API_FOOTBALL_KEY: return (None,None)
    # Nota: qui mettiamo uno stub robusto (molti piani non danno half-time goal detail). Se non arriva, torna None.
    try:
        headers={"x-apisports-key": API_FOOTBALL_KEY}
        # Esempio: potresti usare /fixtures?team={id}&last=10&timezone=Europe/Rome
        # ma servono ID squadra; senza mapping certo, ritorniamo None (evitiamo falsi).
        return (None, None)
    except Exception:
        return (None, None)

def soccer_predictions():
    df=_soccer_load_hist()
    events=_upcoming("soccer_epl") + _upcoming("soccer_italy_serie_a") + _upcoming("soccer_italy_serie_b") + \
           _upcoming("soccer_france_ligue_one") + _upcoming("soccer_germany_bundesliga") + _upcoming("soccer_spain_la_liga")
    sent=_sent_load()
    out_count=0

    for ev in events:
        home=ev.get("home_team","Home"); away=ev.get("away_team","Away")
        mid = ev.get("id", f"SOCCER|{home}|{away}")
        # CSV features
        p_home_csv = _soccer_ht_features(df, home)["lead_rate"] if df is not None else 0.5
        p_away_csv = _soccer_ht_features(df, away)["lead_rate"] if df is not None else 0.5
        p_o15_csv  = 0.0
        if df is not None:
            fhome=_soccer_ht_features(df, home)["o15_rate"]
            faway=_soccer_ht_features(df, away)["o15_rate"]
            p_o15_csv = 0.5*(fhome+faway)

        # API (se disponibile)
        p_home_api, p_o15_api = _soccer_api_ht(home, away)

        # Combina
        p_home = _combine_probs(p_home_csv, p_home_api)
        p_away = _combine_probs(p_away_csv, None)  # niente API affidabile lato away qui
        p_draw = max(0.0, 1.0 - (p_home + p_away))  # normalizzazione semplice
        # ribilancia per evitare <0
        tot = p_home + p_away + p_draw
        if tot>0:
            p_home, p_away, p_draw = p_home/tot, p_away/tot, p_draw/tot

        p_o15  = _combine_probs(p_o15_csv, p_o15_api)

        # invii
        # 1) Vincitore 1° Tempo
        pick_name, pick_prob = None, 0.0
        if p_home>=THRESH_SOCCER_HT_WIN:
            pick_name, pick_prob = ("Home HT", p_home)
        elif p_away>=THRESH_SOCCER_HT_WIN:
            pick_name, pick_prob = ("Away HT", p_away)
        elif p_draw>=THRESH_SOCCER_HT_WIN:
            pick_name, pick_prob = ("Draw HT", p_draw)

        def _send_row(market, outcome, prob, point=None):
            # evita duplicati
            pid=f"{mid}|{market}|{outcome}|{point or ''}"
            if pid in sent: return False
            # messaggio
            ts = datetime.datetime.fromisoformat(ev["commence_time"].replace("Z","+00:00")).astimezone(TZ)
            msg=(f"*⚽ Calcio — {home} vs {away}*\n"
                 f"🕒 {ts.strftime('%d/%m/%Y %H:%M')}\n"
                 f"🔮 Esito: *{outcome}* ({market})\n"
                 f"📈 Probabilità: *{prob*100:.1f}%*")
            tg_send(msg)
            # log
            row={
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "date": ts.strftime("%Y-%m-%d"),
                "sport": ev.get("sport_key","soccer_generic"),
                "match_id": mid,
                "home": home, "away": away,
                "market": market, "outcome": outcome,
                "price": "", "prob_api": "", "prob_csv": round(prob*100,2),
                "prob_model": "", "prob_final": round(prob*100,2),
                "ev": "", "point": point or "", "outcome_result": ""
            }
            _append_log(row)
            sent.add(pid); _sent_save(sent)
            return True

        if pick_name:
            if _send_row("1st_half_result", pick_name, pick_prob):
                out_count += 1

        # 2) Over 1.5 1° Tempo
        if p_o15 >= THRESH_SOCCER_HT_O15:
            if _send_row("1st_half_over_1_5", "Over 1.5 HT", p_o15):
                out_count += 1

    logging.info(f"[soccer_predictions] inviati: {out_count}")

# ─────────────────────────────────────────────────
# NHL – 1° PERIODO
# ─────────────────────────────────────────────────
def _nhl_load_hist() -> Optional[pd.DataFrame]:
    for folder in ["hockey","nhl","icehockey"]:
        df=_concat(f"{DATA_DIR}/{folder}/*.csv")
        if df is not None: return df
    return None

def _nhl_p1_rate(df: pd.DataFrame, team: str) -> float:
    """
    Prova diverse colonne per ricavare vantaggio fine 1° periodo:
    - 'P1H','P1A' o 'home_p1_goals','away_p1_goals'
    - fallback: se non ci sono, usa 0.5
    """
    if df is None or df.empty: return 0.5
    cols = {c.lower(): c for c in df.columns}
    p1h = cols.get("p1h") or cols.get("home_p1_goals")
    p1a = cols.get("p1a") or cols.get("away_p1_goals")
    hometeam = cols.get("hometeam") or cols.get("home_team") or "home_team"
    awayteam = cols.get("awayteam") or cols.get("away_team") or "away_team"
    sub = df[(df.get(hometeam,"")==team)|(df.get(awayteam,"")==team)].tail(20).copy()
    if sub.empty or not (p1h and p1a): return 0.5
    lead=0
    for _,r in sub.iterrows():
        is_home = (r.get(hometeam,"")==team)
        h = pd.to_numeric(r.get(p1h,0), errors="coerce"); a = pd.to_numeric(r.get(p1a,0), errors="coerce")
        diff = (h-a) if is_home else (a-h)
        if diff>0: lead+=1
    return lead/max(1,len(sub))

def nhl_predictions():
    df=_nhl_load_hist()
    events=_upcoming("icehockey_nhl")
    sent=_sent_load()
    sent_n=0

    for ev in events:
        home=ev.get("home_team","Home"); away=ev.get("away_team","Away")
        mid = ev.get("id", f"NHL|{home}|{away}")
        p_home = _nhl_p1_rate(df, home)
        p_away = _nhl_p1_rate(df, away)
        # normalizza
        tot=p_home+p_away
        if tot>0: p_home, p_away = p_home/tot, p_away/tot

        pick=None; p=0.0
        if p_home>=THRESH_NHL_P1_WIN: pick, p=("Home P1", p_home)
        elif p_away>=THRESH_NHL_P1_WIN: pick, p=("Away P1", p_away)
        else:
            continue

        pid=f"{mid}|1st_period_result|{pick}"
        if pid in sent: continue

        ts=datetime.datetime.fromisoformat(ev["commence_time"].replace("Z","+00:00")).astimezone(TZ)
        msg=(f"*🏒 NHL — {home} vs {away}*\n"
             f"🕒 {ts.strftime('%d/%m/%Y %H:%M')}\n"
             f"🔮 Esito: *{pick}* (1st\\_period\\_result)\n"
             f"📈 Probabilità: *{p*100:.1f}%*")
        tg_send(msg)

        row={"timestamp": datetime.datetime.utcnow().isoformat(),"date": ts.strftime("%Y-%m-%d"),
             "sport": "icehockey_nhl","match_id": mid,"home": home,"away": away,
             "market": "1st_period_result","outcome": pick,"price": "",
             "prob_api": "","prob_csv": round(p*100,2),"prob_model": "",
             "prob_final": round(p*100,2),"ev": "","point": "","outcome_result": ""}
        _append_log(row)
        sent.add(pid); _sent_save(sent); sent_n+=1

    logging.info(f"[nhl_predictions] inviati: {sent_n}")

# ─────────────────────────────────────────────────
# NBA – PLAYER MARKETS (punti/rimbalzi)
# ─────────────────────────────────────────────────
def _nba_load_hist() -> Optional[pd.DataFrame]:
    for folder in ["basket","nba","basketball"]:
        df=_concat(f"{DATA_DIR}/{folder}/*.csv")
        if df is not None: return df
    return None

def _bdl_player_id(name: str) -> Optional[int]:
    """BallDontLie v2: cerca player id (best effort)."""
    try:
        r=requests.get("https://api.balldontlie.io/v1/players", params={"search": name, "per_page": 1}, timeout=15)
        if r.status_code!=200: return None
        data=r.json().get("data",[])
        if not data: return None
        return data[0].get("id")
    except: return None

def _bdl_player_recent_avg(pid: int, last_n=10) -> Tuple[Optional[float],Optional[float]]:
    """Ritorna (pts, reb) medie ultime N gare."""
    try:
        r=requests.get("https://api.balldontlie.io/v1/season_averages", params={"player_ids[]": pid}, timeout=15)
        if r.status_code==200 and r.json().get("data"):
            d=r.json()["data"][0]
            return d.get("pts"), d.get("reb")
        # fallback: ultime X gare (se necessario)
        r=requests.get("https://api.balldontlie.io/v1/stats", params={"player_ids[]": pid, "per_page": last_n}, timeout=15)
        if r.status_code!=200: return (None,None)
        data=r.json().get("data",[])
        if not data: return (None,None)
        pts = sum([x.get("pts",0) for x in data])/len(data)
        reb = sum([x.get("reb",0) for x in data])/len(data)
        return (pts, reb)
    except: return (None,None)

def _nba_csv_line(df: pd.DataFrame, player: str, kind: str) -> Optional[float]:
    """
    Cerca nei CSV eventuali colonne linea (es: 'points_line','rebounds_line','line_points','line_rebounds').
    """
    if df is None or df.empty: return None
    cols = {c.lower(): c for c in df.columns}
    pname = cols.get("player") or cols.get("player_name") or cols.get("giocatore")
    if not pname: return None
    line_cols_pts = [cols.get("points_line"), cols.get("line_points")]
    line_cols_reb = [cols.get("rebounds_line"), cols.get("line_rebounds")]
    sub = df[df[pname].str.lower()==player.lower()].tail(1)
    if sub.empty: return None
    if kind=="points":
        for c in line_cols_pts:
            if c and c in sub.columns:
                try: return float(sub[c].iloc[0])
                except: pass
        return None
    if kind=="rebounds":
        for c in line_cols_reb:
            if c and c in sub.columns:
                try: return float(sub[c].iloc[0])
                except: pass
        return None
    return None

def _bayes_rate(mean_val: float, line: float, sigma: float=5.0) -> float:
    """
    Stima P(X >= line) assumendo normale (grezza). sigma default 5 (robusto per punti),
    per rimbalzi puoi raffinare via ENV se vuoi.
    """
    if mean_val is None or line is None: return 0.5
    # Z = (line - mean)/sigma
    z = (line - mean_val)/max(1e-6, sigma)
    # P(X >= line) = 1 - Phi(z)
    # approx Phi via erfc
    import math
    phi = 0.5*(1.0 + math.erf(-z/math.sqrt(2)))
    return max(0.0, min(1.0, phi))

def nba_predictions(players_watchlist: Optional[List[str]]=None):
    """
    players_watchlist: lista opzionale di giocatori su cui calcolare le props.
    Se None, prova a inferire dai CSV ultimi 100 record.
    """
    df=_nba_load_hist()
    sent=_sent_load()
    sent_n=0

    # scegliamo i giocatori: da watchlist o ultimi del CSV
    targets=set()
    if players_watchlist:
        targets.update(players_watchlist)
    elif df is not None and not df.empty:
        cname = None
        for k in ["player","player_name","giocatore"]:
            if k in [c.lower() for c in df.columns]:
                cname = [c for c in df.columns if c.lower()==k][0]
                break
        if cname:
            last=df.tail(200)[cname].dropna().unique().tolist()
            targets.update([str(x) for x in last][:25])  # limita

    for player in list(targets)[:25]:
        # linee da CSV o default
        line_pts = _nba_csv_line(df, player, "points") or NBA_DEFAULT_POINTS_LINE
        line_reb = _nba_csv_line(df, player, "rebounds") or NBA_DEFAULT_REBOUNDS_LINE

        # medie da BallDontLie (API free)
        pid=_bdl_player_id(player)
        avg_pts=avg_reb=None
        if pid:
            avg_pts, avg_reb = _bdl_player_recent_avg(pid)

        # fallback: medie dal CSV (se presenti)
        if (avg_pts is None or avg_reb is None) and df is not None:
            cols={c.lower():c for c in df.columns}
            pname = cols.get("player") or cols.get("player_name") or cols.get("giocatore")
            ppts  = cols.get("pts") or cols.get("points")
            preb  = cols.get("reb") or cols.get("rebounds")
            if pname and (ppts or preb):
                sub=df[df[pname].str.lower()==player.lower()].tail(20)
                if not sub.empty:
                    if avg_pts is None and ppts: avg_pts=float(pd.to_numeric(sub[ppts], errors="coerce").mean())
                    if avg_reb is None and preb: avg_reb=float(pd.to_numeric(sub[preb], errors="coerce").mean())

        # Probabilità (normale grezza)
        p_pts = _bayes_rate(avg_pts, line_pts, sigma=6.0)
        p_reb = _bayes_rate(avg_reb, line_reb, sigma=3.0)

        # invii
        def _send_player(market, outcome, prob, line_val):
            pid_key=f"NBA|{player}|{market}|{line_val}"
            if pid_key in sent: return False
            msg=(f"*🏀 NBA — {player}*\n"
                 f"🔮 Esito: *{outcome}* ({market})\n"
                 f"📏 Linea: {line_val}\n"
                 f"📈 Probabilità: *{prob*100:.1f}%*")
            tg_send(msg)
            row={"timestamp": datetime.datetime.utcnow().isoformat(),"date": datetime.date.today().isoformat(),
                 "sport": "basketball_nba","match_id": pid_key,"home": "","away": "",
                 "market": market,"outcome": outcome,"price": "",
                 "prob_api": "","prob_csv": round(prob*100,2),"prob_model": "",
                 "prob_final": round(prob*100,2),"ev": "","point": line_val,"outcome_result": ""}
            _append_log(row)
            sent.add(pid_key); _sent_save(sent)
            return True

        if p_pts >= THRESH_NBA_POINTS:
            if _send_player("player_points", f"{player} Over {line_pts}", p_pts, line_pts):
                sent_n+=1
        if p_reb >= THRESH_NBA_REBOUNDS:
            if _send_player("player_rebounds", f"{player} Over {line_reb}", p_reb, line_reb):
                sent_n+=1

    logging.info(f"[nba_predictions] inviati: {sent_n}")

# ─────────────────────────────────────────────────
# ENTRYPOINT BATCH
# ─────────────────────────────────────────────────
def run_statistical_batch():
    try:
        soccer_predictions()
    except Exception as e:
        logging.warning(f"soccer_predictions error: {e}")
    try:
        nhl_predictions()
    except Exception as e:
        logging.warning(f"nhl_predictions error: {e}")
    try:
        # Se vuoi limitare a una watchlist, passa un array di nomi
        nba_predictions(players_watchlist=None)
    except Exception as e:
        logging.warning(f"nba_predictions error: {e}")
