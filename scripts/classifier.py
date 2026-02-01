import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS

from scripts.utils import BASE_DIR, load_settings

logger = logging.getLogger("photo-to-post")

INPUT_DIR = BASE_DIR / "01_input"
CLASSIFIED_DIR = BASE_DIR / "02_classified"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "photo-to-post/1.0"


def _get_exif_data(filepath):
    try:
        img = Image.open(filepath)
        exif = img._getexif()
        if not exif:
            return {}
        return {TAGS.get(k, k): v for k, v in exif.items()}
    except Exception:
        return {}


def _get_gps_info(exif_data):
    gps_info = exif_data.get("GPSInfo")
    if not gps_info:
        return None
    parsed = {}
    for key, val in gps_info.items():
        tag = GPSTAGS.get(key, key)
        parsed[tag] = val
    return parsed


def _convert_to_degrees(value):
    d, m, s = value
    return float(d) + float(m) / 60.0 + float(s) / 3600.0


def read_gps(filepath):
    exif = _get_exif_data(filepath)
    gps = _get_gps_info(exif)
    if not gps:
        return None

    try:
        lat = _convert_to_degrees(gps["GPSLatitude"])
        if gps.get("GPSLatitudeRef", "N") == "S":
            lat = -lat
        lon = _convert_to_degrees(gps["GPSLongitude"])
        if gps.get("GPSLongitudeRef", "E") == "W":
            lon = -lon
        return {"lat": lat, "lon": lon}
    except (KeyError, TypeError, ZeroDivisionError):
        return None


def get_date_taken(filepath):
    exif = _get_exif_data(filepath)
    date_str = exif.get("DateTimeOriginal") or exif.get("DateTime")
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            pass
    stat = filepath.stat()
    return datetime.fromtimestamp(stat.st_mtime)


def reverse_geocode(lat, lon):
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 10},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        addr = data.get("address", {})
        country = addr.get("country", "_unknown")
        city = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("municipality")
            or addr.get("state")
            or "_unknown"
        )
        return country, city
    except Exception as e:
        logger.warning(f"Geocoding failed for ({lat}, {lon}): {e}")
        return "_unknown", "_unknown"


def classify_photo(filepath):
    filepath = Path(filepath)
    gps = read_gps(filepath)
    date_taken = get_date_taken(filepath)
    date_str = date_taken.strftime("%Y%m%d")

    if gps:
        country, city = reverse_geocode(gps["lat"], gps["lon"])
        # Rate limit for Nominatim
        time.sleep(1)
    else:
        logger.info(f"No GPS data for {filepath.name}, moving to _unknown")
        country, city = "_unknown", "_unknown"

    dest_dir = CLASSIFIED_DIR / country / city
    dest_dir.mkdir(parents=True, exist_ok=True)

    new_name = f"{date_str}_{filepath.name}"
    dest_path = dest_dir / new_name

    if dest_path.exists():
        stem = dest_path.stem
        suffix = dest_path.suffix
        i = 1
        while dest_path.exists():
            dest_path = dest_dir / f"{stem}_{i}{suffix}"
            i += 1

    shutil.move(str(filepath), str(dest_path))
    logger.info(f"Classified: {filepath.name} → {country}/{city}/{dest_path.name}")
    return {"country": country, "city": city, "path": str(dest_path)}


def classify_all():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = [
        f
        for f in INPUT_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".tiff")
    ]

    if not files:
        logger.info("No photos found in 01_input/")
        return []

    logger.info(f"Found {len(files)} photos to classify")
    results = []
    for f in sorted(files):
        result = classify_photo(f)
        results.append(result)

    logger.info(f"Classification complete: {len(results)} photos processed")
    return results
