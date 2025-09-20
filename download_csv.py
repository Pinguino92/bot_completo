import os
import logging
import gdown

# Logging
logging.basicConfig(level=logging.INFO)

# Cartelle di destinazione
FOLDERS = {
    "calcio": "downloads/calcio",
    "basket": "downloads/basket",
    "football": "downloads/football",
}

# Link Google Drive definitivi
CSV_LINKS = {
    "calcio": [
        "https://drive.google.com/uc?id=1IwH4OWw8K7d6lA6L_yOHDv0sPWzAjB7R",
        "https://drive.google.com/uc?id=1OvFQSfS818GvIrE668IceV2BxWpUwpPH",
        "https://drive.google.com/uc?id=1nuA3X9RR8nmHCiIJgHtYBNXSBfh5JVpz",
        "https://drive.google.com/uc?id=1Mu5mHX1iZ6DDty4yOsPBhYDBG4IV8tBo",
        "https://drive.google.com/uc?id=101leVcEblRX6SIZQ9IPYt3gBftfdTfU6",
        "https://drive.google.com/uc?id=1ZuKPIIPCH9aqwX80CpDb0-KGVcylYlRy",
        "https://drive.google.com/uc?id=1DCElGIAfJmpKcCWU6i2vcuCPs1No5orq",
        "https://drive.google.com/uc?id=1Wu9IG7QdmunqUw0duHVgCzzLlMXhSLE5",
        "https://drive.google.com/uc?id=18-IzszXSMuTehzogMXzCpEtXY4MX-3y7",
        "https://drive.google.com/uc?id=1rzjuCvl1FCY81BdUiFycC0doRUHtjjLR",
        "https://drive.google.com/uc?id=1wEjlzWU9e_B9VVtQQTXzRP9hXu7C_4SH",
        "https://drive.google.com/uc?id=1fjVYftn8Wzq5wVsgD1-9I3b1x8JsOhqK",
        "https://drive.google.com/uc?id=1UjdjPAGJYZvqGchWlrb3DWbBNl_eHuxN",
        "https://drive.google.com/uc?id=1c1WEcoUiGnvfs34Fs8EQQlwlHsNPnoTA",
        "https://drive.google.com/uc?id=10LQ4_jPdt3NG42MGPUbrRygmMXXChRvo",
        "https://drive.google.com/uc?id=1INKdlNQxnoyDuNhMIYwAe0LA1SxveDcC",
        "https://drive.google.com/uc?id=109b1Cw9xPCND3gDGBHElegMp6ky5Uk_h",
        "https://drive.google.com/uc?id=1Cv0zrXxbEV7pVT4tT2dMBaFwD4fKuiIT",
        "https://drive.google.com/uc?id=1f9jKgs5DcvUES_9KdaYdqyCP-L-7hNdS",
        "https://drive.google.com/uc?id=1MHk4DTUw2rzhCZMDFB7yCLwOc1HWHFmR",
        "https://drive.google.com/uc?id=1FN39YP3RwZsrgxC7n-Jlp5C9Yv6i-Zh_",
        "https://drive.google.com/uc?id=1x0nZkpMHAainZQsBgxsyjRghOgDfltIg",
        "https://drive.google.com/uc?id=1JE4DO2DH1dmE_N9zxKKkTFTUuWUyVMBV",
        "https://drive.google.com/uc?id=1UCba1YBdJknDRQQTmjrsy3nmZIRxT87_",
    ],
    "basket": [
        "https://drive.google.com/uc?id=1jW1s1ZsMPG9nqRSv7eMncSeYxGl7zaJ1",
        "https://drive.google.com/uc?id=17AbS759AvEYGqgHOZv1legV4cDi-eMfL",
        "https://drive.google.com/uc?id=1pag9i3by7rLo-4uq9VV2BkuDXzQA-cf3",
        "https://drive.google.com/uc?id=1ksnBEN0qVnJnkTsmw6c5aNM2Ijhp4TGh",
    ],
    "football": [
        "https://drive.google.com/uc?id=1M49rGXflx9jX5PnDP87JvI145f2lNEuU",
        "https://drive.google.com/uc?id=1DFDw8u6jtr-y9bTD2vqcZdw7Itn_gBeU",
        "https://drive.google.com/uc?id=1E0pqvpIx6PEX5MYNBcwVmQl1YwoSrFmb",
        "https://drive.google.com/uc?id=1_YyLl3lE5AcfLHJ6YXRP23SZrE7ei5GO",
    ],
}

def ensure_folders():
    """Crea cartelle se non esistono"""
    for folder in FOLDERS.values():
        os.makedirs(folder, exist_ok=True)

def download_csv():
    """Scarica tutti i CSV nelle rispettive cartelle"""
    ensure_folders()
    for sport, links in CSV_LINKS.items():
        folder = FOLDERS[sport]
        for url in links:
            try:
                file_id = url.split("id=")[-1]
                output = os.path.join(folder, f"{file_id}.csv")
                logging.info(f"⬇️ Download {url} → {output}")
                gdown.download(url, output, quiet=False)
            except Exception as e:
                logging.error(f"❌ Errore download {url}: {e}")

if __name__ == "__main__":
    download_csv()
    logging.info("✅ Download CSV completato!")
