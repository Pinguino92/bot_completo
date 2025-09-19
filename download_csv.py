import gdown
import os
import logging

# Configurazione logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Cartella di download
OUTPUT_DIR = "downloads"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Lista completa dei file Google Drive (Calcio, Basket, Football)
FILES = {
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
        "1oflc93SXwfeUp1hzpQSieyuogQ5p0R8-",
        "1sdIMsZKbLME04YjjftomMjPYj4nm7gTW",
    ]
}

def download_files():
    for category, file_ids in FILES.items():
        category_dir = os.path.join(OUTPUT_DIR, category)
        os.makedirs(category_dir, exist_ok=True)

        for file_id in file_ids:
            url = f"https://drive.google.com/uc?id={file_id}"
            output = os.path.join(category_dir, f"{file_id}.csv")
            try:
                logging.info(f"⬇️ Download {url} → {output}")
                gdown.download(url, output, quiet=False, fuzzy=True)
            except Exception as e:
                logging.error(f"❌ Errore download {url}: {e}")

if __name__ == "__main__":
    download_files()
    logging.info("✅ Download CSV completato!")

