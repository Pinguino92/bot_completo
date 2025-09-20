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
        "1IwH4OWw8K7d6lA6L_yOHDv0sPWzAjB7R",
        "1OvFQSfS818GvIrE668IceV2BxWpUwpPH",
        "1nuA3X9RR8nmHCiIJgHtYBNXSBfh5JVpz",
        "1Mu5mHX1iZ6DDty4yOsPBhYDBG4IV8tBo",
        "101leVcEblRX6SIZQ9IPYt3gBftfdTfU6",
        "1ZuKPIIPCH9aqwX80CpDb0-KGVcylYlRy",
        "1DCElGIAfJmpKcCWU6i2vcuCPs1No5orq",
        "1Wu9IG7QdmunqUw0duHVgCzzLlMXhSLE5",
        "18-IzszXSMuTehzogMXzCpEtXY4MX-3y7",
        "1rzjuCvl1FCY81BdUiFycC0doRUHtjjLR",
        "1wEjlzWU9e_B9VVtQQTXzRP9hXu7C_4SH",
        "1fjVYftn8Wzq5wVsgD1-9I3b1x8JsOhqK",
        "1UjdjPAGJYZvqGchWlrb3DWbBNl_eHuxN",
        "1c1WEcoUiGnvfs34Fs8EQQlwlHsNPnoTA",
        "10LQ4_jPdt3NG42MGPUbrRygmMXXChRvo",
        "1INKdlNQxnoyDuNhMIYwAe0LA1SxveDcC",
        "109b1Cw9xPCND3gDGBHElegMp6ky5Uk_h",
        "1Cv0zrXxbEV7pVT4tT2dMBaFwD4fKuiIT",
        "1f9jKgs5DcvUES_9KdaYdqyCP-L-7hNdS",
        "1MHk4DTUw2rzhCZMDFB7yCLwOc1HWHFmR",
        "1FN39YP3RwZsrgxC7n-Jlp5C9Yv6i-Zh_",
        "1x0nZkpMHAainZQsBgxsyjRghOgDfltIg",
        "1JE4DO2DH1dmE_N9zxKKkTFTUuWUyVMBV",
    ],
    "basket": [
        "1jW1s1ZsMPG9nqRSv7eMncSeYxGl7zaJ1",
        "17AbS759AvEYGqgHOZv1legV4cDi-eMfL",
        "1pag9i3by7rLo-4uq9VV2BkuDXzQA-cf3",
        "1ksnBEN0qVnJnkTsmw6c5aNM2Ijhp4TGh",
    ],
    "football": [
        "1M49rGXflx9jX5PnDP87JvI145f2lNEuU",
        "1DFDw8u6jtr-y9bTD2vqcZdw7Itn_gBeU",
        "1E0pqvpIx6PEX5MYNBcwVmQl1YwoSrFmb",
        "1_YyLl3lE5AcfLHJ6YXRP23SZrE7ei5GO",
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
