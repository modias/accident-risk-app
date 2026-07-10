VIS_BUCKETS = ["0-1", "1-3", "3-5", "5-10", "10+"]

VIS_BUCKET_LABELS = {
    "0-1": "0–1 miles",
    "1-3": "1–3 miles",
    "3-5": "3–5 miles",
    "5-10": "5–10 miles",
    "10+": "10+ miles",
}


def map_weather(condition: str) -> str:
    c = (condition or "").lower().strip()
    if not c or c == "unknown":
        return "clear"
    if "snow" in c:
        return "snow"
    if any(token in c for token in ("rain", "drizzle", "shower", "thunder")):
        return "rain"
    if any(token in c for token in ("fog", "haze", "mist")):
        return "fog"
    if "ice" in c or "freez" in c:
        return "ice"
    if any(token in c for token in ("cloud", "overcast")):
        return "cloudy"
    return "clear"


def map_place(
    street: str,
    description: str,
    junction: bool,
    traffic_signal: bool,
    amenity: bool,
) -> str:
    street_l = str(street or "").lower()
    desc_l = str(description or "").lower()
    if junction or traffic_signal:
        return "intersection"
    if (
        street_l.startswith("i-")
        or " fwy" in street_l
        or "highway" in desc_l
        or "interstate" in desc_l
    ):
        return "highway"
    if "parking" in desc_l:
        return "parking_lot"
    if amenity:
        return "urban"
    return "rural"


def visibility_bucket(visibility_mi: float) -> str:
    if visibility_mi < 1:
        return "0-1"
    if visibility_mi < 3:
        return "1-3"
    if visibility_mi < 5:
        return "3-5"
    if visibility_mi < 10:
        return "5-10"
    return "10+"
