import json
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from data_mappings import VIS_BUCKET_LABELS, VIS_BUCKETS, visibility_bucket

DATA_DIR = Path(__file__).parent / "data"
LOOKUP_PATH = DATA_DIR / "accident_lookup.parquet"
META_PATH = DATA_DIR / "baseline.json"

_lookup: pd.DataFrame | None = None
_baseline: dict | None = None


@dataclass
class RiskFactor:
    name: str
    label: str
    contribution: float


@dataclass
class RiskResult:
    score: float
    level: str
    accident_count: int
    avg_severity: float
    relative_risk: float
    matched_conditions: str
    factors: list[RiskFactor]
    suggestions: list[str]


def _load_data() -> tuple[pd.DataFrame, dict]:
    global _lookup, _baseline
    if _lookup is not None and _baseline is not None:
        return _lookup, _baseline

    if not LOOKUP_PATH.exists() or not META_PATH.exists():
        raise FileNotFoundError(
            "Accident lookup data not found. Run: python preprocess_data.py"
        )

    _lookup = pd.read_parquet(LOOKUP_PATH)
    _baseline = json.loads(META_PATH.read_text())
    return _lookup, _baseline


def get_baseline() -> dict:
    _, baseline = _load_data()
    return baseline


WEATHER_RISK = {
    "clear": 0.0,
    "cloudy": 0.08,
    "rain": 0.28,
    "snow": 0.32,
    "fog": 0.30,
    "ice": 0.38,
}

PLACE_RISK = {
    "highway": 0.10,
    "urban": 0.08,
    "intersection": 0.14,
    "rural": 0.12,
    "parking_lot": 0.04,
}


def _visibility_risk(visibility_mi: float) -> float:
    if visibility_mi < 1:
        return 0.35
    if visibility_mi < 3:
        return 0.25
    if visibility_mi < 5:
        return 0.15
    if visibility_mi < 10:
        return 0.08
    return 0.0


def _time_risk(hour: int) -> float:
    if hour >= 22 or hour <= 5:
        return 0.20
    if 7 <= hour <= 9 or 16 <= hour <= 19:
        return 0.12
    return 0.0


def _intrinsic_risk(
    weather: str,
    visibility_mi: float,
    hour: int,
    place_type: str,
) -> tuple[float, list[RiskFactor]]:
    factors: list[RiskFactor] = []

    weather_risk = WEATHER_RISK.get(weather, 0.10)
    if weather_risk > 0:
        factors.append(
            RiskFactor("weather", f"{weather.title()} conditions", weather_risk)
        )

    vis_risk = _visibility_risk(visibility_mi)
    if vis_risk > 0:
        factors.append(
            RiskFactor(
                "visibility",
                f"Low visibility ({visibility_mi:.1f} mi)",
                vis_risk,
            )
        )

    time_risk = _time_risk(hour)
    if time_risk > 0:
        label = "Night driving" if hour >= 22 or hour <= 5 else "Rush hour"
        factors.append(RiskFactor("time", label, time_risk))

    place_risk = PLACE_RISK.get(place_type, 0.08)
    if place_risk > 0:
        factors.append(
            RiskFactor(
                "place",
                place_type.replace("_", " ").title(),
                place_risk,
            )
        )

    score = min(weather_risk + vis_risk + time_risk + place_risk, 1.0)
    factors.sort(key=lambda f: f.contribution, reverse=True)
    return score, factors


def _data_risk(
    lookup: pd.DataFrame,
    accident_count: int,
    avg_severity: float,
    hour: int,
    place_type: str,
    baseline_severity: float,
) -> tuple[float, float, list[RiskFactor]]:
    factors: list[RiskFactor] = []

    peers = lookup[
        (lookup["hour"] == hour) & (lookup["place_type"] == place_type)
    ]
    if peers.empty or accident_count == 0:
        return 0.0, 0.0, factors

    percentile = float((peers["accident_count"] <= accident_count).mean())
    peer_max = float(peers["accident_count"].max())
    log_factor = math.log1p(accident_count) / math.log1p(peer_max)

    severity_ratio = avg_severity / baseline_severity if baseline_severity else 1.0
    severity_factor = min(max((severity_ratio - 0.95) / 0.35, 0), 1.0)

    avg_peer_count = float(peers["accident_count"].mean())
    relative_risk = accident_count / avg_peer_count if avg_peer_count else 1.0

    score = 0.35 * percentile + 0.30 * log_factor + 0.35 * severity_factor
    score = min(score, 1.0)

    factors.append(
        RiskFactor(
            "accidents",
            f"{accident_count:,} accidents in dataset",
            round(0.35 * percentile + 0.30 * log_factor, 3),
        )
    )
    factors.append(
        RiskFactor(
            "severity",
            f"Avg severity {avg_severity:.1f} / 4 (baseline {baseline_severity:.1f})",
            round(0.35 * severity_factor, 3),
        )
    )
    factors.append(
        RiskFactor(
            "frequency",
            f"{relative_risk:.1f}× vs same hour on {place_type.replace('_', ' ')}",
            0.0,
        )
    )

    return score, relative_risk, factors


def _risk_level(score: float) -> str:
    if score < 0.25:
        return "Low"
    if score < 0.50:
        return "Moderate"
    if score < 0.75:
        return "High"
    return "Very High"


