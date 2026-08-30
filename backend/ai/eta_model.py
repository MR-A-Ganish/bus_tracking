"""
AI-based ETA prediction module (prototype).

This is a REAL machine learning model, not a fixed "5 minutes per stop"
formula. It is intentionally simple (a RandomForestRegressor with 4 features)
so it stays explainable in a final-year project review, while still being a
genuine trained model rather than a hardcoded rule.

Because real bus-GPS history is not available for this prototype, we
generate a synthetic training dataset (training_data.csv) using a
physics-based formula PLUS random noise, which mimics how travel time in the
real world depends on distance, traffic and stops. The model is then trained
on that generated data. This is clearly a limitation of the prototype and is
documented as such (see README.md and the "is_prototype" flag returned by
predict_eta()).

Features used:
    - distance_km          : remaining distance to the target stop (km)
    - avg_speed_kmph        : the bus's current average speed
    - traffic_condition     : 0 = low, 1 = medium, 2 = high
    - stops_remaining        : number of stops left before the target stop

Target:
    - actual_travel_time_min : how long the trip actually took (minutes)
"""

import os
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import joblib

MODEL_PATH = os.path.join(os.path.dirname(__file__), "eta_model.joblib")
DATA_PATH = os.path.join(os.path.dirname(__file__), "training_data.csv")

TRAFFIC_MAP = {"low": 0, "medium": 1, "high": 2}
TRAFFIC_DELAY_FACTOR = {0: 1.0, 1: 1.25, 2: 1.6}  # traffic slows the bus down


def generate_training_data(n_samples=800, seed=42):
    """
    Create a synthetic but realistic dataset:
    base_time = distance / speed * 60 (minutes), then scaled by a traffic
    delay factor and a small random variation to imitate real-world noise
    (driver behaviour, minor stoppages, weather, etc).
    """
    rng = np.random.default_rng(seed)

    distance_km = rng.uniform(0.5, 26.0, n_samples)
    avg_speed_kmph = rng.uniform(15, 45, n_samples)
    traffic_condition = rng.integers(0, 3, n_samples)  # 0,1,2
    stops_remaining = rng.integers(0, 5, n_samples)

    base_time_min = (distance_km / avg_speed_kmph) * 60
    traffic_factor = np.array([TRAFFIC_DELAY_FACTOR[t] for t in traffic_condition])
    stop_delay_min = stops_remaining * rng.uniform(1.0, 2.5, n_samples)  # boarding time per stop
    noise = rng.normal(0, 1.2, n_samples)

    actual_travel_time_min = np.clip(
        base_time_min * traffic_factor + stop_delay_min + noise, 0.5, None
    )

    df = pd.DataFrame({
        "distance_km": distance_km,
        "avg_speed_kmph": avg_speed_kmph,
        "traffic_condition": traffic_condition,
        "stops_remaining": stops_remaining,
        "actual_travel_time_min": actual_travel_time_min,
    })
    df.to_csv(DATA_PATH, index=False)
    return df


def train_model():
    """Train (or re-train) the RandomForestRegressor and save it to disk."""
    if not os.path.exists(DATA_PATH):
        df = generate_training_data()
    else:
        df = pd.read_csv(DATA_PATH)

    X = df[["distance_km", "avg_speed_kmph", "traffic_condition", "stops_remaining"]]
    y = df["actual_travel_time_min"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)

    joblib.dump(model, MODEL_PATH)

    feature_importance = dict(zip(X.columns, model.feature_importances_.round(3)))
    print(f"[eta_model] Trained RandomForestRegressor. Test MAE = {mae:.2f} min")
    print(f"[eta_model] Feature importance: {feature_importance}")
    return model, mae


def load_model():
    if not os.path.exists(MODEL_PATH):
        model, _ = train_model()
        return model
    return joblib.load(MODEL_PATH)


_model_cache = None


def predict_eta(distance_km, avg_speed_kmph, traffic_condition, stops_remaining):
    """
    Predict ETA in minutes for a bus that is `distance_km` away from the
    target stop, travelling at `avg_speed_kmph`, under `traffic_condition`
    ('low' | 'medium' | 'high'), with `stops_remaining` intermediate stops
    left before reaching the target.

    Returns a dict: {"eta_minutes": float, "is_prototype": True}
    """
    global _model_cache
    if _model_cache is None:
        _model_cache = load_model()

    traffic_val = TRAFFIC_MAP.get(traffic_condition, 0)
    distance_km = max(distance_km, 0.05)
    avg_speed_kmph = max(avg_speed_kmph, 5)

    X = pd.DataFrame([{
        "distance_km": distance_km,
        "avg_speed_kmph": avg_speed_kmph,
        "traffic_condition": traffic_val,
        "stops_remaining": stops_remaining,
    }])

    eta = float(_model_cache.predict(X)[0])
    return {
        "eta_minutes": round(eta, 1),
        "is_prototype": True,
        "model": "RandomForestRegressor (trained on generated sample data)",
    }


if __name__ == "__main__":
    # Run this file directly to (re)generate data and train the model:
    #   python ai/eta_model.py
    generate_training_data()
    train_model()
