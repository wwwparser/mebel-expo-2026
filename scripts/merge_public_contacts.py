"""Attach public contact details from printed exhibitor websites to catalogue entries."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "contacts" / "contacts.jsonl"
KINDS = (("emails", "Email", "mailto:"), ("phones", "Телефон", "tel:"),
         ("telegram", "Telegram", ""), ("max", "MAX", ""),
         ("whatsapp", "WhatsApp", ""), ("vk", "ВКонтакте", ""),
         ("instagram", "Instagram", ""), ("facebook", "Facebook", ""),
         ("ok", "Одноклассники", ""), ("linkedin", "LinkedIn", ""),
         ("youtube", "YouTube", ""), ("wechat", "WeChat", ""),
         ("line", "LINE", ""), ("xing", "Xing", ""), ("x", "X", ""))


def host(value: str) -> str:
    try:
        raw = urlsplit(value if "://" in value else "https://" + value).hostname or ""
        return raw.encode("idna").decode("ascii").lower().removeprefix("www.")
    except Exception:
        return ""


def main() -> None:
    records = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_host = {host(x.get("home", "")): x for x in records if host(x.get("home", ""))}
    participants = json.loads((ROOT / "data/portal/participants.json").read_text(encoding="utf-8"))
    channels: dict[str, dict] = {}
    contact_count = channel_count = 0
    for participant in participants:
        for website in participant.get("links", []):
            result = by_host.get(host(website.get("url", "")))
            if not result:
                continue
            for key, label, prefix in KINDS:
                for value in result.get(key, []):
                    value = (value or "").strip()
                    if not value:
                        continue
                    if key == "telegram":
                        parsed = urlsplit(value)
                        path = parsed.path.strip("/").split("/")
                        slug = path[-1] if path else ""
                        if not slug or slug in {"share", "addstickers", "joinchat"} or slug.startswith("+"):
                            continue
                        cid = "tg-" + hashlib.sha1(slug.casefold().encode()).hexdigest()[:12]
                        channel = channels.setdefault(cid, {"id": cid, "title": slug, "url": "https://t.me/" + slug,
                            "preview_url": "https://t.me/s/" + slug, "participant_ids": [],
                            "source_urls": [], "status": "pending"})
                        if participant["id"] not in channel["participant_ids"]:
                            channel["participant_ids"].append(participant["id"])
                        if website["url"] not in channel["source_urls"]:
                            channel["source_urls"].append(website["url"])
                        channel_count += 1
                    url = value if prefix == "" else prefix + value
                    if key == "telegram":
                        url = "https://t.me/" + slug
                    if key == "max" and not value.startswith("http"):
                        continue
                    link = {"label": label, "value": value, "url": url,
                            "source_url": website["url"], "checked_at": "2026-11-16"}
                    if not any(existing.get("url") == url for existing in participant.get("links", [])):
                        participant.setdefault("links", []).append(link)
                        contact_count += 1
    data = ROOT / "data" / "portal"
    (data / "participants.json").write_text(json.dumps(participants, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (data / "channels.json").write_text(json.dumps(list(channels.values()), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Attached {contact_count} public contact links; confirmed {len(channels)} public Telegram channel links")


if __name__ == "__main__":
    main()
