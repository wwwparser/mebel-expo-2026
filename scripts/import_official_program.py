"""Import the published MEBEL-2026 programme and its named speakers."""
from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.meb-expo.ru/ru/events/"
MONTH = {"ноября": "11"}


def person_id(name: str, role: str) -> str:
    digest = hashlib.sha1((name.casefold() + "\0" + role.casefold()).encode()).hexdigest()[:12]
    return "sp-" + digest


def main() -> None:
    response = requests.get(URL, headers={"User-Agent": "Mozilla/5.0 (compatible; MebelExpoPortal/1.0)"}, timeout=25)
    response.raise_for_status()
    response.encoding = "windows-1251"
    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.select("div.event-task[data-event-id]")
    if not cards:
        raise SystemExit("No official programme entries found; existing data was not changed.")

    people: OrderedDict[str, dict] = OrderedDict()
    events = []
    for card in cards:
        title = card.get("data-event-name", "").strip()
        date_text = card.get("data-eventdate", "")
        dm = re.search(r"(\d{1,2})\s+(\S+)", date_text)
        event_date = f"2026-{MONTH.get(dm.group(2), '11')}-{int(dm.group(1)):02d}" if dm else None
        time_text = card.select_one(".time")
        times = re.search(r"(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})", time_text.get_text(" ", strip=True)) if time_text else None
        venue_node = card.select_one(".hall")
        org_node = card.select_one(".org")
        event_id = card.get("data-event-id", "")
        modal = soup.find(id="m" + event_id)
        people_ids = []
        description = ""
        if modal:
            body = modal.select_one(".modal-body")
            if body:
                description = re.sub(r"\s+", " ", body.get_text(" ", strip=True))[:5000]
            for row in modal.select(".row.flex-row.align-items-center"):
                text = re.sub(r"\s+", " ", row.get_text(" ", strip=True))
                if "павильон" in text.casefold() or re.search(r"\bзал\s+\d", text.casefold()):
                    continue
                # Profile rows use “Surname Name, role”; keep the source wording intact.
                match = re.match(r"(.{2,100}?),\s*(.{2,350})$", text)
                if not match:
                    continue
                name, role = match.group(1).strip(" ,"), match.group(2).strip()
                if len(name.split()) < 2 or len(name) > 100:
                    continue
                pid = person_id(name, role)
                people.setdefault(pid, {
                    "id": pid,
                    "name": name,
                    "role": role,
                    "about": "",
                    "links": [],
                    "sources": [{"title": "Деловая программа МЕБЕЛЬ-2026", "url": URL}],
                })
                people_ids.append(pid)
            if body:
                for talk in body.select("li"):
                    text = re.sub(r"\s+", " ", talk.get_text(" ", strip=True))
                    match = re.search(r"Спикер:\s*(.{2,100}?),\s*(.{2,350}?)(?:\s+Спикер:|$)", text)
                    if not match:
                        continue
                    name, role = match.group(1).strip(" ,"), match.group(2).strip()
                    if len(name.split()) < 2:
                        continue
                    pid = person_id(name, role)
                    people.setdefault(pid, {
                        "id": pid,
                        "name": name,
                        "role": role,
                        "about": "",
                        "links": [],
                        "sources": [{"title": "Деловая программа МЕБЕЛЬ-2026", "url": URL}],
                    })
                    people_ids.append(pid)
        events.append({
            "id": "ev-" + event_id,
            "title": title,
            "date": event_date,
            "start": times.group(1) if times else None,
            "end": times.group(2) if times else None,
            "venue": venue_node.get_text(" ", strip=True) if venue_node else "",
            "description": description,
            "organizer": org_node.get_text(" ", strip=True) if org_node else "",
            "people_ids": list(dict.fromkeys(people_ids)),
            "participant_ids": [],
            "sources": [{"title": "Официальная деловая программа МЕБЕЛЬ-2026", "url": URL, "date": "2026-11-16",
                         "note": "Анонс будущего события, дата просмотра списка"}],
            "source_url": URL,
            "source_date": "2026-11-16",
            "status": "announced",
        })

    data = ROOT / "data" / "portal"
    data.mkdir(parents=True, exist_ok=True)
    (data / "program.json").write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (data / "people.json").write_text(json.dumps(list(people.values()), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raw = ROOT / "data" / "raw" / "official_events.html"
    raw.write_bytes(response.content)
    print(f"Imported {len(events)} programme entries and {len(people)} speaker profiles from {URL}")


if __name__ == "__main__":
    main()
