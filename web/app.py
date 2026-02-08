"""Flask web app for reviewing, approving, and scheduling posts."""

import json
import shutil
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.utils import BASE_DIR, load_settings, load_hashtags, count_files, count_posts

app = Flask(__name__)


def _get_counts():
    """Get counts for all pipeline stages."""
    return {
        "input": count_files(BASE_DIR / "01_input"),
        "classified": count_files(BASE_DIR / "02_classified"),
        "drafts": count_posts(BASE_DIR / "03_drafts"),
        "approved": count_posts(BASE_DIR / "04_approved"),
        "scheduled": count_posts(BASE_DIR / "05_scheduled"),
        "published": count_posts(BASE_DIR / "06_published"),
    }

CLASSIFIED_DIR = BASE_DIR / "02_classified"
DRAFTS_DIR = BASE_DIR / "03_drafts"
APPROVED_DIR = BASE_DIR / "04_approved"
SCHEDULED_DIR = BASE_DIR / "05_scheduled"
PUBLISHED_DIR = BASE_DIR / "06_published"


def _load_posts(directory, prefix="draft_"):
    """Load all post.json files from a directory."""
    posts = []
    directory = Path(directory)
    if not directory.exists():
        return posts
    for post_dir in sorted(directory.iterdir()):
        if not post_dir.is_dir():
            continue
        post_json = post_dir / "post.json"
        if post_json.exists():
            with open(post_json, "r", encoding="utf-8") as f:
                post = json.load(f)
            post["_dir"] = str(post_dir)
            posts.append(post)
    return posts


