#!/usr/bin/env python3
"""photo-to-post - CLI para automatización de posts en Instagram."""

import argparse
import sys

from scripts.utils import (
    BASE_DIR,
    STAGE_DIRS,
    count_files,
    count_posts,
    ensure_folders,
    setup_logging,
)


def cmd_init(args):
    logger = setup_logging()
    logger.info("Initializing photo-to-post...")
    ensure_folders()
    logger.info("Folder structure created.")
    logger.info(f"Base directory: {BASE_DIR}")
    logger.info("Place your exported photos in 01_input/ and run: python run.py classify")


def cmd_classify(args):
    logger = setup_logging()
    from scripts.classifier import classify_all

    results = classify_all()
    if results:
        countries = {}
        for r in results:
            key = f"{r['country']}/{r['city']}"
            countries[key] = countries.get(key, 0) + 1
        logger.info("Summary:")
        for loc, n in sorted(countries.items()):
            logger.info(f"  {loc}: {n} photos")


def cmd_status(args):
    setup_logging()
    print("\n=== photo-to-post Status ===\n")
    print(f"  01_input:      {count_files(BASE_DIR / '01_input')} photos")
    print(f"  02_classified: {count_files(BASE_DIR / '02_classified')} photos")
    print(f"  03_drafts:     {count_posts(BASE_DIR / '03_drafts')} posts")
    print(f"  04_approved:   {count_posts(BASE_DIR / '04_approved')} posts")
    print(f"  05_scheduled:  {count_posts(BASE_DIR / '05_scheduled')} posts")
    print(f"  06_published:  {count_posts(BASE_DIR / '06_published')} posts")
    print()


def cmd_create_posts(args):
    logger = setup_logging()
    from scripts.post_creator import create_posts

    results = create_posts()
    if results:
        logger.info("Drafts summary:")
        for post in results:
            n = len(post["photos"])
            logger.info(f"  {post['id']} - {post['location_display']} ({n} photos)")
        logger.info(f"\nReview drafts in 03_drafts/ or run: python run.py review")


def cmd_review(args):
    logger = setup_logging()
    logger.info("Starting web interface at http://localhost:5000")
    import sys
    sys.path.insert(0, str(BASE_DIR))
    from web.app import app
    app.run(debug=True, port=5000, use_reloader=False)


def cmd_schedule(args):
    logger = setup_logging()
    from scripts.scheduler import schedule_posts

    results = schedule_posts()
    if results:
        logger.info("Scheduled posts:")
        for post in results:
            sched = post.get("schedule", {})
            logger.info(
                f"  {post['id']} → {sched.get('suggested_date')} "
                f"{sched.get('suggested_time')} ({post.get('location_display', '')})"
            )
        logger.info(f"\nView calendar: python run.py calendar")


def cmd_calendar(args):
    setup_logging()
    from scripts.scheduler import get_calendar

    calendar = get_calendar()
    if not calendar:
        print("\nNo hay posts programados ni publicados.\n")
        return

    print("\n=== Calendario de Publicaciones ===\n")
    last_country = None
    consecutive = 0
    for date, entries in calendar.items():
        for entry in entries:
            status_icon = "[PROG]" if entry["status"] == "scheduled" else "[PUB] "
            country = entry["country"]

            # Diversity warning
            if country == last_country:
                consecutive += 1
            else:
                consecutive = 1
                last_country = country

            warning = " [!] >3 mismo pais" if consecutive > 3 else ""

            print(
                f"  {status_icon} {date} {entry['time']}  "
                f"{entry['location']} ({entry['photos']} fotos){warning}"
            )
    print()


def cmd_publish(args):
    logger = setup_logging()
    from scripts.publisher import publish_post

    post_id = args.post_id
    logger.info(f"Publishing post: {post_id}")
    try:
        ig_id = publish_post(post_id)
        if ig_id:
            logger.info(f"Published successfully. Instagram ID: {ig_id}")
        else:
            logger.error("Publication failed.")
    except ValueError as e:
        logger.error(str(e))
    except Exception as e:
        logger.error(f"Publication error: {e}")


