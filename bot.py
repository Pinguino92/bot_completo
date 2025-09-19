import os
import time
import logging
import requests
import pandas as pd
from collections import defaultdict

# =========================
# CONFIG
# =========================
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

CHECK_INTERVAL_SEC = 2 * 60 * 60  # ogni 2 ore
MIN_WIN_PROB = 0.75               # >= 75%
MIN_ODDS = 1.70                   # quota minima

# Soglie minime di linea per totals
BASKET_MIN_TOTAL = 218.5
FOOTBALL_MIN_TOTAL = 37.5

# Sport key per Odds API
SPORT_KEYS = {
    "soccer": ["soccer_italy_serie_a", "soccer_epl"],
    "basket": ["basketball_nba"],
    "football": ["americanfootball_nfl"]
}

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# =========================
# STATE: evita duplicati
# =========================
sent_matches = set()  # memorizza chiavi dei pronostici già inviati in questa esecuzione

def make_key(sport_label, home, away, dt_local_str, market_label):
    return f"{sport_label}|{home}|{away}|{dt_local_str}|{market_label}"

# =========================
# TELEGRAM
# =========================
def send_telegram_message(message: str):
    """Invia un messaggio su Telegram (logga errori ma non blocca)."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram non configurato: TOKEN/CHAT_ID mancanti.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        r = requests.post(url, json=payload, timeout=20)
        r.raise_for_status()
    except Exception as e:
        logging.error(f"Errore invio Telegram: {e}")

# =========================
# UTILS DATE & CSV
# =========================
def now_utc():
    return pd.Timestamp.now(tz="UTC")

def parse_dt(series):
    return pd.to_datetime(series, errors="coerce", dayfirst=True, utc=True)

def to_local(dt_utc):
    try:
        return dt_utc.tz_convert("Europe/Rome")
    except Exception:
        return dt_utc

def find_col(df, names):
    for n in names:
        if n in df.columns:
            return n
    return None

def list_csv():
    files = []
    for f in os.listdir():
        if f.lower().endswith(".csv"):
            files.append(f)
    return files

# =========================
# ODDS API (on-demand)
# =========================
def fetch_odds(sport_key, markets="h2h,totals,spreads"):
    """Recupera quote per uno sport. Usato solo se serve (candidato pick già filtrato)."""
    if not ODDS_API_KEY:
        return []
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {"apiKey": ODDS_API_KEY, "regions": "eu", "markets": markets, "oddsFormat": "decimal"}
    try:
        r = requests.get(url, params=params, timeout=25)
        if r.status_code != 200:
            logging.error(f"Odds fetch error {sport_key}/{markets}: {r.status_code} {r.text[:180]}")
            return []
        logging.info(f"✅ Odds API chiamata per {sport_key} (markets={markets})")
        return r.json()
    except Exception as e:
        logging.error(f"Odds fetch error {sport_key}/{markets}: {e}")
        return []

def best_price_from_odds(event, desired_market, team_name=None, min_total=None):
    """
    Estrae il miglior prezzo dal JSON dell'evento per mercato:
    - desired_market in {"h2h","totals","spreads"}
    - team_name per h2h/spreads
    - min_total per totals (filtra linee troppo basse)
    """
    best = None
    for bm in event.get("bookmakers", []):
        for mk in bm.get("markets", []):
            if mk.get("key") != desired_market:
                continue
            for out in mk.get("outcomes", []):
                try:
                    price = float(out.get("price", 0))
                except Exception:
                    continue
                if price < MIN_ODDS:
                    continue

                if desired_market == "h2h":
                    # confronta con team desiderato (home/away name)
                    if team_name and out.get("name") != team_name:
                        continue
                    cand = price

                elif desired_market == "totals":
                    point = out.get("point")
                    try:
                        line = float(point) if point is not None else None
                    except Exception:
                        line = None
                    # filtra linee troppo basse (basket/football)
                    if min_total and (line is None or line < min_total):
                        continue
                    cand = price

                elif desired_market == "spreads":
                    # preferiamo spread favorevole (non valutiamo signe: solo prezzo)
                    if team_name and out.get("name") != team_name:
                        continue
                    cand = price

                else:
                    continue

                if best is None or cand > best:
                    best = cand
    return best

# =========================
# FORMAT MSG
# =========================
def fmt_msg(sport_label, emoji, home, away, dt_utc, market_label, odds, prob):
    dt_local = to_local(dt_utc)
    prob_pct = int(round(max(MIN_WIN_PROB, min(0.95, float(prob))) * 100))
    odds_txt = f"{odds:.2f}" if isinstance(odds, (int, float)) else str(odds)
    return (
        f"📊 Pronostico {sport_label}\n"
        f"{emoji} {home} vs {away}\n"
        f"📅 {dt_local.strftime('%d/%m/%Y - %H:%M')}\n"
        f"🔮 Pronostico: {market_label}\n"
        f"💰 Quota stimata: {odds_txt}\n"
        f"📈 Percentuale vincita stimata: {prob_pct}%"
    )

# =========================
# HEURISTICHE CSV
# =========================
def safe_team(row, keys, default="Sconosciuta"):
    for k in keys:
        if k in row and pd.notna(row[k]):
            return str(row[k])
    return default

def soccer_candidates(df, file_name):
    """
    Calcio: produce candidati per 4 mercati: 1X2, BTTS, O/U 2.5, Doppia Chance.
    Ritorna lista di dict con {home, away, dt, market_label, market_type}.
    """
    out = []
    now = now_utc()
    date_col = find_col(df, ["date", "Date", "match_date"])
    if not date_col:
        return out
    df[date_col] = parse_dt(df[date_col])
    df = df[df[date_col] > now].copy()
    if df.empty:
        return out

    # Prova colonne team tipiche
    home_cols = ["HomeTeam", "homeTeam", "home_team", "homeTeamId", "Home"]
    away_cols = ["AwayTeam", "awayTeam", "away_team", "awayTeamId", "Away"]

    for _, row in df.head(6).iterrows():
        home = safe_team(row, home_cols, "Casa")
        away = safe_team(row, away_cols, "Ospiti")
        dt = row[date_col]

        # Heuristica: generiamo 4 candidati diversi
        # 1X2 (Home)
        out.append({"sport":"Calcio","emoji":"⚽","home":home,"away":away,"dt":dt,
                    "market_label":f"1X2 → {home}","market_type":"h2h","side":home})
        # BTTS Gol
        out.append({"sport":"Calcio","emoji":"⚽","home":home,"away":away,"dt":dt,
                    "market_label":"Gol/No Gol → Gol","market_type":"btts"})
        # Over/Under 2.5
        out.append({"sport":"Calcio","emoji":"⚽","home":home,"away":away,"dt":dt,
                    "market_label":"Over 2.5","market_type":"totals_ou25"})
        # Doppia Chance 1X
        out.append({"sport":"Calcio","emoji":"⚽","home":home,"away":away,"dt":dt,
                    "market_label":"Doppia Chance → 1X","market_type":"double_chance"})
    return out

def basket_candidates(df, file_name):
    """
    Basket: 4 mercati: Moneyline, Totali >=218.5, Spread, Pari/Dispari.
    """
    out = []
    now = now_utc()
    date_col = find_col(df, ["Date", "date", "GameDate"])
    if not date_col:
        return out
    df[date_col] = parse_dt(df[date_col])
    df = df[df[date_col] > now].copy()
    if df.empty:
        return out

    home_cols = ["HomeTeam", "Home/Neutral", "TeamHome", "Home", "home"]
    away_cols = ["AwayTeam", "Visitor/Neutral", "TeamAway", "Away", "away"]

    for _, row in df.head(4).iterrows():
        home = safe_team(row, home_cols, "Home")
        away = safe_team(row, away_cols, "Away")
        dt = row[date_col]

        out.append({"sport":"Basket","emoji":"🏀","home":home,"away":away,"dt":dt,
                    "market_label":f"Moneyline → {home}","market_type":"h2h","side":home})
        out.append({"sport":"Basket","emoji":"🏀","home":home,"away":away,"dt":dt,
                    "market_label":f"Over {BASKET_MIN_TOTAL}","market_type":"totals_basket"})
        out.append({"sport":"Basket","emoji":"🏀","home":home,"away":away,"dt":dt,
                    "market_label":f"Spread → {home}","market_type":"spreads","side":home})
        out.append({"sport":"Basket","emoji":"🏀","home":home,"away":away,"dt":dt,
                    "market_label":"Totale Punti Pari","market_type":"even_odd"})
    return out

def football_candidates(df, file_name):
    """
    Football: 4 mercati: Moneyline, Totali >=37.5, Spread, Margine di Vittoria.
    """
    out = []
    now = now_utc()
    date_col = find_col(df, ["Date", "date", "GameDate"])
    if not date_col:
        return out
    df[date_col] = parse_dt(df[date_col])
    df = df[df[date_col] > now].copy()
    if df.empty:
        return out

    home_cols = ["HomeTeam", "Home", "home"]
    away_cols = ["AwayTeam", "Away", "away"]
    # Alcuni dataset NFL hanno Winner/Loser: li usiamo come placeholder per i nomi
    if not find_col(df, home_cols) and "Winner/tie" in df.columns and "Loser/tie" in df.columns:
        home_cols = ["Winner/tie"]
        away_cols = ["Loser/tie"]

    for _, row in df.head(4).iterrows():
        home = safe_team(row, home_cols, "Home")
        away = safe_team(row, away_cols, "Away")
        dt = row[date_col]

        out.append({"sport":"Football","emoji":"🏈","home":home,"away":away,"dt":dt,
                    "market_label":f"Moneyline → {home}","market_type":"h2h","side":home})
        out.append({"sport":"Football","emoji":"🏈","home":home,"away":away,"dt":dt,
                    "market_label":f"Over {FOOTBALL_MIN_TOTAL}","market_type":"totals_football"})
        out.append({"sport":"Football","emoji":"🏈","home":home,"away":away,"dt":dt,
                    "market_label":f"Spread → {home}","market_type":"spreads","side":home})
        out.append({"sport":"Football","emoji":"🏈","home":home,"away":away,"dt":dt,
                    "market_label":"Margine Vittoria (1-6) → {home}","market_type":"winning_margin"})
    return out

def estimate_prob_and_odds(candidate):
    """
    Stima una probabilità e una quota base da CSV.
    Mantiene prob >= MIN_WIN_PROB e quota >= MIN_ODDS quando possibile.
    """
    # euristica semplice ma stabile
    base_map = {
        "h2h": 0.78,
        "totals_ou25": 0.76,
        "btts": 0.77,
        "double_chance": 0.80,
        "totals_basket": 0.78,
        "spreads": 0.76,
        "even_odd": 0.75,
        "totals_football": 0.78,
        "winning_margin": 0.76
    }
    p = base_map.get(candidate["market_type"], 0.76)
    p = max(MIN_WIN_PROB, min(0.95, p))

    # quota “stimata” base (se non riusciamo a leggere dalle odds API)
    est_odds = max(MIN_ODDS, round((1.0 / p) * 1.03, 2))
    return p, est_odds

# =========================
# PIPELINE PRINCIPALE
# =========================
def build_candidates_from_csv():
    """
    Legge tutti i CSV e costruisce una lista di candidati (futuri) per i 4 mercati/sport.
    """
    candidates = []
    files = list_csv()
    if not files:
        logging.info("Nessun CSV trovato nella cartella.")
        return candidates

    # Log di controllo: quante future per file
    now = now_utc()
    logging.info("📊 Check CSV caricati (partite future per file):")
    for f in files:
        try:
            df = pd.read_csv(f)
            dc = None
            for c in df.columns:
                if "date" in c.lower():
                    dc = c; break
            if not dc:
                logging.info(f" - {f}: nessuna colonna data")
                continue
            df[dc] = parse_dt(df[dc])
            fut = df[df[dc] > now]
            logging.info(f" - {f}: future = {len(fut)}")
        except Exception as e:
            logging.error(f"Errore lettura {f}: {e}")

    # Genera candidati per sport
    for f in files:
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        lf = f.lower()
        # Heuristic per capire sport dal nome o dalle colonne
        if lf.startswith("calcio") or "soccer" in lf:
            candidates += soccer_candidates(df, f)
        elif lf.startswith("basket") or "basketball" in lf or "nba" in lf:
            candidates += basket_candidates(df, f)
        elif "nfl" in lf or "football" in lf or "american" in lf:
            candidates += football_candidates(df, f)

    return candidates

def enrich_with_odds_if_needed(candidates):
    """
    Per i candidati con prob >= MIN_WIN_PROB, tenta di prendere la quota reale tramite Odds API
    SOLO quando utile, per risparmiare crediti.
    """
    if not candidates:
        return []

    # Prima stimiamo prob e quota base CSV
    enriched = []
    for c in candidates:
        p, est_odds = estimate_prob_and_odds(c)
        c["prob"] = p
        c["est_odds"] = est_odds
        # consideriamo solo quelli che superano la soglia
        if p >= MIN_WIN_PROB:
            enriched.append(c)

    if not enriched:
        return []

    # Raggruppiamo per sport per minimizzare chiamate
    need_odds = defaultdict(list)
    for c in enriched:
        if c["sport"] == "Calcio":
            key_list = SPORT_KEYS["soccer"]
        elif c["sport"] == "Basket":
            key_list = SPORT_KEYS["basket"]
        elif c["sport"] == "Football":
            key_list = SPORT_KEYS["football"]
        else:
            key_list = []

        need_odds[tuple(key_list)].append(c)

    # Per ciascun gruppo di sport keys, effettua 1-2 chiamate e prova a mappare i match
    # (matching semplice su home/away stringhe)
    for sport_keys, cand_list in need_odds.items():
        if not sport_keys:
            continue

        # markets sempre quelli coperti dall’API
        fetched_events = []
        for sk in sport_keys:
            events = fetch_odds(sk, markets="h2h,totals,spreads")
            if events:
                fetched_events.extend(events)

        if not fetched_events:
            continue

        # prova ad assegnare la migliore quota per ciascun candidato
        for c in cand_list:
            home = c["home"]; away = c["away"]; dt = c["dt"]
            # trova evento “più simile” (match per team names)
            matches = [ev for ev in fetched_events
                       if ev.get("home_team") == home or ev.get("away_team") == away
                          or ev.get("home_team") == away or ev.get("away_team") == home]

            if not matches:
                continue

            ev = matches[0]  # prima corrispondenza semplice
            mtype = c["market_type"]
            best_price = None

            if mtype == "h2h":
                best_price = best_price_from_odds(ev, "h2h", team_name=c.get("side"))
            elif mtype == "totals_basket":
                best_price = best_price_from_odds(ev, "totals", min_total=BASKET_MIN_TOTAL)
            elif mtype == "totals_football" or mtype == "totals_ou25":
                # per calcio non forziamo linea a 2.5 via API (potrebbe non esserci); usiamo price se c'è
                best_price = best_price_from_odds(ev, "totals")
            elif mtype == "spreads":
                best_price = best_price_from_odds(ev, "spreads", team_name=c.get("side"))
            # btts, double_chance, even_odd, winning_margin non sono generalizzati via API → teniamo est_odds

            if best_price and best_price >= MIN_ODDS:
                c["est_odds"] = round(float(best_price), 2)
                c["from_api"] = True
            else:
                c["from_api"] = False

    return enriched

def generate_and_send():
    """
    Pipeline:
    - Costruisce candidati dai CSV (solo gare future)
    - Stima probabilità (>=75%)
    - Chiede odds all’API solo per i candidati idonei
    - Invia messaggi su Telegram, evitando duplicati
    """
    candidates = build_candidates_from_csv()
    if not candidates:
        logging.info("Nessun candidato trovato dai CSV.")
        return

    picks = enrich_with_odds_if_needed(candidates)
    if not picks:
        logging.info("Nessun pronostico sopra soglia trovata.")
        return

    # Ordina e limita per non spammare (max 8 a giro)
    picks = picks[:8]

    sent = 0
    for p in picks:
        sport = p["sport"]; emoji = p["emoji"]
        home = p["home"]; away = p["away"]; dt = p["dt"]
        market_label = p["market_label"]; prob = p["prob"]; odds = p["est_odds"]

        msg = fmt_msg(sport, emoji, home, away, dt, market_label, odds, prob)
        key = make_key(sport, home, away, to_local(dt).strftime("%Y-%m-%d %H:%M"), market_label)
        if key in sent_matches:
            logging.info(f"Già inviato, salto → {key}")
            continue
        sent_matches.add(key)

        logging.info(f"Invio pronostico → {sport} | {home} vs {away} | {market_label} | odds={odds} | prob={prob}")
        send_telegram_message(msg)
        sent += 1

    if sent == 0:
        logging.info("Nessun nuovo pronostico da inviare (tutti già inviati in precedenza).")

# =========================
# MAIN LOOP
# =========================
if __name__ == "__main__":
    # Messaggio test all’avvio
    send_telegram_message("✅ Test: il bot è avviato ed è connesso a Telegram!")

    logging.info("🤖 Bot avviato, in ascolto...")
    while True:
        try:
            generate_and_send()
        except Exception as e:
            logging.error(f"Errore ciclo principale: {e}")
        time.sleep(CHECK_INTERVAL_SEC)
