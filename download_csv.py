import os
import re
import time
import logging
import pathlib
import requests
from urllib.parse import urlparse, parse_qs

def _gdrive_extract_id(url: str):
    m = re.search(r'/d/([-\w]{10,})', url)
    if m:
        return m.group(1)
    qs = parse_qs(urlparse(url).query)
    if 'id' in qs:
        return qs['id'][0]
    return None

def _download_google_drive(url: str, dest_path: str, max_retries: int = 2) -> bool:
    file_id = _gdrive_extract_id(url)
    if not file_id:
        logging.error(f"⚠️ Impossibile estrarre l'ID da: {url}")
        return False

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    base = f"https://drive.google.com/uc?export=download&id={file_id}"

    for attempt in range(1, max_retries + 1):
        try:
            r = session.get(base, stream=True, timeout=60)

            token = None
            for k, v in r.cookies.items():
                if k.startswith('download_warning'):
                    token = v
                    break
            if token:
                confirm_url = f"https://drive.google.com/uc?export=download&confirm={token}&id={file_id}"
                r = session.get(confirm_url, stream=True, timeout=60)

            ctype = r.headers.get("Content-Type", "")
            if "text/html" in ctype:
                html = r.text
                if "Quota exceeded" in html or "too many users" in html or "download quota" in html:
                    logging.error(f"❌ Quota Google Drive superata per: {url}")
                    return False

                m = re.search(r'href="([^"]*confirm=([^&"]+)[^"]*)"', html)
                if m:
                    confirm_url = "https://drive.google.com" + m.group(1).replace("&amp;", "&")
                    r = session.get(confirm_url, stream=True, timeout=60)
                    ctype = r.headers.get("Content-Type", "")

            if "text/html" in ctype:
                logging.error(f"❌ Google Drive conferma non risolta: {url} (tentativo {attempt}/{max_retries})")
                continue

            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(32768):
                    if chunk:
                        f.write(chunk)

            logging.info(f"✅ Scaricato da Google Drive: {dest_path}")
            return True
        except Exception as e:
            logging.error(f"❌ Errore GDrive ({attempt}/{max_retries}) {url}: {e}")
    return False

def _download_http(url: str, dest_path: str) -> bool:
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(r.content)
        logging.info(f"✅ Scaricato: {dest_path}")
        return True
    except Exception as e:
        logging.error(f"❌ Errore download {url}: {e}")
        return False

logging.basicConfig(level=logging.INFO)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

