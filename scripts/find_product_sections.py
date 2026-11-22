"""Identify explicit new-product sections on websites linked in the exhibitor catalogue."""
import concurrent.futures
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/portal/participants.json"
REPORT = ROOT / "data/raw/product-sections.jsonl"
TERMS = re.compile(r"новинк|новые коллекции|new arrivals|new products", re.I)


def sections(website):
    result = {"website": website, "sections": []}
    try:
        with requests.get(website, timeout=(5, 8), stream=True, headers={"User-Agent": "Mozilla/5.0 (compatible; ExpoCatalogue/1.0)"}) as response:
            response.raise_for_status()
            if "html" not in response.headers.get("Content-Type", "").lower():
                result["status"] = "not_html"
                return result
            source = bytearray()
            for chunk in response.iter_content(32768):
                source.extend(chunk)
                if len(source) >= 1_500_000:
                    break
            page = BeautifulSoup(bytes(source), "html.parser")
            site = urlsplit(response.url).hostname
            for a in page.select("a[href]"):
                title = a.get_text(" ", strip=True)
                if len(title) > 150 or not TERMS.search(title):
                    continue
                href = urljoin(response.url, a["href"]).split("#")[0]
                item = {"title": title, "url": href}
                if urlsplit(href).hostname == site and item not in result["sections"]:
                    result["sections"].append(item)
            result["status"] = "checked"
    except requests.RequestException as e:
        result["status"] = type(e).__name__
    return result


def main():
    companies = json.loads(CATALOG.read_text(encoding="utf-8"))
    sites = {link["url"] for company in companies for link in company.get("links", []) if "путеводител" in link.get("label", "").lower() and link["url"].startswith(("http:", "https:"))}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(line)["website"] for line in REPORT.read_text(encoding="utf-8").splitlines()} if REPORT.exists() else set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool, REPORT.open("a", encoding="utf-8") as out:
        for job in concurrent.futures.as_completed([pool.submit(sections, site) for site in sorted(sites-done)]):
            out.write(json.dumps(job.result(), ensure_ascii=False)+"\n")
            out.flush()
    print(f"Surveyed {len(sites)} linked websites")


if __name__ == "__main__":
    main()
