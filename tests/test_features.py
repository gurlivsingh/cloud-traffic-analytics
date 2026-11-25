import pandas as pd

from pipeline import etl
from pipeline.features import FEATURES, build_features


def frame(n=400, drop_hour=None):
    ts = pd.date_range("2018-01-01", periods=n, freq="h")
    df = pd.DataFrame({"location_id": 1, "ts": ts, "volume": range(n), "temp": 5.0, "rain": 0.0,
                       "snow": 0.0, "clouds": 40.0, "weather_main": "Clouds", "is_holiday": False})
    return df.drop(index=drop_hour) if drop_hour is not None else df


def test_lags_only_use_past_hours():   # no data leakage
    f = build_features(frame())
    assert (f["lag_1h"] == f["volume"] - 1).all()
    assert (f["lag_24h"] == f["volume"] - 24).all()
    assert (f["lag_168h"] == f["volume"] - 168).all()
    assert (f["roll_3h"] == f["volume"] - 2).all()   # mean of the 3 previous hours
    assert "volume" not in FEATURES


def test_missing_hour_does_not_shift_lags():
    f = build_features(frame(drop_hour=300))
    # the hour after the gap has no real previous hour -> dropped, not given a wrong lag
    assert not (f["ts"] == pd.Timestamp("2018-01-01") + pd.Timedelta(hours=301)).any()
    assert (f["lag_1h"] == f["volume"] - 1).all()


def test_uci_format_cleaning():
    raw = pd.DataFrame({
        "holiday": ["Christmas Day", "None", "None", "None"],
        "temp": [270.0, 0.0, 272.0, 272.0],                       # 0 K = bad sensor
        "rain_1h": [0.0, 9831.3, 0.0, 0.0],                        # impossible rain
        "snow_1h": 0.0, "clouds_all": 90, "weather_main": ["Snow", "Snow", "Mist", "Mist"],
        "weather_description": "x",
        "date_time": ["2017-12-25 00:00:00", "2017-12-25 01:00:00", "2017-12-25 02:00:00", "2017-12-25 02:00:00"],
        "traffic_volume": [500, 400, 300, 300],                    # last row duplicates an hour
    })
    df = etl.clean(etl.normalize(raw))
    assert len(df) == 3
    assert df["is_holiday"].all()                                  # holiday spread to the whole day
    assert df["temp"].notna().all() and abs(df["temp"].iloc[0] + 3.15) < 0.01
    assert df["rain"].max() <= 100


def test_unknown_csv_rejected():
    try:
        etl.normalize(pd.DataFrame({"a": [1]}))
    except ValueError:
        return
    raise AssertionError("expected ValueError")
