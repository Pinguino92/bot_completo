import gdown
import os

# Cartelle locali
os.makedirs("data/soccer", exist_ok=True)
os.makedirs("data/basketball", exist_ok=True)
os.makedirs("data/football", exist_ok=True)

# Lista CSV Google Drive (sostituisci con i tuoi link)
links = [
    # Calcio
    "https://drive.google.com/uc?id=1IwH4OWw8K7d6lA6L_yOHDv0sPWzAjB7R",
    # Basket
    "https://drive.google.com/uc?id=1jW1s1ZsMPG9nqRSv7eMncSeYxGl7zaJ1",
    # Football
    "https://drive.google.com/uc?id=1M49rGXflx9jX5PnDP87JvI145f2lNEuU"
]

for url in links:
    try:
        gdown.download(url, quiet=False)
    except Exception as e:
        print(f"Errore download {url}: {e}")