# === LINK CORRETTI PER TUTTI GLI SPORT ===
LINKS = {
    # ⚽ Calcio
    "soccer": [
        "https://drive.google.com/file/d/1wTlTM25ZdyB8W1AiqpGEPiCSDr8j5AfX/view?usp=sharing",
        "https://drive.google.com/file/d/11tSVFvOLlO15PKwfeD8EvuseSVZ3bLCx/view?usp=sharing",
        "https://drive.google.com/file/d/1b3GwAwcFrZo6Wl0k0qKQBM3HKZ1guxE4/view?usp=drive_link",
        "https://drive.google.com/file/d/1BgTAXO7Pbf7krU4VSqpe9mRNcFN1fpAU/view?usp=drive_link",
        "https://drive.google.com/file/d/1tZWqSSwql5EPd4ewkK4L-lr7vkdWDSyG/view?usp=drive_link",
        "https://drive.google.com/file/d/16e9fVPJOjKVXINpJLFeiEz51BIOKPW22/view?usp=drive_link",
        "https://drive.google.com/file/d/1dfXkJq7tW0_gEPtE_I1VQmrQmNptZr-B/view?usp=drive_link",
        "https://drive.google.com/file/d/1oGdZVCRRRd1bsr5aYerYCtr5ozChVEsb/view?usp=drive_link",
        "https://drive.google.com/file/d/1XnYsWx9z4cftPq7QsM9OjlWW_HAl_ATU/view?usp=drive_link",
        "https://drive.google.com/file/d/1RxWz1vdOBucb2MCIaiwJ781ud8w4w43Z/view?usp=drive_link",
        "https://drive.google.com/file/d/1o4BwSRoSWtRe75giJX5oPgOLE0p8aCQ_/view?usp=drive_link",
        "https://drive.google.com/file/d/1FM2zJUMNdv6a802hSwu_O78JTcyAOUYg/view?usp=drive_link",
        "https://drive.google.com/file/d/1J6klYEANGe4fKLra2C5KXApTBbGyGqlh/view?usp=drive_link",
        "https://drive.google.com/file/d/1UEXCOk7ftQktsJyVuwYYy_zmNi8SNO9O/view?usp=drive_link",
        "https://drive.google.com/file/d/1zxsOuE5XlyHCXaVPKk-QA0owntdBrrSn/view?usp=drive_link",
        "https://drive.google.com/file/d/1nvA7rGIQ89mIt57_QrfcYYXUMdyV2P5c/view?usp=drive_link",
        "https://drive.google.com/file/d/1mUBvukQzzHcMQejEIBt9hhVujHC1rTD5/view?usp=drive_link",
        "https://drive.google.com/file/d/1yGh9VBLtXi6Xpd7jjpUm7pUyy08_xoMq/view?usp=drive_link",
        "https://drive.google.com/file/d/1nfa_-cVX_W-IQ_h_7OXr6oSszgk4fr4h/view?usp=drive_link",
        "https://drive.google.com/file/d/1KOy7IBJhefHPvxJnbnCVSnMrFsClJ-XG/view?usp=drive_link",
        "https://drive.google.com/file/d/12700XBoabfEmP4Z5OM0eyPKw7rOPULD4/view?usp=drive_link",
        "https://drive.google.com/file/d/1RIcsAkKtci-YfdwHnFnOMhfaeBadszup/view?usp=drive_link",
        "https://drive.google.com/file/d/1NkVTEZ_s7IecTzQrS28OKrxWoJuDq0jK/view?usp=drive_link",
        "https://drive.google.com/file/d/1wl73AzeYwNS5mapuAifltDA3x5FYQyWZ/view?usp=drive_link",
    ],

    # 🏀 NBA
    "basketball_nba": [
        "https://drive.google.com/file/d/1zMdXKb_0Kgy734fl_J3cDZ7KOgCNM6Ng/view?usp=drive_link",
        "https://drive.google.com/file/d/1eSXgRXH9U7QrO5Q4LO6oA6pweyaCqsgF/view?usp=drive_link",
        "https://drive.google.com/file/d/1jRzPAg5Q-yHmJPqYliakxDmWnrpMCqu_/view?usp=drive_link",
        "https://drive.google.com/file/d/1XZ_fzreWKgSrt4Fdh6Dzooax3Bc0ZugF/view?usp=drive_link",
    ],

    # 🏈 NFL
    "americanfootball_nfl": [
        "https://drive.google.com/file/d/1c6mPo49iqxkl3Z2soKlJrY9wdF3874Jl/view?usp=drive_link",
        "https://drive.google.com/file/d/10HdPiazGdgoHhmAGFZWrltlTdbhHW-jg/view?usp=drive_link",
    ],

    # 🏈 NCAA
    "americanfootball_ncaaf": [
        "https://drive.google.com/file/d/1jdBb1FntwcUNEFsGcpsm_l4CfYvXmwxf/view?usp=drive_link",
        "https://drive.google.com/file/d/1mx56GF1c9t5TLb2jt4XpvcBUGNzG1hQL/view?usp=drive_link",
    ],
}

OUT_DIR = pathlib.Path("downloads")

def main():
    for group, urls in LINKS.items():
        base = OUT_DIR / group
        base.mkdir(parents=True, exist_ok=True)
        for url in urls:
            filename = url.split("/")[-1] or "file.csv"
            dest = base / filename

            success = False
            if "drive.google.com" in url:
                success = _download_google_drive(url, str(dest))
            else:
                success = _download_http(url, str(dest))

            if not success and "drive.google.com/file/d/" in url:
                file_id = _gdrive_extract_id(url)
                if file_id:
                    direct = f"https://drive.google.com/uc?export=download&id={file_id}"
                    dest2 = base / f"{file_id}.csv"
                    success2 = _download_google_drive(direct, str(dest2))
                    if not success2:
                        logging.error(f"❌ Fallito anche con link diretto: {direct}")
            elif not success:
                logging.error(f"❌ Download fallito per: {url}")

if __name__ == "__main__":
    main()
