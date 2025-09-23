import os
import re
import time
import logging
import pathlib
import requests
from urllib.parse import urlparse, parse_qs

# Logging
logging.basicConfig(level=logging.INFO)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

OUT_DIR = pathlib.Path("downloads")

# === INSERISCI QUI i link Google Drive e HTTP ===
LINKS = {
    "LINKS = {
    "soccer_italy_serie_a": [
        "https://drive.google.com/file/d/1IwH4OWw8K7d6lA6L_yOHDv0sPWzAjB7R/view?usp=sharing",
        "https://drive.google.com/file/d/1OvFQSfS818GvIrE668IceV2BxWpUwpPH/view?usp=sharing",
        "https://drive.google.com/file/d/1nuA3X9RR8nmHCiIJgHtYBNXSBfh5JVpz/view?usp=sharing",
        "https://drive.google.com/file/d/1Mu5mHX1iZ6DDty4yOsPBhYDBG4IV8tBo/view?usp=sharing",
    ],
    "soccer_spain_la_liga": [
        "https://drive.google.com/file/d/101leVcEblRX6SIZQ9IPYt3gBftfdTfU6/view?usp=sharing",
        "https://drive.google.com/file/d/1ZuKPIIPCH9aqwX80CpDb0-KGVcylYlRy/view?usp=sharing",
    ],
    "soccer_france_ligue_one": [
        "https://drive.google.com/file/d/1DCElGIAfJmpKcCWU6i2vcuCPs1No5orq/view?usp=sharing",
        "https://drive.google.com/file/d/1Wu9IG7QdmunqUw0duHVgCzzLlMXhSLE5/view?usp=sharing",
    ],
    "soccer_germany_bundesliga": [
        "https://drive.google.com/file/d/18-IzszXSMuTehzogMXzCpEtXY4MX-3y7/view?usp=sharing",
        "https://drive.google.com/file/d/1rzjuCvl1FCY81BdUiFycC0doRUHtjjLR/view?usp=sharing",
    ],
    "soccer_england_efl_champ": [
        "https://drive.google.com/file/d/1wEjlzWU9e_B9VVtQQTXzRP9hXu7C_4SH/view?usp=sharing",
        "https://drive.google.com/file/d/1fjVYftn8Wzq5wVsgD1-9I3b1x8JsOhqK/view?usp=sharing",
    ],
    "soccer_uefa_champs_league": [
        "https://drive.google.com/file/d/1UjdjPAGJYZvqGchWlrb3DWbBNl_eHuxN/view?usp=sharing",
        "https://drive.google.com/file/d/1c1WEcoUiGnvfs34Fs8EQQlwlHsNPnoTA/view?usp=sharing",
    ],
    "soccer_uefa_europa_league": [
        "https://drive.google.com/file/d/10LQ4_jPdt3NG42MGPUbrRygmMXXChRvo/view?usp=sharing",
        "https://drive.google.com/file/d/1INKdlNQxnoyDuNhMIYwAe0LA1SxveDcC/view?usp=sharing",
    ],
    "soccer_argentina_primera_division": [
        "https://drive.google.com/file/d/109b1Cw9xPCND3gDGBHElegMp6ky5Uk_h/view?usp=sharing",
    ],
    "soccer_brazil_campeonato": [
        "https://drive.google.com/file/d/1Cv0zrXxbEV7pVT4tT2dMBaFwD4fKuiIT/view?usp=sharing",
    ],
    "soccer_mexico_ligamx": [
        "https://drive.google.com/file/d/1f9jKgs5DcvUES_9KdaYdqyCP-L-7hNdS/view?usp=sharing",
    ],
    "soccer_portugal_primeira_liga": [
        "https://drive.google.com/file/d/1MHk4DTUw2rzhCZMDFB7yCLwOc1HWHFmR/view?usp=sharing",
    ],
    "soccer_netherlands_eredivisie": [
        "https://drive.google.com/file/d/1FN39YP3RwZsrgxC7n-Jlp5C9Yv6i-Zh_/view?usp=sharing",
    ],
    "soccer_turkey_super_league": [
        "https://drive.google.com/file/d/1x0nZkpMHAainZQsBgxsyjRghOgDfltIg/view?usp=sharing",
    ],

    "basketball_nba": [
         "https://drive.google.com/file/d/1zMdXKb_0Kgy734fl_J3cDZ7KOgCNM6Ng/view?usp=drive_link",
         "https://drive.google.com/file/d/1eSXgRXH9U7QrO5Q4LO6oA6pweyaCqsgF/view?usp=drive_link",
         "https://drive.google.com/file/d/1jRzPAg5Q-yHmJPqYliakxDmWnrpMCqu_/view?usp=drive_link",
         "https://drive.google.com/file/d/1XZ_fzreWKgSrt4Fdh6Dzooax3Bc0ZugF/view?usp=drive_link",
    ],

    ],
    "americanfootball_nfl": [
         "https://drive.google.com/file/d/1c6mPo49iqxkl3Z2soKlJrY9wdF3874Jl/view?usp=drive_link",
         "https://drive.google.com/file/d/10HdPiazGdgoHhmAGFZWrltlTdbhHW-jg/view?usp=drive_link",
         "https://drive.google.com/file/d/1jdBb1FntwcUNEFsGcpsm_l4CfYvXmwxf/view?usp=drive_link",
         "https://drive.google.com/file/d/1mx56GF1c9t5TLb2jt4XpvcBUGNzG1hQL/view?usp=drive_link",
    ],
    "americanfootball_ncaaf": [
         "https://drive.google.com/file/d/10HdPiazGdgoHhmAGFZWrltlTdbhHW-jg/view?usp=drive_link",
         "https://drive.google.com/file/d/1jdBb1FntwcUNEFsGcpsm_l4CfYvXmwxf/view?usp=drive_link",
    ],

}

