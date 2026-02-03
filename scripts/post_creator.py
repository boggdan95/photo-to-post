"""Post creator - groups classified photos into carousel drafts."""

import json
import logging
import random
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from scripts.caption_generator import generate_caption
from scripts.classifier import get_date_taken, read_gps
from scripts.utils import BASE_DIR, load_hashtags, load_settings

logger = logging.getLogger("photo-to-post")

CLASSIFIED_DIR = BASE_DIR / "02_classified"
DRAFTS_DIR = BASE_DIR / "03_drafts"


def _scan_classified():
    """Scan 02_classified and return photos grouped by country/city."""
    groups = defaultdict(list)
    if not CLASSIFIED_DIR.exists():
        return groups

    for photo in CLASSIFIED_DIR.rglob("*"):
        if not photo.is_file() or photo.suffix.lower() not in (".jpg", ".jpeg", ".png", ".tiff"):
            continue
        # Path structure: 02_classified/{country}/{city}/{file}
        rel = photo.relative_to(CLASSIFIED_DIR)
        parts = rel.parts
        if len(parts) < 3:
            continue
        country, city = parts[0], parts[1]
        date_taken = get_date_taken(photo)
        groups[(country, city)].append({
            "path": photo,
            "date": date_taken,
        })

    # Sort photos within each group by date
    for key in groups:
        groups[key].sort(key=lambda x: x["date"])

    return groups


def _split_into_posts(photos, min_photos, max_photos):
    """Split a list of photos into post-sized chunks.

    Groups by date proximity (same day), then fills up to max_photos.
    If a group has fewer than min_photos, it gets merged with adjacent groups.
    """
    if not photos:
        return []

    # Group by date (same day)
    day_groups = defaultdict(list)
    for p in photos:
        day_key = p["date"].strftime("%Y-%m-%d")
        day_groups[day_key].append(p)

    # Build posts from day groups
    posts = []
    current_batch = []

    for day_key in sorted(day_groups.keys()):
        day_photos = day_groups[day_key]

        if len(current_batch) + len(day_photos) <= max_photos:
            current_batch.extend(day_photos)
        else:
            # Flush current batch if it has enough photos
            if len(current_batch) >= min_photos:
                posts.append(current_batch)
                current_batch = []

            # If this day alone exceeds max, split it
            while len(day_photos) > max_photos:
                posts.append(day_photos[:max_photos])
                day_photos = day_photos[max_photos:]
            current_batch.extend(day_photos)

    # Handle remaining photos
    if current_batch:
        if len(current_batch) >= min_photos:
            posts.append(current_batch)
        elif posts:
            # Merge with last post if possible
            combined = posts[-1] + current_batch
            if len(combined) <= max_photos:
                posts[-1] = combined
            else:
                # Keep as small post anyway
                posts.append(current_batch)
        else:
            # Only group and it's small - keep it anyway
            posts.append(current_batch)

    return posts


def _select_hashtags(country, city, ai_hashtags=None):
    """Select hashtags: AI-generated + base + country from JSON."""
    ht = load_hashtags()
    counts = ht.get("hashtags_per_post", {})

    selected = []

    # AI-generated hashtags (specific to the content)
    if ai_hashtags:
        selected.extend(ai_hashtags)

    # Base hashtags
    base = ht.get("base", [])
    n_base = min(counts.get("base", 3), len(base))
    selected.extend(random.sample(base, n_base))

    # Country hashtags
    country_tags = ht.get("by_country", {}).get(country, [])
    n_country = min(counts.get("country", 2), len(country_tags))
    if country_tags:
        selected.extend(random.sample(country_tags, n_country))

    return selected


def _generate_post_id():
    now = datetime.now()
    return f"post_{now.strftime('%Y%m%d')}_{now.strftime('%H%M%S')}"


def create_posts():
    """Create draft posts from classified photos.

    Groups photos by location, splits into carousel-sized posts,
    generates captions, assigns hashtags, and saves to 03_drafts/.
    """
    settings = load_settings()
    min_photos = settings.get("carousel", {}).get("min_photos", 3)
    max_photos = settings.get("carousel", {}).get("max_photos", 10)

    groups = _scan_classified()
    if not groups:
        logger.info("No classified photos found in 02_classified/")
        return []

    created = []

    for (country, city), photos in groups.items():
        post_batches = _split_into_posts(photos, min_photos, max_photos)

        for batch in post_batches:
            post_id = _generate_post_id()
            draft_dir = DRAFTS_DIR / f"draft_{post_id}"
            photos_dir = draft_dir / "photos"
            photos_dir.mkdir(parents=True, exist_ok=True)

            # Copy photos into draft
            photo_entries = []
            for i, p in enumerate(batch, 1):
                ext = p["path"].suffix
                dest_name = f"{i:02d}{ext}"
                dest_path = photos_dir / dest_name
                shutil.copy2(str(p["path"]), str(dest_path))

                gps = read_gps(p["path"])
                photo_entries.append({
                    "filename": dest_name,
                    "original_name": p["path"].name,
                    "gps": gps,
                    "taken_at": p["date"].isoformat(),
                })

            # Generate caption + AI hashtags
            earliest_date = batch[0]["date"].strftime("%Y-%m-%d")
            caption_text, ai_hashtags = generate_caption(country, city, len(batch), earliest_date)

            # Combine AI hashtags with base + country hashtags
            hashtags = _select_hashtags(country, city, ai_hashtags)

            # Build post.json
            post_data = {
                "id": post_id,
                "status": "draft",
                "country": country,
                "city": city,
                "location_display": f"{city}, {country}",
                "photos": photo_entries,
                "caption": {
                    "text": caption_text,
                    "hashtags": hashtags,
                    "generated_by": "claude-api",
                    "edited": False,
                },
                "schedule": {
                    "suggested_date": None,
                    "suggested_time": None,
                    "scheduled_at": None,
                    "published_at": None,
                },
                "meta": {
                    "created_at": datetime.now().isoformat(),
                    "approved_at": None,
                    "instagram_post_id": None,
                },
            }

            post_json_path = draft_dir / "post.json"
            with open(post_json_path, "w", encoding="utf-8") as f:
                json.dump(post_data, f, ensure_ascii=False, indent=2)

            # Remove originals from 02_classified
            for p in batch:
                p["path"].unlink()

            logger.info(
                f"Created draft: {post_id} - {city}, {country} "
                f"({len(batch)} photos)"
            )
            created.append(post_data)

            # Small delay between posts to get unique IDs
            import time
            time.sleep(1)

    # Clean up empty directories in 02_classified
    _cleanup_empty_dirs(CLASSIFIED_DIR)

    logger.info(f"Total drafts created: {len(created)}")
    return created


def _cleanup_empty_dirs(path):
    """Remove empty directories recursively."""
    for d in sorted(path.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
