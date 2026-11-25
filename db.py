"""Database schema and helpers. PostgreSQL on RDS in the cloud, SQLite locally."""
from functools import lru_cache

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer, MetaData, String, Table,
                        Text, UniqueConstraint, create_engine, func, select)
from sqlalchemy.engine import URL

import cloud
import config

metadata = MetaData()

locations = Table(
    "locations", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), unique=True, nullable=False),
    Column("lat", Float), Column("lon", Float),
    Column("capacity", Integer),            # 95th percentile of hourly volume (proxy for road capacity)
    Column("is_synthetic", Boolean, default=False),
)

traffic_records = Table(
    "traffic_records", metadata,
    Column("id", Integer, primary_key=True),
    Column("location_id", Integer, ForeignKey("locations.id"), nullable=False),
    Column("ts", DateTime, nullable=False),
    Column("volume", Integer, nullable=False),
    Column("speed", Float), Column("occupancy", Float),
    Column("temp", Float), Column("rain", Float), Column("snow", Float), Column("clouds", Float),
    Column("weather_main", String(40)),
    Column("is_holiday", Boolean),
    Column("congestion_index", Float),
    Column("congestion_level", String(12)),
    UniqueConstraint("location_id", "ts", name="uq_record_location_ts"),   # makes re-loads idempotent
)

model_runs = Table(
    "model_runs", metadata,
    Column("id", Integer, primary_key=True),
    Column("model_name", String(40)),
    Column("trained_at", DateTime, server_default=func.now()),
    Column("mae", Float), Column("rmse", Float), Column("r2", Float), Column("level_accuracy", Float),
    Column("train_rows", Integer), Column("test_rows", Integer),
    Column("s3_key", String(255)),
    Column("is_active", Boolean, default=False),
)

predictions = Table(
    "predictions", metadata,
    Column("id", Integer, primary_key=True),
    Column("location_id", Integer, ForeignKey("locations.id"), nullable=False),
    Column("target_ts", DateTime, nullable=False),
    Column("predicted_volume", Integer),
    Column("predicted_level", String(12)),
    Column("model_run_id", Integer, ForeignKey("model_runs.id")),
    Column("created_at", DateTime, server_default=func.now()),
    UniqueConstraint("location_id", "target_ts", name="uq_prediction_location_ts"),
)

pipeline_runs = Table(
    "pipeline_runs", metadata,
    Column("id", Integer, primary_key=True),
    Column("s3_key", String(255)),
    Column("started_at", DateTime), Column("finished_at", DateTime),
    Column("rows_in", Integer), Column("rows_loaded", Integer),
    Column("status", String(20)),
    Column("error", Text),
)


def _url():
    if not config.DB_HOST:
        return f"sqlite:///{config.SQLITE_PATH}"
    password = cloud.get_secret("DB_PASSWORD", config.DB_PASSWORD_PARAM)
    if not password:
        raise RuntimeError("DB password not found in env DB_PASSWORD or SSM " + config.DB_PASSWORD_PARAM)
    return URL.create("postgresql+psycopg2", username=config.DB_USER, password=password,
                      host=config.DB_HOST, port=5432, database=config.DB_NAME)


@lru_cache(maxsize=None)
def engine():
    eng = create_engine(_url(), pool_pre_ping=True)
    metadata.create_all(eng)
    return eng


def upsert(table, rows: list[dict], conflict_cols: list[str], update: bool = False) -> int:
    """Insert rows; on a duplicate key either skip (default) or overwrite. Returns rows written."""
    if not rows:
        return 0
    eng = engine()
    if eng.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    written = 0
    with eng.begin() as conn:
        for i in range(0, len(rows), 1000):   # chunks: low memory on a 1 GB EC2, under SQLite's variable limit
            stmt = insert(table).values(rows[i:i + 1000])
            if update:
                cols = {c: stmt.excluded[c] for c in rows[0] if c not in conflict_cols}
                stmt = stmt.on_conflict_do_update(index_elements=conflict_cols, set_=cols)
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)
            written += conn.execute(stmt).rowcount
    return written


def db_ok() -> bool:
    try:
        with engine().connect() as conn:
            conn.execute(select(1))
        return True
    except Exception:  # noqa: BLE001 - health check
        return False
