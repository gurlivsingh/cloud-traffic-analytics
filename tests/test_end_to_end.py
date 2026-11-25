"""Whole system on a small synthetic dataset: storage -> ETL -> DB -> train -> predict -> API."""
import io

import numpy as np
import pandas as pd
import pytest

import cloud
import config
from pipeline import etl, run_all


@pytest.fixture(scope="module")
def client():
    ts = pd.date_range("2018-01-01", periods=24 * 60, freq="h")
    daily = 1000 + 3000 * np.exp(-((ts.hour - 8) ** 2) / 6) + 2500 * np.exp(-((ts.hour - 17) ** 2) / 6)
    rng = np.random.default_rng(1)
    parts = [pd.DataFrame({"location": name, "lat": lat, "lon": -93.2, "ts": ts,
                           "volume": (daily * scale * rng.normal(1, 0.05, len(ts))).round().astype(int),
                           "temp": 2.0, "rain": 0.0, "snow": 0.0, "clouds": 20, "weather_main": "Clear"})
             for name, lat, scale in [("Road A", 44.9, 1.0), ("Road B", 45.0, 0.6)]]
    cloud.put_bytes("raw/test.csv", pd.concat(parts).to_csv(index=False).encode())
    result = run_all.run(do_train=True)
    assert result["failed_files"] == [] and result["rows_loaded"] == 2 * 24 * 60

    from app.app import app
    app.config["TESTING"] = True
    return app.test_client()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json["db"] == "ok" and r.json["storage"] == "ok"


def test_locations_have_level_and_next_hour(client):
    locs = client.get("/api/locations").json
    assert {l["name"] for l in locs} == {"Road A", "Road B"}
    for l in locs:
        assert l["level"] in ("Low", "Moderate", "High", "Severe")
        assert l["next"] and l["next"]["level"]


def test_predictions_cover_future_hours(client):
    loc = client.get("/api/locations").json[0]["id"]
    d = client.get(f"/api/predictions?location={loc}").json
    assert len(d["future"]) == config.PREDICT_HOURS
    assert len(d["predicted"]) >= 48               # backfilled 1-hour-ahead predictions


def test_model_beats_baseline(client):
    m = client.get("/api/model").json["metrics"]
    by = {r["model"]: r for r in m["results"]}
    assert by["Random Forest"]["rmse"] < by["Baseline (same hour last week)"]["rmse"]
    assert m["test_period"][0] > m["train_period"][1]   # time split: test strictly after train


def test_patterns_and_traffic(client):
    loc = client.get("/api/locations").json[0]["id"]
    p = client.get(f"/api/patterns?location={loc}").json
    assert len(p["heatmap"]) == 7 and len(p["heatmap"][0]) == 24
    t = client.get(f"/api/traffic?location={loc}&agg=day").json
    assert t["agg"] == "day" and len(t["t"]) > 0


def test_reloading_same_file_adds_no_duplicates():
    assert etl.load(etl.clean(etl.normalize(etl.read_csv_bytes(cloud.get_bytes("raw/test.csv"), "x.csv")))) == 0


def test_admin_requires_login(client):
    assert client.get("/admin").status_code == 302
    assert client.post("/admin/run-pipeline").status_code == 302
    assert client.post("/login", data={"password": "wrong"}).status_code == 200   # stays on login page


def test_upload_validation(client):
    client.post("/login", data={"password": "admin"})
    r = client.post("/admin/upload", data={"file": (io.BytesIO(b"a,b\n1,2\n"), "bad.csv")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"Rejected" in r.data
    r = client.post("/admin/upload", data={"file": (io.BytesIO(b"x"), "evil.exe")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"Choose a .csv" in r.data
    good = b"location,ts,volume\nRoad A,2018-03-02 00:00,500\n"
    r = client.post("/admin/upload", data={"file": (io.BytesIO(good), "new.csv")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert b"Uploaded 1 rows" in r.data
    assert any(k.startswith("raw/uploads/") for k in cloud.list_keys("raw/"))
