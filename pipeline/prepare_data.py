"""Download the public dataset, add synthetic road segments, upload to storage (S3 raw/ + feed/).

Real data : UCI Metro Interstate Traffic Volume (CC BY 4.0), hourly, I-94 WB, 2012-2018.
Synthetic : 6 nearby road segments derived from the real hourly pattern (scaled, time-shifted,
            noisy) with speed and occupancy added. Clearly named "(synthetic)" everywhere.
The last 7 days are held back in feed/ so replay_feed.py can stream them in "live" during the demo.

    python -m pipeline.prepare_data            # downloads from UCI
    python -m pipeline.prepare_data --csv FILE # use an already-downloaded csv / csv.gz
"""
import argparse
import io
import logging
import urllib.request
import zipfile

import numpy as np
import pandas as pd

import cloud
from pipeline import congestion, etl

log = logging.getLogger(__name__)

UCI_URL = "https://archive.ics.uci.edu/static/public/492/metro+interstate+traffic+volume.zip"
SEGMENTS = [  # name, lat, lon, volume scale, hour shift
    ("I-35W @ Lake St (synthetic)", 44.948, -93.270, 1.10, 0),
    ("I-394 @ Penn Ave (synthetic)", 44.969, -93.308, 0.70, -1),
    ("MN-55 @ Hiawatha Ave (synthetic)", 44.936, -93.235, 0.45, 1),
    ("I-94 @ Snelling Ave (synthetic)", 44.957, -93.167, 0.95, 0),
    ("I-35E @ Maryland Ave (synthetic)", 44.977, -93.099, 0.80, 1),
    ("US-52 @ Plato Blvd (synthetic)", 44.932, -93.088, 0.55, -1),
]
SYNTHETIC_DAYS = 365
FEED_DAYS = 7
FREE_FLOW_KMH = 100


def download_uci() -> pd.DataFrame:
    log.info("downloading %s", UCI_URL)
    with urllib.request.urlopen(UCI_URL, timeout=60) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    name = next(n for n in z.namelist() if n.endswith((".csv", ".csv.gz")))
    return etl.read_csv_bytes(z.read(name), name)


def synthetic_segments(real: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = real[real["ts"] > real["ts"].max() - pd.Timedelta(days=SYNTHETIC_DAYS)].set_index("ts")
    out = []
    for name, lat, lon, scale, shift in SEGMENTS:
        s = base.copy()
        s["volume"] = (base["volume"].shift(shift).bfill().ffill() * scale
                       * rng.normal(1, 0.08, len(s))).clip(lower=0).round().astype(int)
        vc = s["volume"] / congestion.capacity(s["volume"])
        s["speed"] = (FREE_FLOW_KMH * (1 - 0.75 * vc.clip(upper=1.2) ** 2)).clip(lower=8).round(1)
        s["occupancy"] = (vc * 30 + rng.normal(0, 2, len(s))).clip(0, 100).round(1)
        s["location"], s["lat"], s["lon"], s["is_synthetic"] = name, lat, lon, True
        out.append(s.reset_index())
    return pd.concat(out, ignore_index=True)[etl.CANONICAL]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="local UCI csv/csv.gz instead of downloading")
    args = ap.parse_args()

    raw = etl.read_csv_bytes(open(args.csv, "rb").read(), args.csv) if args.csv else download_uci()
    real = etl.clean(etl.normalize(raw))
    data = pd.concat([real, synthetic_segments(real)], ignore_index=True)

    cutoff = data["ts"].max() - pd.Timedelta(days=FEED_DAYS)
    history, feed = data[data["ts"] <= cutoff], data[data["ts"] > cutoff]
    cloud.put_bytes("raw/history.csv.gz", etl._gzip_csv(history))
    cloud.put_bytes("feed/feed.csv.gz", etl._gzip_csv(feed))
    log.info("uploaded raw/history.csv.gz (%d rows) and feed/feed.csv.gz (%d rows, after %s)",
             len(history), len(feed), cutoff)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
