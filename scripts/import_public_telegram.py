"""Collect up to ten latest messages from public Telegram previews linked by exhibitors."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CHECKED = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def fetch(channel: dict) -> tuple[dict, list[dict]]:
    slug = channel["url"].rstrip("/").rsplit("/", 1)[-1]
    url = "https://t.me/s/" + slug
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MebelExpoPortal/1.0)"}, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        nodes = soup.select(".tgme_widget_message")
        title_node = soup.select_one(".tgme_channel_info_header_title")
        title = title_node.get_text(" ", strip=True) if title_node else channel.get("title", slug)
        channel["title"] = title
        channel["checked_at"] = CHECKED
        channel["final_url"] = response.url
        channel["status"] = "public_preview" if nodes else "preview_unavailable_or_no_public_posts"
        posts = []
        for node in nodes[-10:]:
            raw_id = node.get("data-post", "")
            if not raw_id:
                continue
            ident = "tgpost-" + re.sub(r"[^a-zA-Z0-9_-]", "-", raw_id)
            text_node = node.select_one(".tgme_widget_message_text")
            text = text_node.get_text(" ", strip=True) if text_node else ""
            time_node = node.select_one("time[datetime]")
            published = time_node.get("datetime") if time_node else None
            permalink = node.get("data-post")
            posts.append({"id": ident, "channel_id": channel["id"],
                          "url": "https://t.me/" + permalink,
                          "text": text, "published_at": published,
                          "participant_ids": channel.get("participant_ids", []),
                          "people_ids": [], "photos": [],
                          "sources": [{"title": "Публичный просмотр канала Telegram", "url": url, "date": CHECKED[:10]}],
                          "source_url": url, "checked_at": CHECKED})
        channel["messages_checked"] = len(posts)
        return channel, posts
    except Exception as exc:
        channel["checked_at"] = CHECKED
        channel["status"] = "fetch_error"
        channel["error"] = type(exc).__name__
        channel["messages_checked"] = 0
        return channel, []


def main() -> None:
    directory = ROOT / "data" / "portal"
    channels = json.loads((directory / "channels.json").read_text(encoding="utf-8"))
    posts: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, channel) for channel in channels]
        output = []
        for future in as_completed(futures):
            channel, messages = future.result()
            output.append(channel)
            posts.extend(messages)
    output.sort(key=lambda x: x["id"])
    posts.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    (directory / "channels.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (directory / "posts.json").write_text(json.dumps(posts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Checked {len(output)} linked channels; {sum(x['status']=='public_preview' for x in output)} show public previews; collected {len(posts)} posts")


if __name__ == "__main__":
    main()
