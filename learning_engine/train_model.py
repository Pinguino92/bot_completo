import os, pandas as pd, joblib, logging
from sklearn.ensemble import RandomForestClassifier

MODEL_PATH = "/data/learning_engine"
os.makedirs(MODEL_PATH, exist_ok=True)

def train_model():
    csv_path = "/data/results_log.csv"
    if not os.path.exists(csv_path):
        return
    df = pd.read_csv(csv_path)
    df = df[df["outcome_result"].isin(["W","L"])]
    if len(df) < 20:
        return
    df["target"] = (df["outcome_result"]=="W").astype(int)
    X = df[["price","prob_final"]]
    y = df["target"]
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X,y)
    joblib.dump(model, os.path.join(MODEL_PATH,"model.pkl"))
    logging.info("🤖 modello ML aggiornato.")

def ai_correction(prob_final, price):
    try:
        model = joblib.load(os.path.join(MODEL_PATH,"model.pkl"))
        pred = model.predict_proba([[price,prob_final]])[0][1]
        return round(100*pred,1)
    except Exception:
        return prob_final