def _find_post_dir(post_id):
    """Find the directory containing a post by its ID."""
    # Check main stage directories
    for stage_dir in [DRAFTS_DIR, APPROVED_DIR, SCHEDULED_DIR]:
        if not stage_dir.exists():
            continue
        for d in stage_dir.iterdir():
            if not d.is_dir():
                continue
            pj = d / "post.json"
            if pj.exists():
                with open(pj, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("id") == post_id:
                    return d, data

    # Check published directory (year/month structure)
    if PUBLISHED_DIR.exists():
        for year_dir in PUBLISHED_DIR.iterdir():
            if not year_dir.is_dir():
                continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue
                for d in month_dir.iterdir():
                    if not d.is_dir():
                        continue
                    pj = d / "post.json"
                    if pj.exists():
                        with open(pj, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        if data.get("id") == post_id:
                            return d, data
    return None, None


# --- Pages ---

@app.route("/")
def index():
    counts = _get_counts()
    return render_template("index.html", counts=counts)


@app.route("/classified")
def classified_page():
    """Show classified photos grouped by country/city."""
    locations = []
    if CLASSIFIED_DIR.exists():
        for country_dir in sorted(CLASSIFIED_DIR.iterdir()):
            if not country_dir.is_dir():
                continue
            country = country_dir.name
            for city_dir in sorted(country_dir.iterdir()):
                if not city_dir.is_dir():
                    continue
                city = city_dir.name
                photos = []
                for f in sorted(city_dir.iterdir()):
                    if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                        photos.append({
                            "filename": f.name,
                            "path": f"{country}/{city}/{f.name}"
                        })
                if photos:
                    locations.append({
                        "country": country,
                        "city": city,
                        "photos": photos,
                        "count": len(photos)
                    })
    # Sort by count descending
    locations.sort(key=lambda x: x["count"], reverse=True)
    settings = load_settings()
    min_photos = settings.get("carousel", {}).get("min_photos", 3)
    return render_template("classified.html", locations=locations, min_photos=min_photos)


@app.route("/review")
def review():
    drafts = _load_posts(DRAFTS_DIR)
    return render_template("review.html", posts=drafts)


@app.route("/approved")
def approved():
    posts = _load_posts(APPROVED_DIR)
    return render_template("approved.html", posts=posts)


@app.route("/settings")
def settings_page():
    settings = load_settings()
    hashtags = load_hashtags()
    return render_template("settings.html", settings=settings, hashtags=hashtags)


@app.route("/schedule")
def schedule_page():
    from scripts.scheduler import preview_schedule, get_calendar, _load_posts_from, _load_published_posts
    approved = _load_posts_from(APPROVED_DIR)
    preview = preview_schedule()
    calendar = get_calendar()
    settings = load_settings()

    # Get recent published posts for grid preview (newest first)
    published = _load_published_posts()
    published_for_grid = []
    for p in published:
        schedule = p.get("schedule", {})
        pub_date = schedule.get("published_at") or schedule.get("suggested_date") or p.get("id", "")
        published_for_grid.append({
            "country": p.get("country", ""),
            "location": p.get("location_display", ""),
            "date": pub_date[:10] if pub_date else "",
        })
    # Sort by date descending (newest first)
    published_for_grid.sort(key=lambda x: x["date"], reverse=True)

    return render_template("schedule.html",
                           approved=approved,
                           preview=preview,
                           calendar=calendar,
                           settings=settings,
                           published_for_grid=published_for_grid)


@app.route("/published")
def published_page():
    """Show published posts history."""
    posts = []
    if PUBLISHED_DIR.exists():
        # Iterate through year/month structure
        for year_dir in sorted(PUBLISHED_DIR.iterdir(), reverse=True):
            if not year_dir.is_dir():
                continue
            for month_dir in sorted(year_dir.iterdir(), reverse=True):
                if not month_dir.is_dir():
                    continue
                for post_dir in sorted(month_dir.iterdir(), reverse=True):
                    if not post_dir.is_dir():
                        continue
                    post_json = post_dir / "post.json"
                    if post_json.exists():
                        with open(post_json, "r", encoding="utf-8") as f:
                            post = json.load(f)
                        post["_dir"] = str(post_dir)
                        post["_year"] = year_dir.name
                        post["_month"] = month_dir.name
                        posts.append(post)
    return render_template("published.html", posts=posts)


# --- API endpoints ---

@app.route("/api/status")
def api_status():
    """Return pipeline counts as JSON."""
    return jsonify(_get_counts())


@app.route("/api/classified/<path:photo_path>")
def serve_classified_photo(photo_path):
    """Serve a classified photo."""
    from flask import send_file
    photo_file = CLASSIFIED_DIR / photo_path
    if not photo_file.exists():
        return "Not found", 404
    return send_file(str(photo_file))


@app.route("/api/classified/locations")
def get_locations():
    """Get list of all locations."""
    locations = []
    if CLASSIFIED_DIR.exists():
        for country_dir in sorted(CLASSIFIED_DIR.iterdir()):
            if not country_dir.is_dir():
                continue
            country = country_dir.name
            for city_dir in sorted(country_dir.iterdir()):
                if not city_dir.is_dir():
                    continue
                city = city_dir.name
                locations.append({"country": country, "city": city})
    return jsonify(locations)


@app.route("/api/classified/move", methods=["POST"])
def move_photo():
    """Move a photo to a different location."""
    body = request.get_json()
    photo_path = body.get("photo_path")  # e.g. "Guatemala/Antigua Guatemala/photo.jpg"
    new_country = body.get("new_country")
    new_city = body.get("new_city")

    if not all([photo_path, new_country, new_city]):
        return jsonify({"error": "Missing required fields"}), 400

    src = CLASSIFIED_DIR / photo_path
    if not src.exists():
        return jsonify({"error": "Photo not found"}), 404

    dest_dir = CLASSIFIED_DIR / new_country / new_city
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    shutil.move(str(src), str(dest))

    # Clean up empty directories
    old_city_dir = src.parent
    old_country_dir = old_city_dir.parent
    if old_city_dir.exists() and not any(old_city_dir.iterdir()):
        old_city_dir.rmdir()
    if old_country_dir.exists() and not any(old_country_dir.iterdir()):
        old_country_dir.rmdir()

    return jsonify({"ok": True, "new_path": f"{new_country}/{new_city}/{src.name}"})


@app.route("/api/classified/merge", methods=["POST"])
def merge_locations():
    """Merge one location into another."""
    body = request.get_json()
    from_country = body.get("from_country")
    from_city = body.get("from_city")
    to_country = body.get("to_country")
    to_city = body.get("to_city")

    if not all([from_country, from_city, to_country, to_city]):
        return jsonify({"error": "Missing required fields"}), 400

    src_dir = CLASSIFIED_DIR / from_country / from_city
    if not src_dir.exists():
        return jsonify({"error": "Source location not found"}), 404

    dest_dir = CLASSIFIED_DIR / to_country / to_city
    dest_dir.mkdir(parents=True, exist_ok=True)

    moved = 0
    for f in list(src_dir.iterdir()):
        if f.is_file():
            shutil.move(str(f), str(dest_dir / f.name))
            moved += 1

    # Clean up empty directories
    if src_dir.exists() and not any(src_dir.iterdir()):
        src_dir.rmdir()
    country_dir = CLASSIFIED_DIR / from_country
    if country_dir.exists() and not any(country_dir.iterdir()):
        country_dir.rmdir()

    return jsonify({"ok": True, "moved": moved})


@app.route("/api/run/<command>", methods=["POST"])
def api_run_command(command):
    """Run a pipeline command (classify, create-posts)."""
    import io
    import sys
    import logging

    allowed_commands = ["classify", "create-posts"]
    if command not in allowed_commands:
        return jsonify({"error": f"Command not allowed: {command}"}), 400

    # Capture log output
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter('%(message)s'))

    logger = logging.getLogger("photo-to-post")
    logger.addHandler(handler)

    try:
        if command == "classify":
            from scripts.classifier import classify_all
            results = classify_all()
            message = f"Clasificadas {len(results)} fotos"

        elif command == "create-posts":
            from scripts.post_creator import create_posts
            results = create_posts()
            message = f"Creados {len(results)} posts"

        log_output = log_capture.getvalue()
        logger.removeHandler(handler)

        return jsonify({"ok": True, "message": message, "log": log_output})

    except Exception as e:
        logger.removeHandler(handler)
        return jsonify({"ok": False, "error": str(e), "log": log_capture.getvalue()}), 500


@app.route("/api/settings", methods=["POST"])
def save_settings():
    """Save settings and hashtags configuration."""
    body = request.get_json()

    settings_path = BASE_DIR / "config" / "settings.json"
    hashtags_path = BASE_DIR / "config" / "hashtags.json"

    # Load current settings to preserve fields not in the UI (paths, apis)
    current_settings = load_settings()

    new_settings = body.get("settings", {})
    # Merge: keep paths and apis from current, update the rest
    current_settings["language"] = new_settings.get("language", current_settings.get("language"))
    current_settings["posts_per_week"] = new_settings.get("posts_per_week", current_settings.get("posts_per_week"))
    current_settings["preferred_times"] = new_settings.get("preferred_times", current_settings.get("preferred_times"))
    current_settings["max_consecutive_same_country"] = new_settings.get("max_consecutive_same_country", current_settings.get("max_consecutive_same_country"))
    current_settings["grid_mode"] = new_settings.get("grid_mode", current_settings.get("grid_mode", False))
    current_settings["cloud_mode"] = new_settings.get("cloud_mode", current_settings.get("cloud_mode", False))
    current_settings["caption_style"] = new_settings.get("caption_style", current_settings.get("caption_style"))
    current_settings["carousel"] = new_settings.get("carousel", current_settings.get("carousel"))

    # Save settings
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(current_settings, f, ensure_ascii=False, indent=2)

    # Save hashtags
    new_hashtags = body.get("hashtags", {})
    with open(hashtags_path, "w", encoding="utf-8") as f:
        json.dump(new_hashtags, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True})


