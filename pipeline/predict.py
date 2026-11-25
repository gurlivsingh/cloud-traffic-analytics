"""Write predictions to RDS with the active model.

For each location:
  * backfill: 1-hour-ahead predictions for the last 48 hours (so the dashboard can show
    predicted vs actual right away)
  * future: the next PREDICT_HOURS hours, one hour at a time, feeding each prediction back
    in as the next lag (error grows with each step).
"""
import io
import logging

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import func, select

import cloud
import config
import db
from pipeline import congestion
from pipeline.features import build_features
from pipeline.train import load_records

log = logging.getLogger(__name__)
BACKFILL_HOURS = 48
_cache = {}


def active_model():
    with db.engine().connect() as conn:
        run = conn.execute(select(db.model_runs).where(db.model_runs.c.is_active)
                           .order_by(db.model_runs.c.id.desc()).limit(1)).first()
    if run is None:
        raise RuntimeError("no trained model yet - run: python -m pipeline.train")
    if run.s3_key not in _cache:
        _cache.clear()
        _cache[run.s3_key] = joblib.load(io.BytesIO(cloud.get_bytes(run.s3_key)))
    return _cache[run.s3_key], run.id


def predict_location(bundle, loc_id: int, cap: int, hours: int) -> list[dict]:
    model, feats = bundle["model"], bundle["features"]
    with db.engine().connect() as conn:
        last = conn.execute(select(func.max(db.traffic_records.c.ts))
                            .where(db.traffic_records.c.location_id == loc_id)).scalar()
    if last is None:
        return []
    hist = load_records(loc_id, since=pd.Timestamp(last) - pd.Timedelta(hours=168 + BACKFILL_HOURS + 4))
    out = []

    f = build_features(hist).tail(BACKFILL_HOURS)
    for ts, p in zip(f["ts"], np.clip(model.predict(f[feats]), 0, None)):
        out.append((ts, p))

    last_row = hist.sort_values("ts").iloc[-1]
    for h in range(1, hours + 1):
        ts = pd.Timestamp(last) + pd.Timedelta(hours=h)
        # shortcut: future weather = last observed weather, holiday = False; use a forecast API to upgrade
        new = dict(last_row, ts=ts, volume=np.nan, is_holiday=False)
        hist = pd.concat([hist.astype({"volume": float}), pd.DataFrame([new])], ignore_index=True)
        f = build_features(hist.tail(200), require_target=False)
        if f.empty or f["ts"].iloc[-1] != ts:
            break   # not enough recent history for lags
        p = float(np.clip(model.predict(f[feats].tail(1)), 0, None)[0])
        hist.loc[hist.index[-1], "volume"] = p
        out.append((ts, p))
    return [{"location_id": loc_id, "target_ts": ts.to_pydatetime(), "predicted_volume": int(round(p)),
             "predicted_level": congestion.level(p / cap)} for ts, p in out]


def main(hours: int = config.PREDICT_HOURS) -> int:
    bundle, run_id = active_model()
    with db.engine().connect() as conn:
        locs = conn.execute(select(db.locations.c.id, db.locations.c.capacity)).all()
    rows = []
    for loc_id, cap in locs:
        rows += [dict(r, model_run_id=run_id) for r in predict_location(bundle, loc_id, cap, hours)]
    n = db.upsert(db.predictions, rows, ["location_id", "target_ts"], update=True)
    log.info("wrote %d predictions for %d locations", n, len(locs))
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
