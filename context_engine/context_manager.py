import os, json, requests, logging

DATA_CONTEXT = "/data/context"
os.makedirs(DATA_CONTEXT, exist_ok=True)

def context_adjustment(sport, home, away):
    bonus = 0
    try:
        inj = os.path.join(DATA_CONTEXT,"injuries.json")
        mot = os.path.join(DATA_CONTEXT,"motivation.json")
        wea = os.path.join(DATA_CONTEXT,"weather.json")
        injuries = json.load(open(inj)) if os.path.exists(inj) else {}
        motivation = json.load(open(mot)) if os.path.exists(mot) else {}
        weather = json.load(open(wea)) if os.path.exists(wea) else {}

        # penalità/bonus semplici
        if home in injuries.get(sport, {}): bonus -= 5 * len(injuries[sport][home])
        if away in injuries.get(sport, {}): bonus += 3 * len(injuries[sport][away])
        if motivation.get(sport, {}).get(home) == "high": bonus += 2
        if motivation.get(sport, {}).get(home) == "low":  bonus -= 2
        if motivation.get(sport, {}).get(away) == "high": bonus -= 2
        if motivation.get(sport, {}).get(away) == "low":  bonus += 2
        if weather.get("generic",{}).get("wind_speed",0) > 25: bonus -= 1
    except Exception as e:
        logging.warning(f"context_adjustment: {e}")
    return bonus

def update_context_data():
    """Aggiorna meteo leggero (esempio Roma)."""
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=41.9&longitude=12.5&current=temperature_2m,wind_speed_10m"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            cur = r.json().get("current",{})
            out = {"generic":{"wind_speed":cur.get("wind_speed_10m",0)}}
            json.dump(out, open(os.path.join(DATA_CONTEXT,"weather.json"),"w"))
    except Exception as e:
        logging.warning(f"update_context_data: {e}")
