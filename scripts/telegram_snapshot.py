"""Fetch selected public Telegram channel previews into an isolated snapshot.

Example: python scripts/telegram_snapshot.py --indices 0:47 --output data/raw/refresh/a.json
Only reads project channel/post data; writes the requested snapshot and optimized images.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import local
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO

ROOT = Path(__file__).resolve().parents[1]
UA = "Mozilla/5.0 (compatible; MebelExpoPublicSnapshot/1.0)"
MAX_IMAGE_BYTES = 12_000_000
MAX_HTML_BYTES = 8_000_000
TIMEOUT = (8, 25)
THREAD = local()


def get(url: str, limit: int) -> requests.Response:
    if not hasattr(THREAD, "session"):
        THREAD.session = requests.Session()
        THREAD.session.headers["User-Agent"] = UA
    with THREAD.session.get(url, timeout=TIMEOUT, stream=True) as r:
        r.raise_for_status()
        chunks, size = [], 0
        for chunk in r.iter_content(65536):
            size += len(chunk)
            if size > limit:
                raise ValueError(f"response exceeds byte limit ({limit})")
            chunks.append(chunk)
        r._content = b"".join(chunks)
        return r


def slug_for(channel: dict) -> str:
    return urlparse(channel.get("preview_url") or channel["url"]).path.rstrip("/").split("/")[-1]


def image_to_webp(url: str, media_dir: Path, seed: str) -> str | None:
    if not url or not url.startswith("https://"):
        return None
    try:
        r = get(url, MAX_IMAGE_BYTES)
        image = Image.open(BytesIO(r.content))
        image.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
        name = hashlib.sha256((seed + "\0" + url).encode()).hexdigest()[:24] + ".webp"
        media_dir.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(media_dir / name, "WEBP", quality=78, method=5)
        return "media/tg/" + name
    except Exception:
        return None


def fetch(channel: dict, checked: str, media_dir: Path | None, limit: int = 10) -> tuple[dict, list[dict]]:
    row = dict(channel)
    slug = slug_for(row)
    url = "https://t.me/s/" + slug
    try:
        response = get(url, MAX_HTML_BYTES)
        soup = BeautifulSoup(response.content, "html.parser")
        nodes = [
            node for node in soup.select(".tgme_widget_message[data-post]")
            if re.fullmatch(re.escape(slug) + r"/\d+", node["data-post"], re.I)
            and node.select_one("time[datetime]")
            and node.select_one(".tgme_widget_message_text, .tgme_widget_message_photo_wrap, "
                                ".tgme_widget_message_video_thumb, .tgme_widget_message_document_wrap, "
                                ".tgme_widget_message_video_player, .tgme_widget_message_voice_player, "
                                ".tgme_widget_message_poll, .tgme_widget_message_sticker")
        ]
        title_node = soup.select_one(".tgme_channel_info_header_title")
        row.update(title=title_node.get_text(" ", strip=True) if title_node else row.get("title", slug),
                   checked_at=checked, final_url=response.url,
                   status="public_preview" if nodes else "preview_no_messages", messages_checked=min(limit, len(nodes)))
        collected = []
        for node in nodes[-limit:]:
            raw_id = node.get("data-post", "")
            if not raw_id:
                continue
            ident = "tgpost-" + re.sub(r"[^a-zA-Z0-9_-]", "-", raw_id)
            text_node = node.select_one(".tgme_widget_message_text")
            text = text_node.get_text(" ", strip=True) if text_node else ""
            time_node = node.select_one("time[datetime]")
            grouped = node.get("data-album") or node.get("data-post", "")
            photos = []
            media = []
            for i, element in enumerate(node.select(".tgme_widget_message_photo_wrap, .tgme_widget_message_video_thumb")):
                style = element.get("style", "")
                match = re.search(r"background-image:\s*url\(['\"]?(.*?)['\"]?\)", style)
                media_url = match.group(1) if match else None
                is_video = "tgme_widget_message_video_thumb" in element.get("class", []) or element.find_parent(class_="tgme_widget_message_video_player") is not None
                local = image_to_webp(media_url, media_dir, f"{ident}-{i}") if media_url and media_dir is not None else None
                if local and local not in photos:
                    photos.append(local)
                media.append({"type": "video_preview" if is_video else "photo", "url": media_url,
                              "local_path": local, "status": "saved" if local else (
                                  "preview_url_missing" if not media_url else
                                  "pending" if media_dir is None else "download_failed")})
            # Video widgets use a public poster preview; record attribution explicitly.
            posts = {"id": ident, "channel_id": row["id"], "url": "https://t.me/" + raw_id,
                     "text": text, "published_at": time_node.get("datetime") if time_node else None,
                     "participant_ids": row.get("participant_ids", []), "people_ids": [], "photos": photos,
                     "media": media,
                     "grouped_message_ids": [grouped],
                     "sources": [{"title": "Публичный просмотр канала Telegram", "url": url, "date": checked[:10]}],
                     "source_url": url, "checked_at": checked,
                     "media_status": ("preview_saved" if photos else
                                      "preview_download_failed" if media and media_dir is not None else
                                      "no_public_media_preview")}
            collected.append(posts)
        return row, collected
    except Exception as exc:
        row.update(checked_at=checked, status="fetch_error", error=f"{type(exc).__name__}: {exc}", messages_checked=0)
        return row, []


def parse_indices(value: str, count: int) -> list[int]:
    result = set()
    for part in value.split(","):
        if ":" in part:
            start, end = map(int, part.split(":", 1)); result.update(range(start, end))
        elif part.strip():
            result.add(int(part))
    if any(i < 0 or i >= count for i in result):
        raise ValueError(f"indices must be in 0..{count-1}")
    return sorted(result)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--indices", required=True, help="comma list or zero-based half-open ranges, e.g. 0:47")
    ap.add_argument("--output", required=True, help="output JSON path relative to portal/")
    args = ap.parse_args()
    channels = json.loads((ROOT / "data/portal/channels.json").read_text(encoding="utf-8-sig"))
    chosen = [channels[i] for i in parse_indices(args.indices, len(channels))]
    checked = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    media_dir = ROOT / "docs/media/tg"
    output_channels, output_posts = [], []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, channel, checked, media_dir) for channel in chosen]
        for future in as_completed(futures):
            result, posts = future.result()
            output_channels.append(result); output_posts.extend(posts)
    order = {c["id"]: i for i, c in enumerate(chosen)}
    output_channels.sort(key=lambda c: order[c["id"]])
    output_posts.sort(key=lambda p: (order.get(p["channel_id"], 999), p.get("published_at") or ""), reverse=False)
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"channels": output_channels, "posts": output_posts}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"channels": len(output_channels), "posts": len(output_posts), "errors": sum(c["status"] == "fetch_error" for c in output_channels), "output": str(output), "media_dir": str(media_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
