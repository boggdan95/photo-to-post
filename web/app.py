"""Flask web app for reviewing, approving, and scheduling posts."""

import json
import shutil
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.utils import BASE_DIR, load_settings, load_hashtags

app = Flask(__name__)

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
    return None, None


# --- Pages ---

@app.route("/")
def index():
    return render_template("index.html")


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


# --- API endpoints ---

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
        for entry in data["photos"]:
            if entry["filename"] == filename:
                entry["filename"] = new_name
                new_photo_entries.append(entry)
                break

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


@app.route("/api/post/<post_id>/reject", methods=["POST"])
def reject_post(post_id):
    """Delete a draft (photos are already copied, originals were removed)."""
    post_dir, data = _find_post_dir(post_id)
    if not post_dir:
        return jsonify({"error": "Post not found"}), 404

    shutil.rmtree(str(post_dir))
    return jsonify({"ok": True, "status": "rejected"})


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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
