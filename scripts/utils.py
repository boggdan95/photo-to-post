import json
import logging
import os
from pathlib import Path

BASE_DIR = Path("D:/photo-to-post")
STAGE_DIRS = [
    "01_input",
    "02_classified",
    "03_drafts",
    "04_approved",
    "05_scheduled",
    "06_published",
]
CONFIG_DIR = BASE_DIR / "config"
LOGS_DIR = BASE_DIR / "logs"


def ensure_folders():
    for d in STAGE_DIRS:
        (BASE_DIR / d).mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging():
    from datetime import datetime

    log_file = LOGS_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("photo-to-post")


def load_settings():
    path = CONFIG_DIR / "settings.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_hashtags():
    path = CONFIG_DIR / "hashtags.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def count_files(directory, extensions=(".jpg", ".jpeg")):
    directory = Path(directory)
    if not directory.exists():
        return 0
    count = 0
    for f in directory.rglob("*"):
        if f.is_file() and f.suffix.lower() in extensions:
            count += 1
    return count


def count_posts(directory):
    directory = Path(directory)
    if not directory.exists():
        return 0
    count = 0
    for f in directory.rglob("post.json"):
        count += 1
    return count
