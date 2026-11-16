"""Fetch the official exhibitor index and update the list-level MVP dataset."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.meb-expo.ru/ru/exhibition/exhibitors/"


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.in_table = 0
        self.rows: list[list[str]] | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.in_table += 1
            if self.in_table == 1:
                self.rows = []
        elif self.in_table == 1 and tag == "tr":
            self.row = []
        elif self.in_table == 1 and tag in {"td", "th"}:
            self.cell = []
        elif self.in_table == 1 and tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_table == 1 and tag in {"td", "th"} and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif self.in_table == 1 and tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.in_table:
            if self.in_table == 1 and self.rows is not None:
                self.tables.append(self.rows)
            self.in_table -= 1


def main() -> None:
    request = urllib.request.Request(
        URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; MebelExpoCatalog/1.0)"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = response.read()
        charset = "windows-1251"
    html = payload.decode(charset, errors="replace")

    parser = TableParser()
    parser.feed(html)
    catalog = None
    for table in parser.tables:
        if table and [x.casefold() for x in table[0]] == ["название фирмы", "страна", "стенд"]:
            catalog = table
            break
    if catalog is None:
        raise SystemExit("Не найдена ожидаемая таблица (Название фирмы / Страна / Стенд); данные не изменены.")

    rows = [r for r in catalog[1:] if len(r) == 3 and all(x.strip() for x in r)]
    if not rows:
        raise SystemExit("Каталог не содержит строк участников; данные не изменены.")
    checked_at = datetime.now(ZoneInfo("Europe/Moscow")).isoformat(timespec="seconds")
    participants = []
    for name, country, stand in rows:
        key = "\0".join((name.casefold(), country.casefold(), stand.casefold()))
        participant_id = "p-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        participants.append({
            "id": participant_id,
            "name": name,
            "country": country,
            "stands": [stand],
            "checked_at": checked_at,
            "sources": [{
                "title": "Официальный алфавитный список участников «МЕБЕЛЬ-2026»",
                "url": URL,
                "date": "2026-11-13",
                "note": "Строка списка: название фирмы, страна и стенд. Подробная карточка и контакты этим срезом не подтверждены.",
            }],
        })
    ids = [p["id"] for p in participants]
    if len(set(ids)) != len(ids):
        raise SystemExit("Найдены повторяющиеся идентификаторы; данные не изменены.")

    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    stamp = checked_at[:10]
    (raw_dir / f"official_catalog_{stamp}.html").write_bytes(payload)
    portal_data = ROOT / "data" / "portal"
    portal_data.mkdir(parents=True, exist_ok=True)
    (portal_data / "participants.json").write_text(
        json.dumps(participants, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "section_map.json").write_text(json.dumps([{
        "label": "Участники «МЕБЕЛЬ-2026»",
        "found_on": URL,
        "url": URL,
        "final_url": URL,
        "section_type": "exhibitor_catalog_index",
        "edition": "МЕБЕЛЬ-2026",
        "checked_at": checked_at,
    }], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "coverage.json").write_text(json.dumps({
        "edition": "МЕБЕЛЬ-2026",
        "source_snapshot_date": "2026-11-13",
        "retrieved_at": checked_at,
        "source_url": URL,
        "source_html": f"data/raw/official_catalog_{stamp}.html",
        "catalog_rows_found": len(rows),
        "participant_rows_imported": len(participants),
        "fields_imported": ["name", "country", "stand"],
        "details_checked": 0,
        "telegram_channels_checked": 0,
        "limitations": [
            "Это списоковый срез, а не расширенные карточки участников.",
            "Контакты и Telegram-каналы не собирались и не подтверждались.",
            "Программа, новости и дополнительные разделы не входят в MVP.",
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {len(participants)} listed exhibitors from {URL}")
    print(f"Retrieved {checked_at}; official page labels its data 2026-11-13")


if __name__ == "__main__":
    main()
