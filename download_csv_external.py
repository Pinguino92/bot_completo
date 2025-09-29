import os
import requests
import logging
import schedule
import time
import pandas as pd  # ← (1) aggiunta

logging.basicConfig(level=logging.INFO)

# Directory di destinazione
os.makedirs("data/calcio", exist_ok=True)
os.makedirs("data/basket", exist_ok=True)
os.makedirs("data/football", exist_ok=True)
os.makedirs("data/hockey", exist_ok=True)

# Mappa competizioni → link CSV verificati o utili
CSV_LINKS = {
    # ⚽ Calcio (football-data.co.uk)
    "soccer_italy_serie_a": [
        "https://www.football-data.co.uk/mmz4281/2425/I1.csv",
    ],
    "soccer_italy_serie_b": [
        "https://www.football-data.co.uk/mmz4281/2425/I2.csv",
    ],
    "soccer_spain_la_liga": [
        "https://www.football-data.co.uk/mmz4281/2425/SP1.csv",
    ],
    "soccer_spain_segunda_division": [
        "https://www.football-data.co.uk/mmz4281/2425/SP2.csv",
    ],
    "soccer_epl": [
        "https://www.football-data.co.uk/mmz4281/2425/E0.csv",
    ],
    "soccer_efl_champ": [  # 👈 corretto da soccer_championship
        "https://www.football-data.co.uk/mmz4281/2425/E1.csv",
    ],
    "soccer_germany_bundesliga": [
        "https://www.football-data.co.uk/mmz4281/2425/D1.csv",
    ],
    "soccer_germany_bundesliga2": [
        "https://www.football-data.co.uk/mmz4281/2425/D2.csv",
    ],
    "soccer_france_ligue_one": [
        "https://www.football-data.co.uk/mmz4281/2425/F1.csv",
    ],
    "soccer_france_ligue_two": [
        "https://www.football-data.co.uk/mmz4281/2425/F2.csv",
    ],
    "soccer_uefa_champs_league": [
        "https://www.football-data.co.uk/mmz4281/2425/EC.csv",
    ],
    "soccer_uefa_europa_league": [
        "https://www.football-data.co.uk/mmz4281/2425/EU.csv",
    ],

   # 🏀 NBA
"basketball_nba": [
    "https://raw.githubusercontent.com/sportsdataverse/nba-data/master/games/games.csv",
    "https://raw.githubusercontent.com/NocturneBear/NBA-Data-2010-2024/main/nba_games.csv",
],

# 🏈 NFL
"americanfootball_nfl": [
    "https://raw.githubusercontent.com/nflverse/nflverse-data/master/games.csv"
    "https://raw.githubusercontent.com/nflverse/nflfastR-data/master/data/games.csv",
],

# 🏈 NCAA Football
"americanfootball_ncaaf": [
    "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/master/games.csv",
],

# 🏒 NHL
"icehockey_nhl": [
    "https://raw.githubusercontent.com/kevinzdavidson/hockeyR-data/main/games.csv",
],

}

# (2) funzione di pulizia leggera post-download
def sanitize_csv(path: str, sport_key: str):
    """
    Pulizia base:
    - autodetect delimiter (virgola/semicolon/tab)
    - UTF-8, rimozione BOM se presente
    - salta righe corrotte e righe completamente vuote
    Non rinomina colonne: i football-data per il calcio sono già conformi.
    """
    try:
        df = pd.read_csv(
            path,
            sep=None,              # autodetect delimitatore
            engine="python",
            encoding="utf-8",
            on_bad_lines="skip"
        )
        df = df.dropna(how="all")
        df.to_csv(path, index=False, encoding="utf-8")
    except UnicodeDecodeError:
        # rimuovi BOM e riprova
        with open(path, "rb") as f:
            raw = f.read()
        bom = b"\xef\xbb\xbf"
        if raw.startswith(bom):
            raw = raw[len(bom):]
        with open(path, "wb") as f:
            f.write(raw)
        try:
            df = pd.read_csv(path, sep=None, engine="python", on_bad_lines="skip")
            df = df.dropna(how="all")
            df.to_csv(path, index=False, encoding="utf-8")
        except Exception as e2:
            logging.warning(f"Pulizia fallback fallita per {path}: {e2}")
    except Exception as e:
        logging.warning(f"Pulizia CSV non riuscita per {path}: {e}")

def download_all_csv():
    for comp, links in CSV_LINKS.items():
        if comp.startswith("soccer_"):
            folder = "data/calcio"
        elif comp.startswith("basketball_"):
            folder = "data/basket"
        elif comp.startswith("americanfootball_"):
            folder = "data/football"
        elif comp.startswith("icehockey_"):
            folder = "data/hockey"
        else:
            folder = "data/misc"

        os.makedirs(folder, exist_ok=True)

        for url in links:
            try:
                filename = url.split("/")[-1]
                dest = f"{folder}/{comp}_{filename}"
                r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                with open(dest, "wb") as f:
                    f.write(r.content)
                logging.info(f"✅ Scaricato {comp}: {filename}")
                sanitize_csv(dest, comp)  # ← (2) chiamata alla pulizia
            except Exception as e:
                logging.error(f"❌ Errore download {url}: {e}")

def job():
    print("⏳ Download CSV esterni in corso...")
    download_all_csv()
    print("✅ Download CSV esterni completato!")

# schedulazione: ogni giorno alle 09:00
schedule.every().day.at("09:00").do(job)

if __name__ == "__main__":
    job()  # primo download immediato al deploy
    while True:
        schedule.run_pending()
        time.sleep(60)
