"""Feature engineering for next-hour traffic volume prediction.

Every lag uses only PAST hours (shift >= 1), so the model never sees the value it predicts.
tests/test_features.py checks this (no data leakage).
"""
import pandas as pd

WEATHER_CATS = ["Clear", "Clouds", "Rain", "Snow", "Mist", "Drizzle", "Haze", "Thunderstorm", "Fog"]
WEATHER_NUM = ["temp", "rain", "snow", "clouds"]
LAGS = ["lag_1h", "lag_24h", "lag_168h", "roll_3h"]
FEATURES = (["hour", "dayofweek", "month", "is_weekend", "is_holiday"] + WEATHER_NUM
            + [f"w_{w}" for w in WEATHER_CATS] + LAGS)


def build_features(df: pd.DataFrame, require_target: bool = True) -> pd.DataFrame:
    """df: location_id, ts, volume, temp, rain, snow, clouds, weather_main, is_holiday (any order)."""
    parts = []
    for loc, g in df.groupby("location_id", sort=False):
        g = g.sort_values("ts").drop_duplicates("ts").set_index("ts").asfreq("h")  # real hourly grid
        g["location_id"] = loc
        g[WEATHER_NUM + ["weather_main"]] = g[WEATHER_NUM + ["weather_main"]].ffill()
        v = g["volume"]
        g["lag_1h"], g["lag_24h"], g["lag_168h"] = v.shift(1), v.shift(24), v.shift(168)
        g["roll_3h"] = v.shift(1).rolling(3).mean()
        parts.append(g.reset_index())
    f = pd.concat(parts, ignore_index=True)

    f["hour"] = f["ts"].dt.hour
    f["dayofweek"] = f["ts"].dt.dayofweek
    f["month"] = f["ts"].dt.month
    f["is_weekend"] = (f["dayofweek"] >= 5).astype(int)
    f["is_holiday"] = f["is_holiday"].astype("boolean").fillna(False).astype(int)
    for w in WEATHER_CATS:
        f[f"w_{w}"] = (f["weather_main"] == w).astype(int)
    f[WEATHER_NUM] = f[WEATHER_NUM].astype(float).fillna(0.0)

    f = f.dropna(subset=LAGS)
    if require_target:
        f = f.dropna(subset=["volume"])
    return f.reset_index(drop=True)
