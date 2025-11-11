# -*- coding: utf-8 -*-
"""
Aggiornamento meteo per nazioni principali di ogni sport
✅ Usa Open-Meteo (gratuito, senza chiave)
✅ Calcola meteo medio per nazione (non singola città)
✅ Salva in /data/weather_cache/<sport>_weather.json
"""

import os
import time
import json
import logging
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

DATA_DIR = "/data/weather_cache"
os.makedirs(DATA_DIR, exist_ok=True)

# Coordinate medie nazionali per gli sport in lista
SPORT_COUNTRIES = {
    "football": [
        ("Italia", 41.9, 12.5),
        ("Spagna", 40.0, -4.0),
        ("Francia", 46.5, 2.5),
        ("Germania", 51.0, 10.0),
        ("Inghilterra", 52.0, -1.5)
    ],
    "basketball": [
        ("Stati Uniti", 39.8, -98.6),
        ("Canada", 56.1, -106.3)
    ],
    "americanfootball": [
        ("Stati Uniti", 39.8, -98.6)
    ],
    "baseball": [
        ("Stati Uniti", 39.8, -98.6),
        ("Giappone", 36.2, 138.3)
    ],
    "icehockey": [
        ("Canada", 56.1, -106.3),
        ("Stati Uniti", 39.8, -98.6),
        ("Finlandia", 64.0, 26.0)
    ],
    "tennis": [
        ("Italia", 41.9, 12.5),
        ("Francia", 46.5, 2.5),
        ("Spagna", 40.0, -4.0),
        ("Stati Uniti", 39.8, -98.6),
        ("Cina", 35.8, 104.2),
        ("Australia", -25.3, 133.8)
    ]
}

def get_weather(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json().get("current_weather", {})
        else:
            return {}
    except Exception:
        return {}

def update_weather():
        logging.info("🌦️ Aggiornamento meteo per nazioni in corso...")
    total_entries = 0
    updated_sports = 0

    for sport, countries in SPORT_COUNTRIES.items():
        results = []
        for country, lat, lon in countries:
            w = get_weather(lat, lon)
            if w:
                w["country"] = country
                results.append(w)
            time.sleep(1)

        out_path = os.path.join(DATA_DIR, f"{sport}_weather.json")
        json.dump(results, open(out_path, "w", encoding="utf-8"))

        updated_sports += 1
        total_entries += len(results)
        logging.info(f"✅ Salvato meteo per {sport}: {len(results)} nazioni")

    logging.info(f"🏁 Meteo aggiornato per {updated_sports} sport, {total_entries} località totali.")

if __name__ == "__main__":
    update_weather()