def cmd_auto_publish(args):
    """Auto-publish scheduled posts that are due."""
    logger = setup_logging()
    from datetime import datetime
    from pathlib import Path
    import json
    from scripts.publisher import publish_post

    scheduled_dir = BASE_DIR / "05_scheduled"
    if not scheduled_dir.exists():
        logger.info("No scheduled posts folder found.")
        return

    now = datetime.now()
    max_delay_hours = args.max_delay or 24  # Don't publish if more than 24h late

    published_count = 0
    skipped_count = 0

    for post_dir in sorted(scheduled_dir.iterdir()):
        if not post_dir.is_dir():
            continue

        post_json = post_dir / "post.json"
        if not post_json.exists():
            continue

        with open(post_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        schedule = data.get("schedule", {})
        sched_date = schedule.get("suggested_date")
        sched_time = schedule.get("suggested_time", "00:00")

        # Fallback to scheduled_at if suggested_date is null
        if not sched_date and schedule.get("scheduled_at"):
            scheduled_at = schedule["scheduled_at"]
            sched_date = scheduled_at[:10]  # YYYY-MM-DD
            sched_time = scheduled_at[11:16] if len(scheduled_at) > 16 else "00:00"  # HH:MM

        if not sched_date:
            continue

        # Parse scheduled datetime
        try:
            sched_dt = datetime.strptime(f"{sched_date} {sched_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            logger.warning(f"Invalid schedule for {data['id']}: {sched_date} {sched_time}")
            continue

        # Check if it's time to publish
        if sched_dt <= now:
            # Check if too late
            hours_late = (now - sched_dt).total_seconds() / 3600
            if hours_late > max_delay_hours:
                logger.warning(
                    f"Skipping {data['id']}: {hours_late:.1f}h late (max: {max_delay_hours}h)"
                )
                skipped_count += 1
                continue

            logger.info(f"Publishing {data['id']} (scheduled: {sched_date} {sched_time})...")
            try:
                ig_id = publish_post(data["id"])
                if ig_id:
                    logger.info(f"Published {data['id']} → Instagram ID: {ig_id}")
                    published_count += 1
                else:
                    logger.error(f"Failed to publish {data['id']}")
            except Exception as e:
                logger.error(f"Error publishing {data['id']}: {e}")

    logger.info(f"Auto-publish complete: {published_count} published, {skipped_count} skipped")


def cmd_sync(args):
    """Sync local folders with GitHub state after git pull.

    Moves photos from 05_scheduled to 06_published for posts that were
    published by GitHub Actions.
    """
    logger = setup_logging()
    import shutil

    scheduled_dir = BASE_DIR / "05_scheduled"
    published_dir = BASE_DIR / "06_published"

    if not published_dir.exists():
        logger.info("No published folder found.")
        return

    synced = 0

    # Find published posts that have post.json but no photos folder
    for year_dir in published_dir.iterdir():
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

                # If has post.json but no photos, look for them in scheduled
                if post_json.exists() and not photos_dir.exists():
                    # Find matching folder in scheduled
                    scheduled_post = scheduled_dir / post_dir.name
                    scheduled_photos = scheduled_post / "photos"

                    if scheduled_photos.exists():
                        # Move photos to published
                        shutil.move(str(scheduled_photos), str(photos_dir))
                        logger.info(f"Synced photos: {post_dir.name}")
                        synced += 1

                        # Remove empty scheduled folder
                        if scheduled_post.exists():
                            try:
                                scheduled_post.rmdir()
                            except OSError:
                                pass  # Not empty, leave it

    if synced:
        logger.info(f"Synced {synced} posts")
    else:
        logger.info("Everything already in sync")


def main():
    parser = argparse.ArgumentParser(
        description="photo-to-post: Automatización de Instagram"
    )
    sub = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    sub.add_parser("init", help="Crear estructura de carpetas y configuración")
    sub.add_parser("classify", help="Clasificar fotos de 01_input por ubicación")
    sub.add_parser("create-posts", help="Crear borradores de posts")
    sub.add_parser("status", help="Ver estado actual del sistema")
    sub.add_parser("review", help="Abrir interfaz web para revisar posts")
    sub.add_parser("schedule", help="Programar posts aprobados")
    sub.add_parser("calendar", help="Ver calendario de publicaciones")

    pub = sub.add_parser("publish", help="Publicar un post manualmente")
    pub.add_argument("--post-id", required=True, help="ID del post a publicar")

    auto = sub.add_parser("auto-publish", help="Publicar automaticamente posts programados que ya toca")
    auto.add_argument("--max-delay", type=int, default=24, help="Max horas de retraso permitido (default: 24)")

    sub.add_parser("sync", help="Sincronizar fotos locales con estado de GitHub (despues de git pull)")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "classify": cmd_classify,
        "create-posts": cmd_create_posts,
        "status": cmd_status,
        "review": cmd_review,
        "schedule": cmd_schedule,
        "calendar": cmd_calendar,
        "publish": cmd_publish,
        "auto-publish": cmd_auto_publish,
        "sync": cmd_sync,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
