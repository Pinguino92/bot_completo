import os
import time
import logging
import re
from typing import List, Dict, Tuple
import gdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# === URL definitivi (copiati da Google Drive) ===
DRIVE_LINKS: Dict[str, List[str]] = {
    "calcio": [
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
    "basket": [
        "https://drive.google.com/file/d/1zMdXKb_0Kgy734fl_J3cDZ7KOgCNM6Ng/view?usp=drive_link",
        "https://drive.google.com/file/d/1eSXgRXH9U7QrO5Q4LO6oA6pweyaCqsgF/view?usp=drive_link",
        "https://drive.google.com/file/d/1jRzPAg5Q-yHmJPqYliakxDmWnrpMCqu_/view?usp=drive_link",
        "https://drive.google.com/file/d/1XZ_fzreWKgSrt4Fdh6Dzooax3Bc0ZugF/view?usp=drive_link",
    ],
    "football": [
        "https://drive.google.com/file/d/1c6mPo49iqxkl3Z2soKlJrY9wdF3874Jl/view?usp=drive_link",
        "https://drive.google.com/file/d/10HdPiazGdgoHhmAGFZWrltlTdbhHW-jg/view?usp=drive_link",
        "https://drive.google.com/file/d/1jdBb1FntwcUNEFsGcpsm_l4CfYvXmwxf/view?usp=drive_link",
        "https://drive.google.com/file/d/1mx56GF1c9t5TLb2jt4XpvcBUGNzG1hQL/view?usp=drive_link",
    ],
}

OUT_BASE = "downloads"

def ensure_dirs():
    for cat in DRIVE_LINKS.keys():
        os.makedirs(os.path.join(OUT_BASE, cat), exist_ok=True)

def extract_id(url: str) -> str:
    """Estrae l'ID da link Google Drive"""
    m = re.search(r"/d/([a-zA-Z0-9\-_]+)", url)
    if m:
        return m.group(1)
    return ""

def download_with_retries(file_id: str, dest_path: str, attempts: int = 3) -> Tuple[bool, str]:
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    last_err = ""
    for attempt in range(1, attempts + 1):
        logging.info(f"⬇️ Download {url} → {dest_path} (tentativo {attempt}/{attempts})")
        try:
            out = gdown.download(url=url, output=dest_path, quiet=False, fuzzy=True, use_cookies=False)
            if out and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                return True, ""
            last_err = "File vuoto o path non creato"
        except Exception as e:
            last_err = str(e)
        time.sleep(2 * attempt)
    return False, last_err

def main():
    ensure_dirs()
    total_ok, total_fail = 0, 0
    failed_items = []

    for category, links in DRIVE_LINKS.items():
        out_dir = os.path.join(OUT_BASE, category)
        for link in links:
            file_id = extract_id(link)
            if not file_id:
                logging.error(f"❌ ID non riconosciuto: {link}")
                total_fail += 1
                failed_items.append((category, link, "ID non valido"))
                continue
            dest = os.path.join(out_dir, f"{file_id}.csv")
            ok, err = download_with_retries(file_id, dest, attempts=3)
            if ok:
                total_ok += 1
            else:
                total_fail += 1
                logging.error(f"❌ Errore download {link}: {err}")
                failed_items.append((category, link, err))

    logging.info(f"✅ Scaricati: {total_ok} | ❌ Falliti: {total_fail}")
    if failed_items:
        for cat, link, err in failed_items:
            logging.warning(f"[{cat}] {link} → {err}")

if __name__ == "__main__":
    main()