def _suggestions(score: float, weather: str, visibility_mi: float) -> list[str]:
    tips: list[str] = []
    if score >= 0.50:
        tips.append("Consider delaying your trip if possible.")
    if weather in {"rain", "snow", "fog", "ice"}:
        tips.append("Reduce speed and increase following distance.")
    if visibility_mi < 5:
        tips.append("Use headlights and watch for sudden stops ahead.")
    if weather == "ice":
        tips.append("Avoid sudden braking or sharp turns on icy roads.")
    if not tips:
        tips.append("Conditions look favorable — stay alert and avoid distractions.")
    return tips


def _format_hour(hour: int) -> str:
    suffix = "AM" if hour < 12 else "PM"
    display = hour % 12
    if display == 0:
        display = 12
    return f"{display}:00 {suffix}"


def _query_lookup(
    lookup: pd.DataFrame,
    hour: int,
    vis_bucket: str,
    place_type: str,
    weather: str,
    *,
    include_weather: bool = True,
) -> pd.DataFrame:
    mask = (
        (lookup["hour"] == hour)
        & (lookup["vis_bucket"] == vis_bucket)
        & (lookup["place_type"] == place_type)
    )
    if include_weather:
        mask &= lookup["weather"] == weather
    return lookup[mask]


def _summarize_match(match: pd.DataFrame) -> tuple[int, float]:
    if match.empty:
        return 0, 0.0
    count = int(match["accident_count"].sum())
    weighted_severity = (match["accident_count"] * match["avg_severity"]).sum()
    avg_severity = weighted_severity / count if count else 0.0
    return count, float(avg_severity)


def _find_match(
    lookup: pd.DataFrame,
    hour: int,
    vis_bucket: str,
    place_type: str,
    weather: str,
) -> tuple[int, float, str, bool]:
    """Try exact match, then relax weather, then widen visibility bucket."""
    vis_label = VIS_BUCKET_LABELS[vis_bucket]

    match = _query_lookup(lookup, hour, vis_bucket, place_type, weather)
    count, avg_severity = _summarize_match(match)
    if count > 0:
        conditions = (
            f"{_format_hour(hour)}, visibility {vis_label}, "
            f"{place_type.replace('_', ' ')}, {weather} weather"
        )
        return count, avg_severity, conditions, True

    match = _query_lookup(
        lookup, hour, vis_bucket, place_type, weather, include_weather=False
    )
    count, avg_severity = _summarize_match(match)
    if count > 0:
        conditions = (
            f"{_format_hour(hour)}, visibility {vis_label}, "
            f"{place_type.replace('_', ' ')} (any weather)"
        )
        return count, avg_severity, conditions, False

    bucket_idx = VIS_BUCKETS.index(vis_bucket)
    for offset in (1, -1, 2, -2):
        neighbor_idx = bucket_idx + offset
        if neighbor_idx < 0 or neighbor_idx >= len(VIS_BUCKETS):
            continue
        neighbor = VIS_BUCKETS[neighbor_idx]
        match = _query_lookup(
            lookup, hour, neighbor, place_type, weather, include_weather=False
        )
        count, avg_severity = _summarize_match(match)
        if count > 0:
            neighbor_label = VIS_BUCKET_LABELS[neighbor]
            conditions = (
                f"{_format_hour(hour)}, visibility ~{neighbor_label}, "
                f"{place_type.replace('_', ' ')} (similar conditions)"
            )
            return count, avg_severity, conditions, False

    conditions = (
        f"{_format_hour(hour)}, visibility {vis_label}, "
        f"{place_type.replace('_', ' ')}"
    )
    return 0, 0.0, conditions, False


def calculate_risk(
    weather: str,
    visibility_mi: float,
    hour: int,
    place_type: str,
) -> RiskResult:
    lookup, baseline = _load_data()
    vis_bucket = visibility_bucket(visibility_mi)

    accident_count, avg_severity, matched_conditions, exact_match = _find_match(
        lookup, hour, vis_bucket, place_type, weather
    )

    baseline_severity = baseline["avg_severity"]
    intrinsic_score, intrinsic_factors = _intrinsic_risk(
        weather, visibility_mi, hour, place_type
    )

    if accident_count == 0:
        data_score = 0.0
        relative_risk = 0.0
        data_factors = [
            RiskFactor(
                "data",
                "No matching accidents in dataset for these conditions",
                0.0,
            )
        ]
        score = intrinsic_score * 0.85
    else:
        data_score, relative_risk, data_factors = _data_risk(
            lookup,
            accident_count,
            avg_severity,
            hour,
            place_type,
            baseline_severity,
        )
        # Blend: conditions set the floor; data can raise or confirm the score.
        blended = 0.55 * intrinsic_score + 0.45 * data_score
        score = max(blended, intrinsic_score * 0.88)
        score = max(0.05, min(score, 1.0))

        factors = intrinsic_factors + data_factors
        if not exact_match:
            factors.insert(
                0,
                RiskFactor(
                    "match",
                    "Expanded search to nearby conditions",
                    0.0,
                ),
            )
    if accident_count == 0:
        factors = intrinsic_factors + data_factors
        score = max(0.05, min(score, 1.0))

    return RiskResult(
        score=score,
        level=_risk_level(score),
        accident_count=accident_count,
        avg_severity=round(avg_severity, 2),
        relative_risk=round(relative_risk, 2),
        matched_conditions=matched_conditions,
        factors=factors,
        suggestions=_suggestions(score, weather, visibility_mi),
    )
