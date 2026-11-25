"""Fetch official 2023–2026 exhibitor lists and detail cards into a resumable cache."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import json
from pathlib import Path
import re
from threading import local
import time
from urllib.parse import parse_qs, urlsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = {
    2023: ("ac7d68d7-c129-11eb-80cc-a0d3c1fab97f", 1064),
    2024: ("348532cd-e716-11ec-80cd-a0d3c1fab97f", 929),
    2025: ("de590dc1-417d-11ee-80ce-a0d3c1fab97f", 742),
    2026: ("f33d045c-98f8-11ef-80ce-a0d3c1fab97f", 478),
}
HOST = "https://icatalog.expocentr.ru/ru/exhibitions/"
CACHE = ROOT / "data/raw/archive_catalogs"
UA = "Mozilla/5.0 (compatible; FurnitureExpoCatalog/1.0)"
THREAD = local()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def get(url, card=False):
    if not hasattr(THREAD, "session"):
        THREAD.session = requests.Session()
        THREAD.session.headers["User-Agent"] = UA
    for attempt in range(3):
        try:
            THREAD.session.trust_env = attempt != 1
            response = THREAD.session.get(url, timeout=(6, 16))
            response.raise_for_status()
            content = response.content
            if card:
                section = re.search(rb'<dl\b[^>]*dl-horizontal[^>]*>.*?</dl>', content, re.S | re.I)
                if not section:
                    raise ValueError('company contact section missing')
                content = section.group()
            return BeautifulSoup(content, "html.parser", from_encoding=response.encoding or "utf-8")
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(0.7 * (attempt + 1))


def listings(year):
    key, expected = ARCHIVES[year]
    url = HOST + key + "/list"
    cache_file = CACHE / f"{year}-list.json"
    if cache_file.exists():
        return read(cache_file)
    html = get(url)
    companies = {}
    for anchor in html.select("tr a[href*='/exhibitors/']"):
        path = urlsplit(anchor["href"])
        found = re.fullmatch(rf"/ru/exhibitions/{key}/exhibitors/(\d+)", path.path)
        if not found:
            continue
        row = anchor.find_parent("tr")
        columns = [cell.get_text(" ", strip=True) for cell in row.find_all("td", recursive=False)]
        stand = parse_qs(path.query).get("stand", [""])[0].strip()
        ident = found[1]
        company = companies.setdefault(ident, dict(year=year, ident=ident, name=anchor.get_text(" ", strip=True),
            source=HOST + key + "/exhibitors/" + ident, list_url=url,
            list_fields=columns, stands=[]))
        if stand and stand not in company["stands"]:
            company["stands"].append(stand)
    if len(companies) != expected:
        raise ValueError(f"{year}: parsed {len(companies)}, expected {expected} from official catalog")
    result = list(companies.values())
    save(cache_file, result)
    return result


def contact_detail(row):
    path = CACHE / str(row["year"]) / (row["ident"] + ".json")
    if path.exists():
        return True
    try:
        dl = get(row["source"], card=True).find("dl")
        if not dl:
            raise ValueError("company contact section missing")
        fields = {}
        for dt in dl.find_all("dt", recursive=False):
            dd = dt.find_next_sibling("dd")
            if dd:
                label = dt.get_text(" ", strip=True).rstrip(":").strip()
                fields[label] = dict(text=dd.get_text(" ", strip=True),
                                     urls=[a["href"].strip() for a in dd.select("a[href]")])
        media_links = sorted({a["href"].strip() for a in dl.select("a[href]")
                              if "t.me/" in a["href"].lower() or "telegram.me/" in a["href"].lower()})
        save(path, dict(fields=fields, telegram=media_links, checked_at=date.today().isoformat()))
        return True
    except (requests.RequestException, ValueError, AttributeError, OSError) as exc:
        save(path.with_suffix(".error.json"), dict(source=row["source"], error=str(exc)))
        return False


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--workers", type=int, default=10)
    args.add_argument("--year", action="append", type=int, choices=sorted(ARCHIVES))
    options = args.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(3) as pool:
        groups = list(pool.map(listings, options.year or ARCHIVES))
    # Alternate editions so each year's metadata becomes available during a single run.
    rows = [row for index in range(max(map(len, groups))) for group in groups for row in group[index:index + 1]]
    print("Official list entries:", len(rows), flush=True)
    for year in options.year or ARCHIVES:
        (CACHE / str(year)).mkdir(exist_ok=True)
    with ThreadPoolExecutor(options.workers) as pool:
        tasks = [pool.submit(contact_detail, row) for row in rows]
        ok = 0
        for index, task in enumerate(as_completed(tasks), 1):
            ok += task.result()
            if index % 100 == 0 or index == len(tasks):
                print(f"{index}/{len(tasks)} processed, {ok} with cards", flush=True)


if __name__ == "__main__":
    main()
