"""Simulated live feed for the demo: every --interval seconds, push the next held-back hour
from feed/feed.csv.gz into S3 raw/feed/, run ETL on it, and refresh predictions.

    python -m pipeline.replay_feed --interval 30 --hours 20
"""
import argparse
import logging
import time

import pandas as pd
from sqlalchemy import func, select

import cloud
import db
from pipeline import etl, predict

log = logging.getLogger(__name__)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=60, help="seconds between hours")
    ap.add_argument("--hours", type=int, default=24, help="how many hours to replay")
    args = ap.parse_args()

    feed = etl.read_csv_bytes(cloud.get_bytes("feed/feed.csv.gz"), "feed.csv.gz")
    feed["ts"] = pd.to_datetime(feed["ts"])
    with db.engine().connect() as conn:
        loaded_until = conn.execute(select(func.max(db.traffic_records.c.ts))).scalar()
    hours = sorted(t for t in feed["ts"].unique() if loaded_until is None or t > pd.Timestamp(loaded_until))
    if not hours:
        log.info("feed fully replayed already")
        return
    for ts in hours[:args.hours]:
        ts = pd.Timestamp(ts)
        key = f"raw/feed/{ts:%Y%m%d_%H}.csv"
        cloud.put_bytes(key, feed[feed["ts"] == ts].to_csv(index=False).encode())
        etl.process_key(key)
        predict.main()
        log.info("replayed hour %s", ts)
        time.sleep(args.interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
