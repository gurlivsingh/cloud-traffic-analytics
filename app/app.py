"""Flask web app: dashboard pages + JSON API. Runs on EC2 behind nginx (gunicorn app.app:app)."""
import json
import logging
import secrets
import subprocess
import sys
from datetime import datetime
from functools import wraps

import pandas as pd
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import and_, func, select
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import cloud
import config
import db
from pipeline import congestion, etl
from pipeline.train import METRICS_KEY

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
ON_AWS = bool(config.S3_BUCKET or config.DB_HOST)

app = Flask(__name__)
app.json.sort_keys = False   # keep Low -> Severe order etc. in API responses
app.secret_key = cloud.get_secret("FLASK_SECRET", config.FLASK_SECRET_PARAM)
if not app.secret_key:
    if ON_AWS:
        raise RuntimeError("Set FLASK_SECRET or SSM " + config.FLASK_SECRET_PARAM)
    app.secret_key = secrets.token_hex(16)        # local dev only
app.config.update(MAX_CONTENT_LENGTH=config.MAX_UPLOAD_MB * 1024 * 1024,
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")  # Lax blocks cross-site POSTs (CSRF)

_admin_hash = cloud.get_secret("ADMIN_PASSWORD_HASH", config.ADMIN_PASSWORD_HASH_PARAM)
if not _admin_hash and not ON_AWS:
    _admin_hash = generate_password_hash("admin")   # local dev only; README says how to set a real one


def fmt(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M")


def read_df(query) -> pd.DataFrame:
    with db.engine().connect() as conn:
        df = pd.read_sql(query, conn)
    df.columns = [str(c) for c in df.columns]
    return df


def location_id_arg() -> int:
    loc = request.args.get("location", type=int)
    if loc is None:
        with db.engine().connect() as conn:
            loc = conn.execute(select(func.min(db.locations.c.id))).scalar()
    if loc is None:
        abort(404, "no data loaded yet")
    return loc


def admin_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return view(*a, **kw)
    return wrapper


# ---------------- pages ----------------

PAGES = [("overview", "Overview"), ("historical", "Historical"), ("prediction", "Prediction"),
         ("map_page", "Map"), ("model_page", "Model"), ("system", "System")]   # Admin is the top-right button


@app.context_processor
def nav():
    return {"pages": PAGES, "level_colors": congestion.COLORS, "on_aws": ON_AWS}


@app.get("/")
def overview():
    return render_template("overview.html")


@app.get("/historical")
def historical():
    return render_template("historical.html")


@app.get("/prediction")
def prediction():
    return render_template("prediction.html")


@app.get("/map")
def map_page():
    return render_template("map.html")


@app.get("/model")
def model_page():
    return render_template("model.html")


@app.get("/system")
def system():
    return render_template("system.html")


@app.get("/admin")
@admin_required
def admin():
    return render_template("admin.html", max_mb=config.MAX_UPLOAD_MB)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if _admin_hash and check_password_hash(_admin_hash, request.form.get("password", "")):
            session["admin"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("admin"))
        flash("Wrong password", "error")
    return render_template("login.html", local_hint=not ON_AWS)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("overview"))


# ---------------- admin actions ----------------

def _spawn(*args):
    log = open(config.PIPELINE_LOG, "a")   # noqa: SIM115 - child process owns the handle
    subprocess.Popen([sys.executable, "-m", *args], cwd=config.ROOT, stdout=log, stderr=subprocess.STDOUT)


@app.post("/admin/upload")
@admin_required
def admin_upload():
    f = request.files.get("file")
    name = secure_filename(f.filename) if f else ""
    if not name.endswith((".csv", ".csv.gz")):
        flash("Choose a .csv or .csv.gz file", "error")
        return redirect(url_for("admin"))
    data = f.read()
    try:   # validate at the trust boundary before anything reaches S3
        df = etl.normalize(etl.read_csv_bytes(data, name))
        if df.empty:
            raise ValueError("file has no rows")
    except Exception as e:  # noqa: BLE001 - any parse problem is a user error here
        flash(f"Rejected: {e}", "error")
        return redirect(url_for("admin"))
    key = f"raw/uploads/{datetime.now():%Y%m%d_%H%M%S}_{name}"
    cloud.put_bytes(key, data)
    flash(f"Uploaded {len(df)} rows to {'s3://' + config.S3_BUCKET + '/' if config.S3_BUCKET else 'storage/'}{key}. "
          "Click 'Run pipeline' to process it.", "ok")
    return redirect(url_for("admin"))


@app.post("/admin/run-pipeline")
@admin_required
def admin_run():
    _spawn("pipeline.run_all", *([] if request.form.get("train") else ["--no-train"]))
    flash("Pipeline started in the background - see the System page for its run log.", "ok")
    return redirect(url_for("admin"))


@app.post("/admin/replay")
@admin_required
def admin_replay():
    _spawn("pipeline.replay_feed", "--hours", "1", "--interval", "0")
    flash("Streaming the next hour of the live feed - refresh the Overview in a few seconds.", "ok")
    return redirect(url_for("admin"))


# ---------------- JSON API ----------------

@app.get("/health")
def health():
    status = {"db": "ok" if db.db_ok() else "down", "storage": "ok" if cloud.storage_ok() else "down",
              "storage_backend": f"s3://{config.S3_BUCKET}" if config.S3_BUCKET else "local",
              "db_backend": "rds-postgresql" if config.DB_HOST else "sqlite"}
    return jsonify(status), 200 if status["db"] == status["storage"] == "ok" else 503


@app.get("/api/locations")
def api_locations():
    t, l, p = db.traffic_records, db.locations, db.predictions
    latest = select(t.c.location_id, func.max(t.c.ts).label("ts")).group_by(t.c.location_id).subquery()
    q = (select(l.c.id, l.c.name, l.c.lat, l.c.lon, l.c.capacity, l.c.is_synthetic, t.c.ts, t.c.volume,
                t.c.speed, t.c.occupancy, t.c.congestion_index, t.c.congestion_level)
         .join(latest, latest.c.location_id == l.c.id)
         .join(t, and_(t.c.location_id == l.c.id, t.c.ts == latest.c.ts)).order_by(l.c.is_synthetic, l.c.name))
    out = []
    with db.engine().connect() as conn:
        for r in conn.execute(q):
            nxt = conn.execute(select(p.c.target_ts, p.c.predicted_volume, p.c.predicted_level)
                               .where(p.c.location_id == r.id, p.c.target_ts > r.ts)
                               .order_by(p.c.target_ts).limit(1)).first()
            out.append({"id": r.id, "name": r.name, "lat": r.lat, "lon": r.lon, "capacity": r.capacity,
                        "synthetic": bool(r.is_synthetic), "ts": fmt(r.ts), "volume": r.volume,
                        "speed": r.speed, "occupancy": r.occupancy, "vc": r.congestion_index,
                        "level": r.congestion_level,
                        "next": nxt and {"ts": fmt(nxt.target_ts), "volume": nxt.predicted_volume,
                                         "level": nxt.predicted_level}})
    return jsonify(out)


@app.get("/api/summary")
def api_summary():
    t = db.traffic_records
    with db.engine().connect() as conn:
        n, last = conn.execute(select(func.count(), func.max(t.c.ts)).select_from(t)).one()
        run = conn.execute(select(db.model_runs).where(db.model_runs.c.is_active)
                           .order_by(db.model_runs.c.id.desc()).limit(1)).first()
    return jsonify({"records": n, "latest": last and fmt(last),
                    "model": run and {"name": run.model_name, "r2": run.r2, "mae": run.mae,
                                      "accuracy": run.level_accuracy}})


@app.get("/api/traffic")
def api_traffic():
    loc = location_id_arg()
    t = db.traffic_records
    with db.engine().connect() as conn:
        last = conn.execute(select(func.max(t.c.ts)).where(t.c.location_id == loc)).scalar()
    if last is None:
        return jsonify({"t": [], "volume": [], "speed": [], "agg": "hour"})
    end = pd.Timestamp(request.args.get("to") or last)
    start = pd.Timestamp(request.args.get("from") or end - pd.Timedelta(days=14))
    df = read_df(select(t.c.ts, t.c.volume, t.c.speed)
                 .where(t.c.location_id == loc, t.c.ts >= start.to_pydatetime(),
                        t.c.ts <= end.to_pydatetime()).order_by(t.c.ts))
    agg = request.args.get("agg", "hour")
    if agg == "day" or end - start > pd.Timedelta(days=60):   # keep charts under ~2k points
        agg = "day"
        df = df.set_index(pd.to_datetime(df["ts"]))[["volume", "speed"]].resample("D").mean().dropna(
            subset=["volume"]).reset_index()
    return jsonify({"agg": agg, "t": [fmt(x) for x in df["ts"]], "volume": df["volume"].round().tolist(),
                    "speed": [None if pd.isna(x) else round(x, 1) for x in df["speed"]]})


@app.get("/api/patterns")
def api_patterns():
    loc = location_id_arg()
    t = db.traffic_records
    df = read_df(select(t.c.ts, t.c.volume, t.c.weather_main, t.c.is_holiday, t.c.congestion_level)
                 .where(t.c.location_id == loc))
    if df.empty:
        return jsonify({})
    ts = pd.to_datetime(df["ts"])
    df["hour"], df["dow"], df["date"] = ts.dt.hour, ts.dt.dayofweek, ts.dt.date
    heat = df.pivot_table(index="dow", columns="hour", values="volume", aggfunc="mean").reindex(
        index=range(7), columns=range(24))
    df["daytype"] = (df["dow"] >= 5).map({True: "Weekend", False: "Weekday"})
    by_type = df.pivot_table(index="hour", columns="daytype", values="volume", aggfunc="mean")
    daytime = df[df["hour"].between(7, 19)]       # same hours for every weather type -> fairer comparison
    weather = daytime.groupby("weather_main")["volume"].agg(["mean", "count"])
    weather = weather[weather["count"] >= 30].sort_values("mean", ascending=False)
    daily = df.groupby(["date", "is_holiday"])["volume"].sum().reset_index()
    hol = daily.groupby("is_holiday")["volume"].mean()
    levels = df["congestion_level"].value_counts()
    return jsonify({
        "heatmap": [[None if pd.isna(v) else round(v) for v in row] for row in heat.to_numpy()],
        "hourly": {k: by_type[k].round().tolist() for k in by_type.columns},
        "weather": {"labels": weather.index.tolist(), "values": weather["mean"].round().tolist()},
        "holiday": {"Normal day": round(float(hol.get(False, 0))), "Holiday": round(float(hol.get(True, 0)))},
        "levels": {lv: int(levels.get(lv, 0)) for lv in ["Low", "Moderate", "High", "Severe"]},
    })


@app.get("/api/predictions")
def api_predictions():
    loc = location_id_arg()
    t, p = db.traffic_records, db.predictions
    with db.engine().connect() as conn:
        last = conn.execute(select(func.max(t.c.ts)).where(t.c.location_id == loc)).scalar()
        cap = conn.execute(select(db.locations.c.capacity).where(db.locations.c.id == loc)).scalar()
    if last is None:
        return jsonify({"actual": [], "predicted": [], "future": []})
    since = (pd.Timestamp(last) - pd.Timedelta(hours=48)).to_pydatetime()
    act = read_df(select(t.c.ts, t.c.volume).where(t.c.location_id == loc, t.c.ts > since).order_by(t.c.ts))
    pr = read_df(select(p.c.target_ts, p.c.predicted_volume, p.c.predicted_level)
                 .where(p.c.location_id == loc, p.c.target_ts > since).order_by(p.c.target_ts))
    fut = pr[pd.to_datetime(pr["target_ts"]) > pd.Timestamp(last)]
    return jsonify({
        "capacity": cap, "latest": fmt(last),
        "actual": [{"t": fmt(a), "v": v} for a, v in zip(act["ts"], act["volume"])],
        "predicted": [{"t": fmt(a), "v": v} for a, v in zip(pr["target_ts"], pr["predicted_volume"])],
        "future": [{"t": fmt(a), "v": v, "level": lv} for a, v, lv in
                   zip(fut["target_ts"], fut["predicted_volume"], fut["predicted_level"])],
    })


@app.get("/api/model")
def api_model():
    try:
        metrics = json.loads(cloud.get_bytes(METRICS_KEY))
    except Exception:  # noqa: BLE001 - no model trained yet
        metrics = None
    runs = read_df(select(db.model_runs).order_by(db.model_runs.c.id.desc()).limit(12))
    runs["trained_at"] = runs["trained_at"].map(fmt)
    return jsonify({"metrics": metrics, "runs": runs.astype(object).where(runs.notna(), None).to_dict("records")})


@app.get("/api/system")
def api_system():
    runs = read_df(select(db.pipeline_runs).order_by(db.pipeline_runs.c.id.desc()).limit(15))
    for c in ("started_at", "finished_at"):
        runs[c] = runs[c].map(lambda x: None if pd.isna(x) else fmt(x))
    return jsonify({"cloudwatch": cloud.system_metrics(),
                    "runs": runs.astype(object).where(runs.notna(), None).to_dict("records")})
