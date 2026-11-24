"""Capture public Telegram previews for the exhibitor and speaker journals."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from speaker_collect_channels import CHANNELS as SPEAKER_CHANNELS
from telegram_snapshot import ROOT, fetch

DATA = ROOT / "data/portal"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    temp.replace(path)


def snapshot(directory: Path) -> None:
    timezone = ZoneInfo(read(ROOT / "expo.json")["timezone"])
    attempts = [("exhibitors", row) for row in read(DATA / "channels.json")]
    attempts.extend(("speakers", row) for row in SPEAKER_CHANNELS)
    directory.mkdir(parents=True, exist_ok=True)

    def cached_fetch(item):
        group, channel = item
        path = directory / group / f'{channel["id"]}.json'
        if path.exists():
            return read(path)
        checked_at = datetime.now(timezone).isoformat(timespec="seconds")
        record, posts = fetch(channel, checked_at, media_dir=None)
        result = {"channel": record, "posts": posts}
        write(path, result)
        return result

    with ThreadPoolExecutor(8) as pool:
        for result in pool.map(cached_fetch, attempts):
            channel = result["channel"]
            print(channel["id"], channel["status"], len(result["posts"]), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Directory for one dated snapshot, outside docs/")
    snapshot(parser.parse_args().directory)
