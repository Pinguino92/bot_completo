import os
import logging
import gdown
import pandas as pd

# Cartelle
DOWNLOAD_DIR = "downloads"
LOCAL_DATA_DIR = "data"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(LOCAL_DATA_DIR, exist_ok=True)

# 🔗 Link Google Drive (se vuoi ancora mantenerli)
GOOGLE_DRIVE_LINKS = {
    "calcio": [
        # Esempio
        "https://drive.google.com/uc?id=1IwH4OWw8K7d6lA6L_yOHDv0sPWzAjB7R",
        "https://drive.google.com/uc?id=1OvFQSfS818GvIrE668IceV2BxWpUwpPH",
        # ... continua con gli altri link ...
    ],
    "basket": [
        "https://drive.google.com/uc?id=1jW1s1ZsMPG9nqRSv7eMncSeYxGl7zaJ1",
        # ...
    ],
    "football": [
        "https://drive.google.com/uc?id=1M49rGXflx9jX5PnDP87JvI145f2lNEuU",
        # ...
    ]
}

def scarica_google_drive():
    """Scarica i CSV da Google Drive"""
    for sport, links in GOOGLE_DRIVE_LINKS.items():
        sport_dir = os.path.join(DOWNLOAD_DIR, sport)
        os.makedirs(sport_dir, exist_ok=True)

        for url in links:
            file_id = url.split("id=")[-1]
            dest = os.path.join(sport_dir, f"{file_id}.csv")
            if not os.path.exists(dest):
                logging.info(f"⬇️ Download {url} → {dest}")
                try:
                    gdown.download(url, dest, quiet=False)
                except Exception as e:
                    logging.error(f"❌ Errore download {url}: {e}")

def carica_csv_locale():
    """Legge tutti i CSV presenti nella cartella data/"""
    files = [f for f in os.listdir(LOCAL_DATA_DIR) if f.endswith(".csv")]
    if not files:
        logging.warning("⚠️ Nessun CSV trovato in data/")
    for f in files:
        path = os.path.join(LOCAL_DATA_DIR, f)
        logging.info(f"📂 CSV locale trovato: {path}")
        try:
            df = pd.read_csv(path)
            logging.info(f"   → Letto correttamente con {len(df)} righe")
        except Exception as e:
            logging.error(f"❌ Errore lettura {path}: {e}")

if __name__ == "__main__":
    scarica_google_drive()
    carica_csv_locale()
    logging.info("✅ Download + Lettura CSV completato!")
