# download_csv.py
import os
import time
import logging
import re
from urllib.parse import urlparse, parse_qs
import gdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------- LINK GOOGLE DRIVE (come da tua lista) ----------
LINKS = {
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

# ---------- UTILS ----------
def ensure_dirs():
    for folder in ["downloads/calcio", "downloads/basket", "downloads/football"]:
        os.makedirs(folder, exist_ok=True)

def extract_file_id(link_or_id: str) -> str | None:
    """
    Accetta:
      - URL tipo .../uc?id=XXXX
      - URL tipo .../file/d/XXXX/view
      - Solo ID (alfanumerico con _ e -)
    Ritorna l'ID o None.
    """
    s = link_or_id.strip()
    if s.startswith("http"):
        parsed = urlparse(s)
        qs = parse_qs(parsed.query)
        if "id" in qs and qs["id"]:
            return qs["id"][0]
        m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", s)
        if m:
            return m.group(1)
    # Se sembra già un ID
    if re.fullmatch(r"[a-zA-Z0-9_-]{10,}", s):
        return s
    return None

def make_uc_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?id={file_id}"

def download_one(url_or_id: str, out_dir: str) -> tuple[bool, str]:
    """
    Prova a scaricare un file. Ritorna (ok, path_o_messaggio_errore).
    """
    fid = extract_file_id(url_or_id)
    if not fid:
        return False, f"ID non riconosciuto: {url_or_id}"
    url = make_uc_url(fid)
    out_path = os.path.join(out_dir, f"{fid}.csv")

    # due tentativi con gdown
    for attempt in range(1, 3):
        try:
            logging.info(f"⬇️ Download {url} → {out_path} (tentativo {attempt}/2)")
            gdown.download(url=url, output=out_path, quiet=False, use_cookies=False, fuzzy=True)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return True, out_path
        except Exception as e:
            time.sleep(1.5)

    return False, f"Failed to retrieve file url: {url}"

def main():
    ensure_dirs()
    total_ok = 0
    failed = []

    for sport, urls in LINKS.items():
        out_dir = os.path.join("downloads", sport)
        os.makedirs(out_dir, exist_ok=True)
        for u in urls:
            ok, msg = download_one(u, out_dir)
            if ok:
                total_ok += 1
            else:
                logging.error(f"❌ Errore download {u}: {msg}")
                failed.append((u, msg))

    logging.info("—" * 60)
    logging.info(f"✅ Download CSV completato! File scaricati: {total_ok}")
    if failed:
        logging.warning(f"⚠️ File falliti: {len(failed)}")
        for u, err in failed[:10]:
            logging.warning(f"- {u} -> {err}")
        if len(failed) > 10:
            logging.warning(f"... altri {len(failed)-10} errori non mostrati")

if __name__ == "__main__":
    main()
