"""Congestion = volume / capacity (V/C ratio), a standard traffic-engineering measure.

Capacity is unknown in the dataset, so we use the 95th percentile of a location's hourly
volume as a proxy (stated as a limitation in the report).
"""
import numpy as np

LEVELS = [(0.40, "Low"), (0.70, "Moderate"), (0.90, "High")]   # >= 0.90 -> "Severe"
# One-hue warm ramp, light -> dark (ordinal; validated for colour-blind separation). Always shown with its label.
COLORS = {"Low": "#da9b6a", "Moderate": "#be7537", "High": "#9b540c", "Severe": "#6e3700"}


def capacity(volumes) -> int:
    return max(1, int(np.percentile(np.asarray(volumes, dtype=float), 95)))


def level(vc: float) -> str:
    for limit, name in LEVELS:
        if vc < limit:
            return name
    return "Severe"


def levels(volumes, cap) -> list[str]:
    return [level(v / cap) for v in np.asarray(volumes, dtype=float)]
