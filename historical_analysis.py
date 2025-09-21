# historical_analysis.py
import os
import logging
import pandas as pd

# Logging
logging.basicConfig(level=logging.INFO)

# Cartelle
DATA_DIR = "data"
OUTPUT_DIR = "processed"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def analyze_soccer(csv_file, league_name):
    """Analizza dataset di calcio (es. Serie A)"""
    try:
        df = pd.read_csv(csv_file)

        # Controlla colonne necessarie
        if not {"HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}.issubset(df.columns):
            logging.warning(f"{league_name}: formato CSV non valido")
            return None

        stats = {}

        # Win rates
        stats["home_win_rate"] = (df["FTR"] == "H").mean() * 100
        stats["draw_rate"] = (df["FTR"] == "D").mean() * 100
        stats["away_win_rate"] = (df["FTR"] == "A").mean() * 100

        # Goal stats
        stats["avg_home_goals"] = df["FTHG"].mean()
        stats["avg_away_goals"] = df["FTAG"].mean()

        # Over/Under 2.5
        stats["over25_rate"] = ((df["FTHG"] + df["FTAG"]) > 2.5).mean() * 100
        stats["under25_rate"] = ((df["FTHG"] + df["FTAG"]) <= 2.5).mean() * 100

        # Both teams to score
        stats["btts_rate"] = ((df["FTHG"] > 0) & (df["FTAG"] > 0)).mean() * 100

        # Salva
        out_file = os.path.join(OUTPUT_DIR, f"{league_name}_soccer_stats.json")
        pd.Series(stats).to_json(out_file, indent=2)
        logging.info(f"✅ Salvato {out_file}")
        return stats

    except Exception as e:
        logging.error(f"Errore analisi {league_name}: {e}")
        return None


def analyze_nfl(csv_file, league_name="NFL"):
    """Analizza dataset NFL"""
    try:
        df = pd.read_csv(csv_file)

        # Controlla colonne necessarie
        if not {"HomeTeam", "AwayTeam", "HomeScore", "AwayScore"}.issubset(df.columns):
            logging.warning(f"{league_name}: formato CSV non valido")
            return None

        stats = {}

        # Win rates
        stats["home_win_rate"] = (df["HomeScore"] > df["AwayScore"]).mean() * 100
        stats["away_win_rate"] = (df["AwayScore"] > df["HomeScore"]).mean() * 100

        # Average points
        stats["avg_home_points"] = df["HomeScore"].mean()
        stats["avg_away_points"] = df["AwayScore"].mean()
        stats["avg_total_points"] = (df["HomeScore"] + df["AwayScore"]).mean()

        # Over/Under 42.5 (esempio NFL comune)
        stats["over42.5_rate"] = ((df["HomeScore"] + df["AwayScore"]) > 42.5).mean() * 100
        stats["under42.5_rate"] = ((df["HomeScore"] + df["AwayScore"]) <= 42.5).mean() * 100

        # Salva
        out_file = os.path.join(OUTPUT_DIR, f"{league_name}_nfl_stats.json")
        pd.Series(stats).to_json(out_file, indent=2)
        logging.info(f"✅ Salvato {out_file}")
        return stats

    except Exception as e:
        logging.error(f"Errore analisi {league_name}: {e}")
        return None


if __name__ == "__main__":
    logging.info("📊 Avvio analisi storica...")

    # ESEMPIO: qui puoi inserire i tuoi file locali
    analyze_soccer("calcio_I1.csv", "SerieA")
    analyze_nfl("NFL_2017-2025_scores.csv", "NFL")
