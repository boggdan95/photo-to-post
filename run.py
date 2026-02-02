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
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