@app.route("/api/post/<post_id>/photos")
def get_post_photos(post_id):
    """Serve photo list for a post."""
    post_dir, data = _find_post_dir(post_id)
    if not post_dir:
        return jsonify({"error": "Post not found"}), 404
    photos_dir = post_dir / "photos"
    photos = []
    if photos_dir.exists():
        for f in sorted(photos_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                photos.append(f.name)
    return jsonify({"photos": photos, "post_id": post_id})


@app.route("/api/photo/<post_id>/<filename>")
def serve_photo(post_id, filename):
    """Serve a photo file."""
    post_dir, _ = _find_post_dir(post_id)
    if not post_dir:
        return "Not found", 404
    photo_path = post_dir / "photos" / filename
    if not photo_path.exists():
        return "Not found", 404
    from flask import send_file
    return send_file(str(photo_path))


@app.route("/api/post/<post_id>/caption", methods=["POST"])
def update_caption(post_id):
    """Update caption text for a post."""
    post_dir, data = _find_post_dir(post_id)
    if not post_dir:
        return jsonify({"error": "Post not found"}), 404

    body = request.get_json()
    if "text" in body:
        data["caption"]["text"] = body["text"]
        data["caption"]["edited"] = True
    if "hashtags" in body:
        data["caption"]["hashtags"] = body["hashtags"]

    with open(post_dir / "post.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True})


@app.route("/api/post/<post_id>/regenerate-caption", methods=["POST"])
def regenerate_caption(post_id):
    """Regenerate caption using AI."""
    post_dir, data = _find_post_dir(post_id)
    if not post_dir:
        return jsonify({"error": "Post not found"}), 404

    body = request.get_json() or {}
    context = body.get("context", "").strip()

    try:
        from scripts.caption_generator import generate_caption
        from scripts.post_creator import _select_hashtags

        country = data.get("country", "")
        city = data.get("city", "")
        photo_count = len(data.get("photos", []))

        # Get date from first photo
        first_photo = data.get("photos", [{}])[0]
        taken_at = first_photo.get("taken_at", "")
        date_str = taken_at[:10] if taken_at else ""

        # Generate new caption with optional context
        caption_text, ai_hashtags = generate_caption(country, city, photo_count, date_str, context)

        # Get full hashtags
        hashtags = _select_hashtags(country, city, ai_hashtags)

        # Update post
        data["caption"]["text"] = caption_text
        data["caption"]["hashtags"] = hashtags
        data["caption"]["generated_by"] = "claude-api"
        data["caption"]["edited"] = False

        with open(post_dir / "post.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return jsonify({
            "ok": True,
            "caption": caption_text,
            "hashtags": hashtags
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _return_photo_to_classified(photo_path, photo_entry, country, city):
    """Move a photo back to 02_classified."""
    if not photo_path.exists():
        return False

    dest_dir = CLASSIFIED_DIR / country / city
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Use original name if available
    original_name = photo_entry.get("original_name", photo_path.name)
    dest = dest_dir / original_name

    # Handle name conflicts
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    shutil.move(str(photo_path), str(dest))
    return True


@app.route("/api/post/<post_id>/photo/<filename>", methods=["DELETE"])
def delete_photo(post_id, filename):
    """Remove a photo from a post's carousel and return it to classified."""
    post_dir, data = _find_post_dir(post_id)
    if not post_dir:
        return jsonify({"error": "Post not found"}), 404

    photos_dir = post_dir / "photos"
    photo_path = photos_dir / filename

    # Don't allow deleting the last photo
    if len(data["photos"]) <= 1:
        return jsonify({"error": "Cannot delete the last photo"}), 400

    # Find photo entry and move to classified
    photo_entry = next((p for p in data["photos"] if p["filename"] == filename), {})
    country = data.get("country", "_recovered")
    city = data.get("city", "_recovered")
    _return_photo_to_classified(photo_path, photo_entry, country, city)

    # Remove from data and renumber remaining photos
    data["photos"] = [p for p in data["photos"] if p["filename"] != filename]

    # Renumber remaining photos
    temp_dir = post_dir / "_temp_renumber"
    temp_dir.mkdir(exist_ok=True)

    new_photo_entries = []
    for i, entry in enumerate(data["photos"], 1):
        old_path = photos_dir / entry["filename"]
        new_name = f"{i:02d}.jpg"
        if old_path.exists():
            shutil.move(str(old_path), str(temp_dir / new_name))
        entry = dict(entry)
        entry["filename"] = new_name
        new_photo_entries.append(entry)

    # Move back
    for f in temp_dir.iterdir():
        shutil.move(str(f), str(photos_dir / f.name))
    temp_dir.rmdir()

    data["photos"] = new_photo_entries
    with open(post_dir / "post.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True, "remaining": len(new_photo_entries)})


@app.route("/api/post/<post_id>/reorder", methods=["POST"])
def reorder_photos(post_id):
    """Reorder photos in a post."""
    post_dir, data = _find_post_dir(post_id)
    if not post_dir:
        return jsonify({"error": "Post not found"}), 404

    body = request.get_json()
    new_order = body.get("order", [])  # list of filenames in new order

    photos_dir = post_dir / "photos"
    temp_dir = post_dir / "_temp_reorder"
    temp_dir.mkdir(exist_ok=True)

    # Build a lookup from current filename to photo entry
    entry_by_filename = {entry["filename"]: entry for entry in data["photos"]}

    # Move to temp with new numbering
    new_photo_entries = []
    for i, filename in enumerate(new_order, 1):
        src = photos_dir / filename
        if not src.exists():
            continue
        ext = src.suffix
        new_name = f"{i:02d}{ext}"
        shutil.move(str(src), str(temp_dir / new_name))

        # Update photo entry
        entry = entry_by_filename.get(filename)
        if entry:
            entry = dict(entry)  # copy to avoid mutation issues
            entry["filename"] = new_name
            new_photo_entries.append(entry)

    # Move back
    for f in temp_dir.iterdir():
        shutil.move(str(f), str(photos_dir / f.name))
    temp_dir.rmdir()

    data["photos"] = new_photo_entries
    with open(post_dir / "post.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True})


@app.route("/api/post/<post_id>/approve", methods=["POST"])
def approve_post(post_id):
    """Move a draft to approved."""
    post_dir, data = _find_post_dir(post_id)
    if not post_dir or data.get("status") != "draft":
        return jsonify({"error": "Post not found or not a draft"}), 404

    data["status"] = "approved"
    data["meta"]["approved_at"] = datetime.now().isoformat()

    dest = APPROVED_DIR / f"post_{post_id}"
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(str(post_dir), str(dest))

    with open(dest / "post.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True, "status": "approved"})


@app.route("/api/post/<post_id>/unapprove", methods=["POST"])
def unapprove_post(post_id):
    """Move an approved post back to drafts for further editing."""
    post_dir = APPROVED_DIR / f"post_{post_id}"
    if not post_dir.exists():
        return jsonify({"error": "Post not found in approved"}), 404

    post_json = post_dir / "post.json"
    with open(post_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Update status back to draft
    data["status"] = "draft"
    data["meta"]["approved_at"] = None

    # Move back to drafts
    dest = DRAFTS_DIR / f"draft_{post_id}"
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(str(post_dir), str(dest))

    with open(dest / "post.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True, "status": "draft"})


@app.route("/api/post/<post_id>/reject", methods=["POST"])
def reject_post(post_id):
    """Reject a draft and return photos to classified."""
    post_dir, data = _find_post_dir(post_id)
    if not post_dir:
        return jsonify({"error": "Post not found"}), 404

    # Move all photos back to classified
    photos_dir = post_dir / "photos"
    country = data.get("country", "_recovered")
    city = data.get("city", "_recovered")
    returned = 0

    if photos_dir.exists():
        for photo_entry in data.get("photos", []):
            photo_path = photos_dir / photo_entry["filename"]
            if _return_photo_to_classified(photo_path, photo_entry, country, city):
                returned += 1

    # Now remove the empty draft directory
    shutil.rmtree(str(post_dir))
    return jsonify({"ok": True, "status": "rejected", "photos_returned": returned})


@app.route("/api/post/<post_id>/split", methods=["POST"])
def split_post(post_id):
    """Split a post into two posts at a given index."""
    post_dir, data = _find_post_dir(post_id)
    if not post_dir:
        return jsonify({"error": "Post not found"}), 404

    body = request.get_json()
    split_after = body.get("split_after", 5)  # Split after this many photos

    photos = data.get("photos", [])
    if len(photos) <= split_after:
        return jsonify({"error": "Not enough photos to split"}), 400

    settings = load_settings()
    min_photos = settings.get("carousel", {}).get("min_photos", 3)

    # Check both parts will have enough photos
    first_part = photos[:split_after]
    second_part = photos[split_after:]

    if len(first_part) < min_photos or len(second_part) < min_photos:
        return jsonify({
            "error": f"Both parts must have at least {min_photos} photos. "
                     f"First: {len(first_part)}, Second: {len(second_part)}"
        }), 400

    # Create new post for second part
    from datetime import datetime
    new_post_id = f"post_{datetime.now().strftime('%Y%m%d')}_{datetime.now().strftime('%H%M%S')}"
    new_draft_dir = DRAFTS_DIR / f"draft_{new_post_id}"
    new_photos_dir = new_draft_dir / "photos"
    new_photos_dir.mkdir(parents=True, exist_ok=True)

    # Move photos to new post and renumber
    photos_dir = post_dir / "photos"
    new_photo_entries = []
    for i, entry in enumerate(second_part, 1):
        old_path = photos_dir / entry["filename"]
        new_name = f"{i:02d}.jpg"
        if old_path.exists():
            shutil.move(str(old_path), str(new_photos_dir / new_name))
        new_entry = dict(entry)
        new_entry["filename"] = new_name
        new_photo_entries.append(new_entry)

    # Create new post.json
    new_post_data = {
        "id": new_post_id,
        "status": "draft",
        "country": data["country"],
        "city": data["city"],
        "location_display": data["location_display"],
        "photos": new_photo_entries,
        "caption": {
            "text": data["caption"]["text"],
            "hashtags": data["caption"]["hashtags"],
            "generated_by": "split",
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
            "split_from": post_id,
        },
    }

    with open(new_draft_dir / "post.json", "w", encoding="utf-8") as f:
        json.dump(new_post_data, f, ensure_ascii=False, indent=2)

    # Update original post - renumber remaining photos
    temp_dir = post_dir / "_temp_split"
    temp_dir.mkdir(exist_ok=True)

    updated_entries = []
    for i, entry in enumerate(first_part, 1):
        old_path = photos_dir / entry["filename"]
        new_name = f"{i:02d}.jpg"
        if old_path.exists():
            shutil.move(str(old_path), str(temp_dir / new_name))
        new_entry = dict(entry)
        new_entry["filename"] = new_name
        updated_entries.append(new_entry)

    for f in temp_dir.iterdir():
        shutil.move(str(f), str(photos_dir / f.name))
    temp_dir.rmdir()

    data["photos"] = updated_entries
    with open(post_dir / "post.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({
        "ok": True,
        "original_photos": len(first_part),
        "new_post_id": new_post_id,
        "new_post_photos": len(second_part)
    })


@app.route("/api/post/<post_id>/split-select", methods=["POST"])
def split_post_select(post_id):
    """Split a post by selecting specific photos to move to new post."""
    post_dir, data = _find_post_dir(post_id)
    if not post_dir:
        return jsonify({"error": "Post not found"}), 404

    body = request.get_json()
    photos_to_move = set(body.get("photos_to_move", []))

    if not photos_to_move:
        return jsonify({"error": "No photos selected to move"}), 400

    photos = data.get("photos", [])
    settings = load_settings()
    min_photos = settings.get("carousel", {}).get("min_photos", 3)

    # Separate photos
    keep_photos = [p for p in photos if p["filename"] not in photos_to_move]
    move_photos = [p for p in photos if p["filename"] in photos_to_move]

    if len(keep_photos) < min_photos or len(move_photos) < min_photos:
        return jsonify({
            "error": f"Both posts must have at least {min_photos} photos"
        }), 400

    # Create new post
    new_post_id = f"post_{datetime.now().strftime('%Y%m%d')}_{datetime.now().strftime('%H%M%S')}"
    new_draft_dir = DRAFTS_DIR / f"draft_{new_post_id}"
    new_photos_dir = new_draft_dir / "photos"
    new_photos_dir.mkdir(parents=True, exist_ok=True)

    photos_dir = post_dir / "photos"

    # Move selected photos to new post and renumber
    new_photo_entries = []
    for i, entry in enumerate(move_photos, 1):
        old_path = photos_dir / entry["filename"]
        new_name = f"{i:02d}.jpg"
        if old_path.exists():
            shutil.move(str(old_path), str(new_photos_dir / new_name))
        new_entry = dict(entry)
        new_entry["filename"] = new_name
        new_photo_entries.append(new_entry)

    # Create new post.json with placeholder caption
    new_post_data = {
        "id": new_post_id,
        "status": "draft",
        "country": data["country"],
        "city": data["city"],
        "location_display": data["location_display"],
        "photos": new_photo_entries,
        "caption": {
            "text": "[Editar caption]",
            "hashtags": data["caption"]["hashtags"],
            "generated_by": "split",
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
            "split_from": post_id,
        },
    }

    with open(new_draft_dir / "post.json", "w", encoding="utf-8") as f:
        json.dump(new_post_data, f, ensure_ascii=False, indent=2)

    # Renumber remaining photos in original post
    temp_dir = post_dir / "_temp_split"
    temp_dir.mkdir(exist_ok=True)

    updated_entries = []
    for i, entry in enumerate(keep_photos, 1):
        old_path = photos_dir / entry["filename"]
        new_name = f"{i:02d}.jpg"
        if old_path.exists():
            shutil.move(str(old_path), str(temp_dir / new_name))
        new_entry = dict(entry)
        new_entry["filename"] = new_name
        updated_entries.append(new_entry)

    for f in temp_dir.iterdir():
        shutil.move(str(f), str(photos_dir / f.name))
    temp_dir.rmdir()

    data["photos"] = updated_entries
    with open(post_dir / "post.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({
        "ok": True,
        "original_photos": len(keep_photos),
        "new_post_id": new_post_id,
        "new_post_photos": len(move_photos)
    })


@app.route("/api/posts/approve-bulk", methods=["POST"])
def approve_bulk():
    """Approve multiple posts at once."""
    body = request.get_json()
    post_ids = body.get("post_ids", [])
    results = []
    for pid in post_ids:
        post_dir, data = _find_post_dir(pid)
        if not post_dir or data.get("status") != "draft":
            results.append({"id": pid, "ok": False})
            continue

        data["status"] = "approved"
        data["meta"]["approved_at"] = datetime.now().isoformat()

        dest = APPROVED_DIR / f"post_{pid}"
        APPROVED_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(post_dir), str(dest))

        with open(dest / "post.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        results.append({"id": pid, "ok": True})

    return jsonify({"results": results})


@app.route("/api/schedule/confirm", methods=["POST"])
def confirm_schedule():
    """Execute the scheduled posts - move from approved to scheduled."""
    from scripts.scheduler import schedule_posts
    try:
        scheduled = schedule_posts()
        return jsonify({"ok": True, "count": len(scheduled)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/schedule/confirm-custom", methods=["POST"])
def confirm_schedule_custom():
    """Execute scheduled posts with custom order and dates from UI."""
    body = request.get_json()
    schedule_data = body.get("schedule", [])

    if not schedule_data:
        return jsonify({"error": "No schedule data provided"}), 400

    settings = load_settings()
    cloud_mode = settings.get("cloud_mode", False)

    scheduled_count = 0

    for item in schedule_data:
        post_id = item.get("post_id")
        scheduled_date = item.get("scheduled_date")
        scheduled_time = item.get("scheduled_time")

        if not all([post_id, scheduled_date, scheduled_time]):
            continue

        # Find post in approved
        post_dir = APPROVED_DIR / f"post_{post_id}"
        if not post_dir.exists():
            continue

        post_json = post_dir / "post.json"
        with open(post_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Update schedule
        scheduled_at = f"{scheduled_date}T{scheduled_time}:00"
        data["status"] = "scheduled"
        data["schedule"]["scheduled_at"] = scheduled_at

        # Upload to Cloudinary if cloud_mode
        if cloud_mode:
            from scripts.scheduler import _upload_photos_to_cloudinary
            data["photos"] = _upload_photos_to_cloudinary(post_dir, data["photos"])

        # Move to scheduled
        SCHEDULED_DIR.mkdir(parents=True, exist_ok=True)
        dest = SCHEDULED_DIR / post_dir.name
        shutil.move(str(post_dir), str(dest))

        with open(dest / "post.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        scheduled_count += 1

    return jsonify({"ok": True, "count": scheduled_count})


@app.route("/api/post/<post_id>/publish-now", methods=["POST"])
def publish_now(post_id):
    """Publish an approved post immediately."""
    # Find the post in approved folder
    post_dir = APPROVED_DIR / f"post_{post_id}"
    if not post_dir.exists():
        return jsonify({"error": "Post not found in approved"}), 404

    post_json = post_dir / "post.json"
    with open(post_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Move to scheduled first
    SCHEDULED_DIR.mkdir(parents=True, exist_ok=True)
    scheduled_path = SCHEDULED_DIR / post_dir.name
    shutil.move(str(post_dir), str(scheduled_path))

    # Update status
    data["status"] = "scheduled"
    data["schedule"]["scheduled_at"] = datetime.now().isoformat()
    with open(scheduled_path / "post.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Now publish
    try:
        from scripts.publisher import publish_post
        ig_post_id = publish_post(post_id)
        if ig_post_id:
            return jsonify({"ok": True, "instagram_post_id": ig_post_id})
        else:
            return jsonify({"error": "Failed to publish"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sync", methods=["POST"])
def api_sync():
    """Run git pull and sync local photos with GitHub state."""
    import subprocess
    import shutil

    results = {"pulled": False, "synced": 0, "errors": []}

    # Git pull
    try:
        result = subprocess.run(
            ["git", "pull"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            results["pulled"] = True
            results["pull_message"] = result.stdout.strip() or "Already up to date"
        else:
            results["errors"].append(f"Git pull failed: {result.stderr}")
    except Exception as e:
        results["errors"].append(f"Git pull error: {e}")

    # Sync photos
    for year_dir in PUBLISHED_DIR.iterdir() if PUBLISHED_DIR.exists() else []:
        if not year_dir.is_dir():
            continue
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir():
                continue
            for post_dir in month_dir.iterdir():
                if not post_dir.is_dir():
                    continue

                photos_dir = post_dir / "photos"
                post_json = post_dir / "post.json"

                if post_json.exists() and not photos_dir.exists():
                    scheduled_post = SCHEDULED_DIR / post_dir.name
                    scheduled_photos = scheduled_post / "photos"

                    if scheduled_photos.exists():
                        shutil.move(str(scheduled_photos), str(photos_dir))
                        results["synced"] += 1

                        if scheduled_post.exists():
                            try:
                                scheduled_post.rmdir()
                            except OSError:
                                pass

    return jsonify({"ok": True, **results})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
