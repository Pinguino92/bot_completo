import os
import requests
import logging

logging.basicConfig(level=logging.INFO)

# Directory di destinazione
os.makedirs("data/calcio", exist_ok=True)
os.makedirs("data/basket", exist_ok=True)
os.makedirs("data/football", exist_ok=True)

# Mappa competizioni → link CSV verificati o utili
CSV_LINKS = {
    # ⚽ Calcio (football-data.co.uk)
    "soccer_italy_serie_a": [
        "https://www.football-data.co.uk/mmz4281/2425/I1.csv",
        "https://www.football-data.co.uk/mmz4281/2526/I1.csv",
    ],
    "soccer_italy_serie_b": [
        "https://www.football-data.co.uk/mmz4281/2425/I2.csv",
        "https://www.football-data.co.uk/mmz4281/2526/I2.csv",
    ],
    "soccer_spain_la_liga": [
        "https://www.football-data.co.uk/mmz4281/2425/SP1.csv",
        "https://www.football-data.co.uk/mmz4281/2526/SP1.csv",
    ],
    "soccer_spain_segunda_division": [
        "https://www.football-data.co.uk/mmz4281/2425/SP2.csv",
        "https://www.football-data.co.uk/mmz4281/2526/SP2.csv",
    ],
    "soccer_epl": [
        "https://www.football-data.co.uk/mmz4281/2425/E0.csv",
        "https://www.football-data.co.uk/mmz4281/2526/E0.csv",
    ],
    "soccer_championship": [
        "https://www.football-data.co.uk/mmz4281/2425/E1.csv",
        "https://www.football-data.co.uk/mmz4281/2526/E1.csv",
    ],
    "soccer_germany_bundesliga": [
        "https://www.football-data.co.uk/mmz4281/2425/D1.csv",
        "https://www.football-data.co.uk/mmz4281/2526/D1.csv",
    ],
    "soccer_germany_bundesliga2": [
        "https://www.football-data.co.uk/mmz4281/2425/D2.csv",
        "https://www.football-data.co.uk/mmz4281/2526/D2.csv",
    ],
    "soccer_france_ligue_one": [
        "https://www.football-data.co.uk/mmz4281/2425/F1.csv",
        "https://www.football-data.co.uk/mmz4281/2526/F1.csv",
    ],
    "soccer_france_ligue_two": [
        "https://www.football-data.co.uk/mmz4281/2425/F2.csv",
        "https://www.football-data.co.uk/mmz4281/2526/F2.csv",
    ],
    "soccer_uefa_champs_league": [
        "https://www.football-data.co.uk/mmz4281/2425/EC.csv",
        "https://www.football-data.co.uk/mmz4281/2526/EC.csv",
    ],
    "soccer_uefa_europa_league": [
        "https://www.football-data.co.uk/mmz4281/2425/EU.csv",
        "https://www.football-data.co.uk/mmz4281/2526/EU.csv",
    ],

    # 🏀 NBA (repo NocturneBear)
    # Uso regolare stagione fino al 2024
    "basketball_nba": [
        "https://github.com/NocturneBear/NBA-Data-2010-2024/raw/main/regular_season_box_scores_2010_2024_part_1.csv",
        "https://github.com/NocturneBear/NBA-Data-2010-2024/raw/main/regular_season_box_scores_2010_2024_part_2.csv",
        "https://github.com/NocturneBear/NBA-Data-2010-2024/raw/main/regular_season_totals_2010_2024.csv",
    ],

    # 🏈 NFL (nflverse data)
    "americanfootball_nfl": [
        "https://github.com/nflverse/nflverse-data/raw/master/games.csv.gz"
    ],

    # NCAA Football (potresti trovare dataset simile/analogo, non sempre aggiornati)
    "americanfootball_ncaaf": [
        "https://github.com/nflverse/nflverse-data/raw/master/college_games.csv.gz"
    ]
}

for comp, links in CSV_LINKS.items():
    if comp.startswith("soccer_"):
        folder = "data/calcio"
    elif comp.startswith("basketball_"):
        folder = "data/basket"
    elif comp.startswith("americanfootball_"):
        folder = "data/football"
    else:
        folder = "data/misc"

    os.makedirs(folder, exist_ok=True)

    for url in links:
        try:
            filename = url.split("/")[-1]
            dest = f"{folder}/{comp}_{filename}"
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            with open(dest, "wb") as f:
                f.write(r.content)
            logging.info(f"✅ Scaricato {comp}: {filename}")
        except Exception as e:
            logging.error(f"❌ Errore download {url}: {e}")

import schedule
import time

def job():
    print("⏳ Download CSV esterni in corso...")
    download_all_csv()   # 👈 la tua funzione principale che scarica i CSV
    print("✅ Download CSV esterni completato!")

# schedulazione: ogni giorno alle 02:00
schedule.every().day.at("09:00").do(job)

if _name_ == "_main_":
    job()  # primo download immediato al deploy
    while True:
        schedule.run_pending()
        time.sleep(60)
