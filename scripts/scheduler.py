"""Scheduler - manages post scheduling with diversity rules."""

import json
import logging
import shutil
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from scripts.utils import BASE_DIR, load_settings

logger = logging.getLogger("photo-to-post")

APPROVED_DIR = BASE_DIR / "04_approved"
SCHEDULED_DIR = BASE_DIR / "05_scheduled"
PUBLISHED_DIR = BASE_DIR / "06_published"


def _load_posts_from(directory):
    posts = []
    directory = Path(directory)
    if not directory.exists():
        return posts
    for d in sorted(directory.iterdir()):
        pj = d / "post.json"
        if pj.exists():
            with open(pj, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["_dir"] = str(d)
            posts.append(data)
    return posts


def _load_published_posts():
    """Load all published posts from the nested year/month structure."""
    posts = []
    if not PUBLISHED_DIR.exists():
        return posts

    for year_dir in sorted(PUBLISHED_DIR.iterdir()):
        if not year_dir.is_dir():
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for post_dir in sorted(month_dir.iterdir()):
                pj = post_dir / "post.json"
                if pj.exists():
                    with open(pj, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    data["_dir"] = str(post_dir)
                    posts.append(data)
    return posts


def _get_scheduled_dates():
    """Return a dict of date -> list of post countries already scheduled."""
    scheduled = _load_posts_from(SCHEDULED_DIR)
    by_date = defaultdict(list)
    for p in scheduled:
        sd = p.get("schedule", {}).get("suggested_date")
        if sd:
            by_date[sd].append(p.get("country", ""))
    return by_date


def _get_last_scheduled_countries():
    """Return list of countries from most recent scheduled posts (newest first)."""
    scheduled = _load_posts_from(SCHEDULED_DIR)
    published = _load_published_posts()
    all_posts = scheduled + published

    dated = []
    for p in all_posts:
        sd = p.get("schedule", {}).get("suggested_date")
        st = p.get("schedule", {}).get("suggested_time", "00:00")
        if sd:
            dated.append((sd, st, p.get("country", "")))

    dated.sort(reverse=True)
    return [c for _, _, c in dated]


def _get_grid_state():
    """Get the current state of the Instagram grid (most recent posts first).

    Returns (last_country, count_in_current_row) where count is how many posts
    of last_country are already in the current incomplete row (0-2).
    """
    scheduled = _load_posts_from(SCHEDULED_DIR)
    published = _load_published_posts()
    all_posts = scheduled + published

    if not all_posts:
        return None, 0

    # Sort by best available date (newest first)
    # Priority: suggested_date > published_at > id (which contains timestamp)
    dated = []
    for p in all_posts:
        schedule = p.get("schedule", {})
        sd = schedule.get("suggested_date")
        st = schedule.get("suggested_time", "00:00")

        # Try published_at if no suggested_date
        if not sd:
            published_at = schedule.get("published_at")
            if published_at:
                # Extract date from ISO format
                sd = published_at[:10]
                st = published_at[11:16] if len(published_at) > 16 else "00:00"

        # Fallback to post ID (contains YYYYMMDD_HHMMSS)
        if not sd:
            post_id = p.get("id", "")
            if "_" in post_id:
                # Extract date from id like "post_20260206_232050"
                parts = post_id.split("_")
                if len(parts) >= 2 and len(parts[1]) == 8:
                    try:
                        sd = f"{parts[1][:4]}-{parts[1][4:6]}-{parts[1][6:8]}"
                        st = "00:00"
                    except:
                        pass

        if sd:
            dated.append((sd, st, p.get("country", "")))

    dated.sort(reverse=True)

    if not dated:
        return None, 0

    # Get the most recent posts and count consecutive same-country
    last_country = dated[0][2]
    count = 0
    for _, _, country in dated:
        if country == last_country:
            count += 1
        else:
            break

    # How many are in the current incomplete row (modulo 3)
    remainder = count % 3
    return last_country, remainder


def _apply_diversity_rule(posts, max_consecutive):
    """Reorder posts so no more than max_consecutive from the same country appear in a row."""
    if not posts or max_consecutive <= 0:
        return posts

    result = []
    remaining = list(posts)

    while remaining:
        placed = False
        for i, post in enumerate(remaining):
            # Check if placing this post would violate the rule
            recent = [p.get("country") for p in result[-max_consecutive:]]
            if len(recent) < max_consecutive or not all(c == post.get("country") for c in recent):
                result.append(remaining.pop(i))
                placed = True
                break

        if not placed:
            # Can't avoid violation, just append the rest
            result.extend(remaining)
            break

    return result


def _apply_grid_mode(posts, group_size=3):
    """Reorder posts to group same country in blocks of group_size for Instagram grid aesthetics.

    Considers already published/scheduled posts to complete the current row first.
    """
    if not posts:
        return posts

    from collections import defaultdict

    # Get current grid state (last country and how many in incomplete row)
    last_country, remainder = _get_grid_state()

    # Group posts by country
    by_country = defaultdict(list)
    for post in posts:
        by_country[post.get("country", "Unknown")].append(post)

    result = []

    # If there's an incomplete row, try to complete it first
    if last_country and remainder > 0:
        needed = group_size - remainder  # How many more needed to complete row
        if last_country in by_country and by_country[last_country]:
            # Take posts of the same country to complete the row
            while by_country[last_country] and needed > 0:
                result.append(by_country[last_country].pop(0))
                needed -= 1
            logger.info(f"Grid mode: completing row with {group_size - remainder - needed} more {last_country} posts (had {remainder} published)")

    # Sort countries by number of posts (descending) to handle larger groups first
    sorted_countries = sorted(by_country.keys(), key=lambda c: len(by_country[c]), reverse=True)

    # Keep taking groups of 3 from each country in round-robin fashion
    while any(by_country.values()):
        for country in sorted_countries:
            if by_country[country]:
                # Take up to group_size posts from this country
                chunk = []
                while by_country[country] and len(chunk) < group_size:
                    chunk.append(by_country[country].pop(0))
                result.extend(chunk)

    return result


def preview_schedule():
    """Preview how posts would be scheduled without actually moving them.

    Returns list of dicts with post info and proposed schedule.
    """
    settings = load_settings()
    posts_per_week = settings.get("posts_per_week", 3)
    preferred_times = settings.get("preferred_times", ["07:00", "12:00", "19:00"])
    max_consecutive = settings.get("max_consecutive_same_country", 3)
    grid_mode = settings.get("grid_mode", False)

    approved = _load_posts_from(APPROVED_DIR)
    if not approved:
        return []

    # Apply ordering rule based on mode
    if grid_mode:
        approved = _apply_grid_mode(approved, group_size=3)
    else:
        approved = _apply_diversity_rule(approved, max_consecutive)

    # Calculate posting interval
    days_between = 7 / posts_per_week
    time_idx = 0

    # Find the next available date
    scheduled_dates = _get_scheduled_dates()
    next_date = datetime.now().date() + timedelta(days=1)

    while True:
        date_str = next_date.strftime("%Y-%m-%d")
        existing = scheduled_dates.get(date_str, [])
        if len(existing) < 1:
            break
        next_date += timedelta(days=1)

    preview = []
    current_date = next_date

    for post in approved:
        date_str = current_date.strftime("%Y-%m-%d")
        time_str = preferred_times[time_idx % len(preferred_times)]

        preview.append({
            "id": post["id"],
            "location": post.get("location_display", ""),
            "country": post.get("country", ""),
            "photos": len(post.get("photos", [])),
            "scheduled_date": date_str,
            "scheduled_time": time_str,
        })

        time_idx += 1
        current_date += timedelta(days=days_between)

    return preview


def _upload_photos_to_cloudinary(post_dir, photos):
    """Upload all photos to Cloudinary and return updated photo entries with URLs."""
    from scripts.publisher import _upload_to_cloudinary

    updated_photos = []
    photos_dir = Path(post_dir) / "photos"

    for photo in photos:
        photo_path = photos_dir / photo["filename"]
        if photo_path.exists() and not photo.get("cloudinary_url"):
            url = _upload_to_cloudinary(photo_path)
            photo = dict(photo)
            photo["cloudinary_url"] = url
        updated_photos.append(photo)

    return updated_photos


def schedule_posts():
    """Schedule approved posts respecting frequency and diversity rules.

    Assigns dates/times to approved posts and moves them to 05_scheduled/.
    If cloud_mode is enabled, uploads photos to Cloudinary.
    """
    settings = load_settings()
    posts_per_week = settings.get("posts_per_week", 3)
    preferred_times = settings.get("preferred_times", ["07:00", "12:00", "19:00"])
    max_consecutive = settings.get("max_consecutive_same_country", 3)
    grid_mode = settings.get("grid_mode", False)
    cloud_mode = settings.get("cloud_mode", False)

    approved = _load_posts_from(APPROVED_DIR)
    if not approved:
        logger.info("No approved posts to schedule.")
        return []

    # Apply ordering rule based on mode
    if grid_mode:
        approved = _apply_grid_mode(approved, group_size=3)
    else:
        approved = _apply_diversity_rule(approved, max_consecutive)

    # Calculate posting interval
    days_between = 7 / posts_per_week
    time_idx = 0

    # Find the next available date
    scheduled_dates = _get_scheduled_dates()
    next_date = datetime.now().date() + timedelta(days=1)

    # Skip dates that already have posts at all preferred times
    while True:
        date_str = next_date.strftime("%Y-%m-%d")
        existing = scheduled_dates.get(date_str, [])
        if len(existing) < 1:  # Max 1 post per slot
            break
        next_date += timedelta(days=1)

    scheduled = []
    current_date = next_date

    for post in approved:
        post_dir = Path(post["_dir"])
        date_str = current_date.strftime("%Y-%m-%d")
        time_str = preferred_times[time_idx % len(preferred_times)]

        # Upload to Cloudinary if cloud_mode is enabled
        if cloud_mode:
            logger.info(f"Uploading photos to Cloudinary for {post['id']}...")
            post["photos"] = _upload_photos_to_cloudinary(post_dir, post["photos"])

        post["status"] = "scheduled"
        post["schedule"]["suggested_date"] = date_str
        post["schedule"]["suggested_time"] = time_str
        post["schedule"]["scheduled_at"] = datetime.now().isoformat()

        # Move to 05_scheduled
        dest = SCHEDULED_DIR / post_dir.name
        SCHEDULED_DIR.mkdir(parents=True, exist_ok=True)
        del post["_dir"]
        shutil.move(str(post_dir), str(dest))

        with open(dest / "post.json", "w", encoding="utf-8") as f:
            json.dump(post, f, ensure_ascii=False, indent=2)

        logger.info(f"Scheduled: {post['id']} → {date_str} {time_str} ({post.get('location_display', '')})")
        scheduled.append(post)

        # Advance date
        time_idx += 1
        current_date += timedelta(days=days_between)
        # Round to next whole day if fractional
        if days_between != int(days_between) and time_idx % posts_per_week == 0:
            current_date = current_date.replace(hour=0, minute=0, second=0, microsecond=0) if hasattr(current_date, 'hour') else current_date

    logger.info(f"Total scheduled: {len(scheduled)}")
    return scheduled


def get_calendar():
    """Return a calendar view of scheduled and published posts.

    Returns dict: {date_str: [post_summary, ...]}
    """
    calendar = defaultdict(list)

    for post in _load_posts_from(SCHEDULED_DIR):
        date = post.get("schedule", {}).get("suggested_date", "unknown")
        time = post.get("schedule", {}).get("suggested_time", "")
        calendar[date].append({
            "id": post["id"],
            "location": post.get("location_display", ""),
            "country": post.get("country", ""),
            "time": time,
            "status": "scheduled",
            "photos": len(post.get("photos", [])),
        })

    # Include published posts
    if PUBLISHED_DIR.exists():
        for year_dir in sorted(PUBLISHED_DIR.iterdir()):
            if not year_dir.is_dir():
                continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue
                for post_dir in month_dir.iterdir():
                    pj = post_dir / "post.json"
                    if pj.exists():
                        with open(pj, "r", encoding="utf-8") as f:
                            post = json.load(f)
                        date = post.get("schedule", {}).get("suggested_date", "unknown")
                        calendar[date].append({
                            "id": post["id"],
                            "location": post.get("location_display", ""),
                            "country": post.get("country", ""),
                            "time": post.get("schedule", {}).get("suggested_time", ""),
                            "status": "published",
                            "photos": len(post.get("photos", [])),
                        })

    # Filter out None keys and sort
    filtered = {k: v for k, v in calendar.items() if k is not None}
    return dict(sorted(filtered.items(), key=lambda x: x[0] if x[0] != "unknown" else "9999-99-99"))