# --- FUNZIONI UTILI ---

def extract_file_id(url: str) -> str | None:
    """Estrae l'ID da link Google Drive."""
    m = re.search(r"/d/([-\w]{10,})", url)
    if m:
        return m.group(1)
    qs = parse_qs(urlparse(url).query)
    if "id" in qs:
        return qs["id"][0]
    return None

def build_direct_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"

def download_google_drive(url: str, dest_path: str, max_retries: int = 2) -> bool:
    """Scarica un file da Google Drive con gestione token di conferma."""
    file_id = extract_file_id(url)
    if not file_id:
        logging.error(f"❌ Link non valido: {url}")
        return False

    direct = build_direct_url(file_id)
    for attempt in range(1, max_retries + 1):
        try:
            r = SESSION.get(direct, stream=True, timeout=60)

            # controllo pagina HTML (richiesta conferma)
            if "text/html" in r.headers.get("Content-Type", ""):
                html = r.text
                m = re.search(r"confirm=([0-9A-Za-z_]+)", html)
                if m:
                    confirm_url = f"{direct}&confirm={m.group(1)}"
                    r = SESSION.get(confirm_url, stream=True, timeout=60)

            if "text/html" in r.headers.get("Content-Type", ""):
                logging.error(f"❌ Conferma Google Drive non risolta: {url} (tentativo {attempt})")
                continue

            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(32768):
                    f.write(chunk)

            logging.info(f"✅ Scaricato da Google Drive: {dest_path}")
            return True
        except Exception as e:
            logging.error(f"❌ Errore download GDrive {url}: {e}")

    return False

def download_http(url: str, dest_path: str) -> bool:
    """Scarica file da URL diretto (http/https)."""
    try:
        r = SESSION.get(url, timeout=60)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(r.content)
        logging.info(f"✅ Scaricato: {dest_path}")
        return True
    except Exception as e:
        logging.error(f"❌ Errore download {url}: {e}")
        return False

# --- MAIN ---
def main():
    ok, fail = 0, 0
    for sport_key, urls in LINKS.items():
        base = OUT_DIR / sport_key   # 👈 usa la chiave API come cartella
        base.mkdir(parents=True, exist_ok=True)


        for url in urls:
            filename = url.split("/")[-1] or "file.csv"
            dest = base / filename

            if "drive.google.com" in url:
                success = download_google_drive(url, str(dest))
            else:
                success = download_http(url, str(dest))

            if success:
                ok += 1
            else:
                fail += 1

    logging.info(f"📊 Download completati: ✅ {ok} | ❌ {fail}")

if __name__ == "__main__":
    main()
