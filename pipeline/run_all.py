"""Full pipeline: ETL every new raw/ file -> (re)train -> predict.

    python -m pipeline.run_all              # ETL + train + predict  (daily cron)
    python -m pipeline.run_all --no-train   # ETL + predict          (hourly cron)

A lock file stops cron and the dashboard's "Run pipeline" button from running it twice at once.
"""
import argparse
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

import db
from pipeline import etl, predict, train

log = logging.getLogger(__name__)
LOCK = Path(tempfile.gettempdir()) / "traffic-pipeline.lock"
STALE_SECONDS = 3600


def _acquire_lock() -> bool:
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime > STALE_SECONDS:
        LOCK.unlink(missing_ok=True)       # a crashed run left it behind
    try:
        os.close(os.open(LOCK, os.O_CREAT | os.O_EXCL))
        return True
    except FileExistsError:
        return False


def run(do_train: bool = True) -> dict:
    if not _acquire_lock():
        log.warning("pipeline already running (%s) - skipping", LOCK)
        return {"skipped": True}
    try:
        loaded, failed = 0, []
        for key in etl.pending_keys():
            try:
                loaded += etl.process_key(key)
            except Exception:  # noqa: BLE001 - one bad file must not block the others; logged in pipeline_runs
                failed.append(key)
        with db.engine().connect() as conn:
            has_model = conn.execute(db.model_runs.select().where(db.model_runs.c.is_active)).first()
        if do_train or not has_model:
            train.main()
        n_pred = predict.main()
        return {"rows_loaded": loaded, "failed_files": failed, "predictions": n_pred}
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-train", action="store_true")
    result = run(do_train=not ap.parse_args().no_train)
    log.info("pipeline result: %s", result)
    sys.exit(1 if result.get("failed_files") else 0)
