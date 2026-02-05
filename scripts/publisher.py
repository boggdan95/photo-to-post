"""Publisher - uploads to Cloudinary and publishes via Meta Graph API."""

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from scripts.utils import BASE_DIR, load_settings

logger = logging.getLogger("photo-to-post")

SCHEDULED_DIR = BASE_DIR / "05_scheduled"
PUBLISHED_DIR = BASE_DIR / "06_published"


def _get_credentials():
    creds_path = BASE_DIR / "config" / "credentials.json"
    try:
        with open(creds_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _upload_to_cloudinary(image_path):
    """Upload an image to Cloudinary and return the public URL."""
    creds = _get_credentials()
    settings = load_settings()

    cloud_name = (
        creds.get("cloudinary_cloud_name")
        or settings.get("apis", {}).get("cloudinary_cloud_name")
    )
    api_key = creds.get("cloudinary_api_key") or os.environ.get("CLOUDINARY_API_KEY")
    api_secret = creds.get("cloudinary_api_secret") or os.environ.get("CLOUDINARY_API_SECRET")

    if not all([cloud_name, api_key, api_secret]):
        raise ValueError(
            "Cloudinary credentials not configured. "
            "Set cloudinary_cloud_name, cloudinary_api_key, cloudinary_api_secret "
            "in config/credentials.json or environment variables."
        )

    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
    )

    result = cloudinary.uploader.upload(str(image_path), folder="photo-to-post")
    url = result.get("secure_url")
    logger.info(f"Uploaded to Cloudinary: {Path(image_path).name} → {url}")
    return url


def _check_container_status(container_id, access_token, max_attempts=10):
    """Check if a media container is ready for publishing."""
    import requests
    import time

    api_base = "https://graph.facebook.com/v21.0"

    for attempt in range(max_attempts):
        resp = requests.get(
            f"{api_base}/{container_id}",
            params={
                "fields": "status_code",
                "access_token": access_token,
            },
            timeout=30,
        )
        if not resp.ok:
            logger.warning(f"Status check failed: {resp.text}")
            time.sleep(2)
            continue

        status = resp.json().get("status_code")
        logger.debug(f"Container {container_id} status: {status}")

        if status == "FINISHED":
            return True
        elif status in ("ERROR", "EXPIRED"):
            logger.error(f"Container {container_id} failed with status: {status}")
            return False

        # Still processing, wait and retry
        time.sleep(2)

    logger.warning(f"Container {container_id} still not ready after {max_attempts} attempts")
    return False


def _publish_to_instagram(image_urls, caption_text, hashtags):
    """Publish a carousel post to Instagram via Meta Graph API.

    For a single image, publishes as a regular post.
    For multiple images, publishes as a carousel.
    """
    creds = _get_credentials()
    access_token = creds.get("meta_access_token") or os.environ.get("META_ACCESS_TOKEN")
    ig_user_id = creds.get("instagram_user_id") or os.environ.get("INSTAGRAM_USER_ID")

    if not access_token or not ig_user_id:
        raise ValueError(
            "Meta API credentials not configured. "
            "Set meta_access_token and instagram_user_id "
            "in config/credentials.json or environment variables."
        )

    import requests
    import time

    full_caption = caption_text
    if hashtags:
        full_caption += "\n\n" + " ".join(hashtags)

    api_base = "https://graph.facebook.com/v21.0"

    if len(image_urls) == 1:
        # Single image post
        resp = requests.post(
            f"{api_base}/{ig_user_id}/media",
            data={
                "image_url": image_urls[0],
                "caption": full_caption,
                "access_token": access_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        creation_id = resp.json()["id"]

    else:
        # Carousel post
        children_ids = []
        for url in image_urls:
            resp = requests.post(
                f"{api_base}/{ig_user_id}/media",
                data={
                    "image_url": url,
                    "is_carousel_item": "true",
                    "access_token": access_token,
                },
                timeout=30,
            )
            if not resp.ok:
                logger.error(f"Meta API error (carousel item): {resp.text}")
                resp.raise_for_status()
            children_ids.append(resp.json()["id"])

        # Wait for all carousel items to be processed
        logger.info("Waiting for carousel items to be processed...")
        for child_id in children_ids:
            if not _check_container_status(child_id, access_token):
                raise RuntimeError(f"Carousel item {child_id} failed to process")

        resp = requests.post(
            f"{api_base}/{ig_user_id}/media",
            data={
                "media_type": "CAROUSEL",
                "caption": full_caption,
                "children": ",".join(children_ids),
                "access_token": access_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        creation_id = resp.json()["id"]

    # Wait for container to be ready before publishing
    logger.info("Waiting for media container to be ready...")
    if not _check_container_status(creation_id, access_token):
        raise RuntimeError(f"Media container {creation_id} failed to process")

    # Publish the container
    resp = requests.post(
        f"{api_base}/{ig_user_id}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": access_token,
        },
        timeout=60,
    )
    if not resp.ok:
        logger.error(f"Publish failed: {resp.text}")
        resp.raise_for_status()
    ig_post_id = resp.json()["id"]

    logger.info(f"Published to Instagram: {ig_post_id}")
    return ig_post_id


def _find_post(post_id):
    """Find a scheduled post by ID."""
    if not SCHEDULED_DIR.exists():
        return None, None
    for d in SCHEDULED_DIR.iterdir():
        pj = d / "post.json"
        if pj.exists():
            with open(pj, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("id") == post_id:
                return d, data
    return None, None


def publish_post(post_id):
    """Publish a scheduled post: upload to Cloudinary, post to Instagram, archive.

    Returns the Instagram post ID on success.
    """
    post_dir, data = _find_post(post_id)
    if not post_dir:
        logger.error(f"Post {post_id} not found in 05_scheduled/")
        return None

    photos_dir = post_dir / "photos"
    photos_data = data.get("photos", [])

    # Step 1: Get image URLs (use existing Cloudinary URLs or upload)
    image_urls = []

    # Check if photos already have Cloudinary URLs (cloud_mode)
    if photos_data and all(p.get("cloudinary_url") for p in photos_data):
        logger.info("Using pre-uploaded Cloudinary URLs...")
        image_urls = [p["cloudinary_url"] for p in photos_data]
    else:
        # Upload photos to Cloudinary
        photo_files = sorted(
            f for f in photos_dir.iterdir()
            if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png")
        )

        if not photo_files:
            logger.error(f"No photos found for post {post_id}")
            return None

        logger.info(f"Uploading {len(photo_files)} photos to Cloudinary...")
        for photo in photo_files:
            url = _upload_to_cloudinary(photo)
            image_urls.append(url)

    # Step 2: Publish to Instagram
    caption = data.get("caption", {})
    logger.info("Publishing to Instagram...")
    ig_post_id = _publish_to_instagram(
        image_urls,
        caption.get("text", ""),
        caption.get("hashtags", []),
    )

    # Step 3: Update post data
    data["status"] = "published"
    data["schedule"]["published_at"] = datetime.now().isoformat()
    data["meta"]["instagram_post_id"] = ig_post_id

    # Step 4: Move to 06_published/{year}/{month}/
    now = datetime.now()
    archive_dir = PUBLISHED_DIR / str(now.year) / f"{now.month:02d}" / post_dir.name
    archive_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(post_dir), str(archive_dir))

    with open(archive_dir / "post.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Published and archived: {post_id} → 06_published/{now.year}/{now.month:02d}/")
    return ig_post_id
