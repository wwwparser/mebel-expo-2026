"""Add a sourced description snippet from each linked, reachable company homepage."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def domain(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").encode("idna").decode("ascii").lower().removeprefix("www.")
    except Exception:
        return ""


def main() -> None:
    data = ROOT / "data" / "portal"
    participants = json.loads((data / "participants.json").read_text(encoding="utf-8"))
    scraped = [json.loads(x) for x in (ROOT / "data/raw/contacts/contacts.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    by_host = {domain(x.get("home", "")): x for x in scraped if domain(x.get("home", ""))}
    count = 0
    for participant in participants:
        if participant.get("about"):
            continue
        site = next((x for x in participant.get("links", []) if x.get("label") == "Сайт из официального путеводителя"), None)
        record = by_host.get(domain(site.get("url", ""))) if site else None
        description = (record or {}).get("meta_desc", "").strip()
        if not description or not (record or {}).get("reachable"):
            continue
        participant["about"] = description[:900]
        source_url = (record or {}).get("home") or site["url"]
        participant.setdefault("sources", []).append({"title": "Сайт компании, связанный с участником в официальном путеводителе",
            "url": source_url, "date": "2026-11-16", "note": "Краткое описание взято из метатега страницы компании."})
        count += 1
    (data / "participants.json").write_text(json.dumps(participants, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Added sourced homepage descriptions to {count} participant profiles")


if __name__ == "__main__":
    main()
