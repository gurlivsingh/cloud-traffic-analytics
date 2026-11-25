"""ETL: S3 raw/ CSV  ->  clean + congestion  ->  S3 processed/  +  RDS traffic_records.

Accepts two CSV formats:
  1. the UCI "Metro Interstate Traffic Volume" file as downloaded (date_time, traffic_volume, ...)
  2. our canonical format: location, ts, volume [, lat, lon, is_synthetic, speed, occupancy,
     temp, rain, snow, clouds, weather_main, is_holiday]
"""
import io
import logging
import time
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import select, update

import cloud
import db
from pipeline import congestion

log = logging.getLogger(__name__)

UCI_LOCATION = {"location": "I-94 Westbound, Minneapolis-St Paul (real)", "lat": 44.962, "lon": -93.196}
CANONICAL = ["location", "lat", "lon", "is_synthetic", "ts", "volume", "speed", "occupancy",
             "temp", "rain", "snow", "clouds", "weather_main", "is_holiday"]


def read_csv_bytes(data: bytes, key: str) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(data), compression="gzip" if key.endswith(".gz") else None)


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Convert either supported format to the canonical columns. Raises ValueError if neither."""
    if {"date_time", "traffic_volume"} <= set(df.columns):
        ts = pd.to_datetime(df["date_time"])
        # UCI marks a holiday only on its midnight row -> spread it to the whole day.
        hol = df.get("holiday", pd.Series(index=df.index, dtype=object))
        hol_dates = set(ts[hol.notna() & (hol.astype(str) != "None")].dt.date)
        temp = df["temp"].astype(float).replace(0, np.nan) - 273.15     # Kelvin -> Celsius, 0 K = bad sensor
        out = pd.DataFrame({
            **{k: v for k, v in UCI_LOCATION.items()}, "is_synthetic": False,
            "ts": ts, "volume": df["traffic_volume"], "speed": np.nan, "occupancy": np.nan,
            "temp": temp, "rain": df["rain_1h"], "snow": df["snow_1h"], "clouds": df["clouds_all"],
            "weather_main": df["weather_main"], "is_holiday": ts.dt.date.isin(hol_dates)})
    elif {"location", "ts", "volume"} <= set(df.columns):
        out = df.copy()
        out["ts"] = pd.to_datetime(out["ts"])
        for c in CANONICAL:
            if c not in out:
                out[c] = False if c in ("is_synthetic", "is_holiday") else np.nan
    else:
        raise ValueError("CSV must have either (date_time, traffic_volume, ...) UCI columns "
                         "or (location, ts, volume) columns")
    return out[CANONICAL]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = df[df["volume"].notna() & (df["volume"] >= 0) & df["ts"].notna()]
    df.loc[df["rain"] > 100, "rain"] = np.nan                       # mm/hour; UCI has one 9831 mm outlier
    df = df.sort_values(["location", "ts"]).drop_duplicates(["location", "ts"])  # UCI repeats hours per weather tag
    df[["temp", "rain", "snow", "clouds", "weather_main"]] = (
        df.groupby("location")[["temp", "rain", "snow", "clouds", "weather_main"]].ffill())
    df["volume"] = df["volume"].astype(int)
    df["location"] = df["location"].astype(str).str.strip().str[:120]
    return df.reset_index(drop=True)


def _location_ids(df: pd.DataFrame) -> dict:
    """Create missing locations (capacity from this file) and return {name: (id, capacity)}."""
    first = df.groupby("location").agg(lat=("lat", "first"), lon=("lon", "first"),
                                       is_synthetic=("is_synthetic", "first"))
    rows = [{"name": n, "lat": None if pd.isna(r.lat) else float(r.lat),
             "lon": None if pd.isna(r.lon) else float(r.lon), "is_synthetic": bool(r.is_synthetic)}
            for n, r in first.iterrows()]
    db.upsert(db.locations, rows, ["name"])
    with db.engine().begin() as conn:
        found = {r.name: [r.id, r.capacity] for r in conn.execute(
            select(db.locations).where(db.locations.c.name.in_(list(first.index))))}
        for name, r in found.items():
            if r[1] is None:
                r[1] = congestion.capacity(df.loc[df["location"] == name, "volume"])
                conn.execute(update(db.locations).where(db.locations.c.id == r[0]).values(capacity=r[1]))
    return found


def load(df: pd.DataFrame) -> int:
    ids = _location_ids(df)
    df = df.copy()
    df["location_id"] = df["location"].map(lambda n: ids[n][0])
    cap = df["location"].map(lambda n: ids[n][1])
    df["congestion_index"] = (df["volume"] / cap).round(3)
    df["congestion_level"] = [congestion.level(v) for v in df["congestion_index"]]
    cols = [c.name for c in db.traffic_records.columns if c.name != "id"]
    out = df[cols].astype(object).where(df[cols].notna(), None)
    return db.upsert(db.traffic_records, out.to_dict("records"), ["location_id", "ts"])


def process_key(key: str) -> int:
    """Run the full ETL for one raw/ object. Logs a pipeline_runs row either way."""
    started = datetime.now()
    t0 = time.time()
    with db.engine().begin() as conn:
        run_id = conn.execute(db.pipeline_runs.insert().values(
            s3_key=key, started_at=started, status="running")).inserted_primary_key[0]
    rows_in = loaded = 0
    try:
        df = clean(normalize(read_csv_bytes(cloud.get_bytes(key), key)))
        rows_in = len(df)
        out_key = "processed/" + key.split("/", 1)[1].replace(".csv", "").replace(".gz", "") + ".csv.gz"
        cloud.put_bytes(out_key, _gzip_csv(df))
        loaded = load(df)
        status, error = "ok", None
    except Exception as e:  # noqa: BLE001 - record the failure, then re-raise below
        status, error = "failed", f"{type(e).__name__}: {e}"[:2000]
        log.exception("ETL failed for %s", key)
    with db.engine().begin() as conn:
        conn.execute(update(db.pipeline_runs).where(db.pipeline_runs.c.id == run_id).values(
            finished_at=datetime.now(), rows_in=rows_in, rows_loaded=loaded, status=status, error=error))
    cloud.put_metric("RowsLoaded", loaded)
    cloud.put_metric("PipelineDurationSec", time.time() - t0, "Seconds")
    if status == "failed":
        cloud.put_metric("PipelineFailures", 1)
        raise RuntimeError(error)
    log.info("ETL %s: %d rows in, %d new rows loaded", key, rows_in, loaded)
    return loaded


def _gzip_csv(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_csv(buf, index=False, compression="gzip")
    return buf.getvalue()


def pending_keys() -> list[str]:
    with db.engine().connect() as conn:
        done = {r[0] for r in conn.execute(select(db.pipeline_runs.c.s3_key).where(db.pipeline_runs.c.status == "ok"))}
    return [k for k in cloud.list_keys("raw/") if k.endswith((".csv", ".csv.gz")) and k not in done]
