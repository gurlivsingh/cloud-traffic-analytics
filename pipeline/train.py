"""Train baseline vs Linear Regression vs Random Forest on RDS data; save the best model to S3.

Split is by TIME (last 15% of the timeline is the test set) - a random split would leak future
hours into training and give fake-good scores.
"""
import io
import json
import logging
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select, update

import cloud
import db
from pipeline import congestion
from pipeline.features import FEATURES, build_features

log = logging.getLogger(__name__)
METRICS_KEY = "models/metrics_latest.json"


def load_records(location_id=None, since=None) -> pd.DataFrame:
    t = db.traffic_records
    q = select(t.c.location_id, t.c.ts, t.c.volume, t.c.temp, t.c.rain, t.c.snow, t.c.clouds,
               t.c.weather_main, t.c.is_holiday)
    if location_id is not None:
        q = q.where(t.c.location_id == location_id)
    if since is not None:
        q = q.where(t.c.ts >= since)
    with db.engine().connect() as conn:
        df = pd.read_sql(q, conn)
    df.columns = [str(c) for c in df.columns]   # SQLAlchemy quoted_name -> str, sklearn needs plain str
    df["ts"] = pd.to_datetime(df["ts"])
    return df


def capacities() -> dict:
    with db.engine().connect() as conn:
        return dict(conn.execute(select(db.locations.c.id, db.locations.c.capacity)).all())


def evaluate(name, y, pred, test, caps) -> dict:
    cap = test["location_id"].map(caps).to_numpy()
    actual_lv = [congestion.level(v) for v in y / cap]
    pred_lv = [congestion.level(v) for v in pred / cap]
    return {"model": name,
            "mae": round(float(mean_absolute_error(y, pred)), 1),
            "rmse": round(float(np.sqrt(mean_squared_error(y, pred))), 1),
            "r2": round(float(r2_score(y, pred)), 4),
            "level_accuracy": round(float(np.mean(np.array(actual_lv) == np.array(pred_lv))), 4)}


def main() -> dict:
    f = build_features(load_records())
    if len(f) < 500:
        raise RuntimeError(f"only {len(f)} usable rows - load more data before training")
    cutoff = f["ts"].quantile(0.85)
    train, test = f[f["ts"] < cutoff], f[f["ts"] >= cutoff]
    X_tr, y_tr, X_te, y_te = train[FEATURES], train["volume"], test[FEATURES], test["volume"].to_numpy()
    caps = capacities()

    results = [evaluate("Baseline (same hour last week)", y_te, test["lag_168h"].to_numpy(), test, caps)]
    models = {
        "Linear Regression": make_pipeline(StandardScaler(), LinearRegression()),
        # depth/leaf limits keep the model small enough for a 1 GB t3.micro
        "Random Forest": RandomForestRegressor(n_estimators=60, max_depth=14, min_samples_leaf=3,
                                               n_jobs=-1, random_state=42),
    }
    preds = {}
    for name, m in models.items():
        log.info("training %s on %d rows", name, len(X_tr))
        m.fit(X_tr, y_tr)
        preds[name] = np.clip(m.predict(X_te), 0, None)
        results.append(evaluate(name, y_te, preds[name], test, caps))

    best = min((r for r in results if r["model"] in models), key=lambda r: r["rmse"])["model"]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    key = f"models/{best.lower().replace(' ', '_')}_{stamp}.joblib"
    buf = io.BytesIO()
    joblib.dump({"model": models[best], "features": FEATURES, "name": best}, buf, compress=3)
    cloud.put_bytes(key, buf.getvalue())

    rf = models["Random Forest"]
    sample = np.random.default_rng(0).choice(len(y_te), size=min(400, len(y_te)), replace=False)
    metrics = {
        "trained_at": stamp, "best_model": best, "model_key": key,
        "train_rows": len(train), "test_rows": len(test),
        "train_period": [str(train["ts"].min()), str(train["ts"].max())],
        "test_period": [str(test["ts"].min()), str(test["ts"].max())],
        "results": results,
        "feature_importance": sorted(
            [{"feature": c, "importance": round(float(v), 4)} for c, v in zip(FEATURES, rf.feature_importances_)],
            key=lambda d: -d["importance"])[:15],
        "scatter": [{"actual": int(y_te[i]), "predicted": int(preds[best][i])} for i in sample],
    }
    body = json.dumps(metrics, indent=2).encode()
    cloud.put_bytes(METRICS_KEY, body)
    cloud.put_bytes(f"models/metrics_{stamp}.json", body)

    with db.engine().begin() as conn:
        conn.execute(update(db.model_runs).values(is_active=False))
        for r in results:
            conn.execute(db.model_runs.insert().values(
                model_name=r["model"], mae=r["mae"], rmse=r["rmse"], r2=r["r2"],
                level_accuracy=r["level_accuracy"], train_rows=len(train), test_rows=len(test),
                s3_key=key if r["model"] == best else None, is_active=r["model"] == best))
    cloud.put_metric("ModelRMSE", next(r["rmse"] for r in results if r["model"] == best), "None")
    log.info("results: %s -> active model %s (%s)", results, best, key)
    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
