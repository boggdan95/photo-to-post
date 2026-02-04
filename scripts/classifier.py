import base64
import json
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

# Vision classification with Claude Haiku
VISION_MODEL = "claude-3-5-haiku-20241022"

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


def _get_anthropic_key():
    """Get Anthropic API key from credentials."""
    creds_path = BASE_DIR / "config" / "credentials.json"
    try:
        with open(creds_path, "r", encoding="utf-8") as f:
            creds = json.load(f)
        return creds.get("anthropic_api_key")
    except FileNotFoundError:
        return None


def classify_with_vision(filepath):
    """Use Claude Vision (Haiku) to identify location from image.

    Returns (country, city) tuple or (None, None) if can't identify.
    """
    api_key = _get_anthropic_key()
    if not api_key:
        logger.warning("No Anthropic API key found, skipping vision classification")
        return None, None

    try:
        # Read and encode image
        with open(filepath, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        # Determine media type
        suffix = Path(filepath).suffix.lower()
        media_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
        }.get(suffix, "image/jpeg")

        # Call Claude Vision
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model=VISION_MODEL,
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": """Analyze this photo and identify the location where it was taken.

Look for landmarks, architecture, signs, landscape features, vegetation, or any visual clues.

Respond ONLY with a JSON object in this exact format:
{"country": "Country Name", "city": "City or Region Name", "confidence": "high/medium/low"}

If you cannot identify the location with at least medium confidence, respond with:
{"country": null, "city": null, "confidence": "none"}

Examples:
- Eiffel Tower → {"country": "Francia", "city": "París", "confidence": "high"}
- Pyramids of Teotihuacan → {"country": "México", "city": "San Martín de las Pirámides", "confidence": "high"}
- Generic beach → {"country": null, "city": null, "confidence": "none"}

Respond in Spanish for country/city names when possible."""
                        }
                    ],
                }
            ],
        )

        # Parse response
        response_text = message.content[0].text.strip()

        # Try to extract JSON from response
        if "{" in response_text and "}" in response_text:
            json_start = response_text.index("{")
            json_end = response_text.rindex("}") + 1
            json_str = response_text[json_start:json_end]
            result = json.loads(json_str)

            country = result.get("country")
            city = result.get("city")
            confidence = result.get("confidence", "none")

            if country and city and confidence in ("high", "medium"):
                logger.info(f"Vision classified: {country}/{city} (confidence: {confidence})")
                return country, city
            else:
                logger.info(f"Vision could not identify location (confidence: {confidence})")
                return None, None
        else:
            logger.warning(f"Vision response not in expected format: {response_text}")
            return None, None

    except Exception as e:
        logger.warning(f"Vision classification failed: {e}")
        return None, None


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
        classification_method = "GPS"
        # Rate limit for Nominatim
        time.sleep(1)
    else:
        # Try vision classification
        logger.info(f"No GPS data for {filepath.name}, trying vision classification...")
        country, city = classify_with_vision(filepath)

        if country and city:
            classification_method = "Vision"
        else:
            logger.warning(f"Could not classify {filepath.name}, moving to _manual")
            country, city = "_manual", "_manual"
            classification_method = "Manual"

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
    logger.info(f"Classified: {filepath.name} → {country}/{city}/{dest_path.name} ({classification_method})")
    return {"country": country, "city": city, "path": str(dest_path), "method": classification_method}


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
