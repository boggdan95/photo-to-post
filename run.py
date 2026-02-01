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
    print("review: Not yet implemented (Phase 3)")
    print("Will launch web interface at http://localhost:5000")


def cmd_schedule(args):
    print("schedule: Not yet implemented (Phase 4)")


def cmd_calendar(args):
    print("calendar: Not yet implemented (Phase 4)")


def cmd_publish(args):
    print(f"publish: Not yet implemented (Phase 4)")


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
