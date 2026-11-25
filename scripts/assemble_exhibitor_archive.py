"""Merge official exhibitor records across editions and publish proven Telegram links."""
from collections import Counter, defaultdict
from datetime import date
import hashlib
import re
from shutil import copyfile
from unicodedata import normalize

from build_portal import excerpt, safe_url
from collect_archive_catalogs import ARCHIVES, CACHE, HOST, ROOT, read, save
from collect_archive_telegram import MEDIA_CACHE, SITE_CACHE, TG_CACHE, handles, known_factory_links, site_name, website_urls
from telegram_snapshot import slug_for

DATA = ROOT / "data/portal"
COUNTRIES = {"российская федерация": "Россия", "россия": "Россия", "китай": "Китай",
             "гонконг, китай": "Гонконг, Китай", "кнр": "Китай",
             "беларусь": "Республика Беларусь", "казахстан": "Республика Казахстан",
             "узбекистан": "Республика Узбекистан", "турция": "Турция"}
CURRENT_ALIASES = {
    "FOSHAN JCL HARDWARE PRODUCTS CO. LTD": "FOSHAN JCL HARDWARE PRODUCT CO. LTD",
    "JIEYENG CITY LIANSHENG HARDWARE PRODUCTS CO. LTD": "JIEYANG CITY LIANSHENG HARDWARE PRODUCTS CO. LTD",
}
# A site can link to its hosting provider, an advertiser, or a partner's channel.
UNRELATED_TELEGRAM = {
    "username", "masterhost_news", "kastamonurussia", "mebelshikvkurse", "kochorbasmm",
}


def country_name(value):
    return COUNTRIES.get(value.casefold(), value.title())


def company_key(value):
    value = normalize("NFKC", value).casefold().replace("ё", "е")
    value = re.sub(r"\s*\(участник коллективной экспозиции[^)]*\)", "", value)
    value = re.sub(r"\b(?:ооо|ooo|ао|оао|зао|пао|ип|годо|llc|ltd|co|inc|limited|company|corp)\b", " ", value)
    return "".join(c for c in value if c.isalnum())


def add_contact(entry, field, values, source):
    for value in values:
        if value and all(contact["value"] != value["value"] for contact in entry.setdefault(field, [])):
            entry[field].append({**value, "year": entry["year"], "source": source})


def official_row(raw):
    path = CACHE / str(raw["year"]) / (raw["ident"] + ".json")
    detail = read(path) if path.exists() else {}
    fields = detail.get("fields", {})
    rows = raw["list_fields"]
    country = country_name(rows[1])
    entry = dict(id=f'{raw["year"]}-{raw["ident"]}', year=raw["year"], name=raw["name"],
                 country=country, stands=raw["stands"] or ([rows[3]] if rows[3] else []),
                 source=raw["source"], city=fields.get("Город", {}).get("text", ""),
                 card_loaded=bool(detail))
    add_contact(entry, "websites", [{"value": site_name(url), "url": url}
                for url in website_urls(fields.get("Сайт", {}))], entry["source"])
    emails = re.findall(r"[A-Za-z0-9._+%\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}",
                       fields.get("E-mail", {}).get("text", ""))
    add_contact(entry, "emails", [{"value": mail, "url": "mailto:" + mail} for mail in emails], entry["source"])
    phones = re.split(r"\s*[;,/]\s*", fields.get("Телефон", {}).get("text", ""))
    add_contact(entry, "phones", [
        {"value": phone, "url": "tel:" + ("+" if phone.startswith("+") else "") + re.sub(r"\D", "", phone)}
        for phone in phones if 7 <= len(re.sub(r"\D", "", phone)) <= 16
    ], entry["source"])
    explicit = set().union(*(handles(text) for text in detail.get("telegram", [])),
                           *(handles(field["text"]) for field in fields.values()))
    entry["telegram_candidates"] = {handle: entry["source"] for handle in explicit}
    return entry


def merge_current(entry, current):
    entry["profile_id"] = current["id"]
    for source in current.get("contacts") or current.get("links", []):
        url = source.get("url", "")
        label = source["label"].casefold()
        evidence = source.get("source_url") or entry["source"]
        if not safe_url(url, contact=True):
            continue
        contact = {"value": source["value"], "url": url}
        if label.startswith("сайт"):
            add_contact(entry, "websites", [{"value": site_name(url), "url": url}], evidence)
        elif url.startswith("tel:"):
            add_contact(entry, "phones", [contact], evidence)
        elif url.startswith("mailto:"):
            add_contact(entry, "emails", [contact], evidence)
        else:
            for handle in handles(url):
                entry["telegram_candidates"].setdefault(handle, evidence)


def combine_companies(all_rows):
    groups = defaultdict(list)
    for entry in all_rows:
        groups[(entry["country"], company_key(entry["name"]))].append(entry)
    result = []
    for (country, key), entries in groups.items():
        counts = Counter(e["year"] for e in entries)
        for members in ([entries] if key and max(counts.values()) == 1 else [[e] for e in entries]):
            members.sort(key=lambda e: e["year"], reverse=True)
            latest = members[0]
            digest = hashlib.sha256(f"{country}:{key}:{latest['id']}".encode()).hexdigest()[:16]
            company = dict(id="archive-" + digest, name=latest["name"], country=country,
                           years=[e["year"] for e in members], city=next(
                               (e["city"] for e in members if e["city"]), ""),
                           profiles=[{k: e[k] for k in ("year", "source", "stands", "name", "card_loaded")}
                                     for e in members])
            if latest.get("profile_id"):
                company["profile_id"] = latest["profile_id"]
            for field in ("websites", "emails", "phones"):
                company[field] = list({
                    contact["url"].casefold().removeprefix("http://").removeprefix("https://").removeprefix("www.").rstrip("/"): contact
                    for e in reversed(members) for contact in e.get(field, [])
                }.values())
                company[field].sort(key=lambda c: -c["year"])
            candidates = {}
            for e in reversed(members):
                candidates.update(e["telegram_candidates"])
            company["telegram_candidates"] = candidates
            result.append(company)
    return sorted(result, key=lambda c: (c["name"].casefold(), c["country"], c["id"]))


def merge_reviewed_companies(companies, reviews):
    """Apply reviewed links between catalog names and retain every source and old anchor."""
    by_id = {company["id"]: company for company in companies}
    related = defaultdict(set)
    for review in reviews:
        left, right = review["ids"]
        if left == right or left not in by_id or right not in by_id:
            raise ValueError(f"Invalid duplicate review: {review}")
        if by_id[left]["country"] != by_id[right]["country"]:
            raise ValueError(f"Duplicate review links different countries: {review}")
        related[left].add(right)
        related[right].add(left)

    removed, visited = set(), set()
    for first in related:
        if first in visited:
            continue
        cluster = set()
        pending = [first]
        while pending:
            ident = pending.pop()
            if ident not in cluster:
                cluster.add(ident)
                pending.extend(related[ident] - cluster)
        members = sorted((by_id[ident] for ident in cluster),
                         key=lambda c: (not c.get("profile_id"), -c["years"][0], -len(c["years"]), c["id"]))
        primary = members[0]
        primary["aliases"] = sorted(cluster - {primary["id"]})
        primary["years"] = sorted({year for item in members for year in item["years"]}, reverse=True)
        primary["profiles"] = sorted((profile for item in members for profile in item["profiles"]),
                                     key=lambda p: (-p["year"], p["source"], p["name"]))
        profile_ids = list(dict.fromkeys(item["profile_id"] for item in members if item.get("profile_id")))
        if len(profile_ids) > 1:
            primary["profile_ids"] = profile_ids
        primary["city"] = next((item["city"] for item in members if item["city"]), "")
        for field in ("websites", "emails", "phones"):
            contacts = sorted((contact for item in members for contact in item[field]),
                              key=lambda c: -c["year"])
            distinct = {}
            for contact in contacts:
                key = contact["url"].casefold().removeprefix("http://").removeprefix("https://").removeprefix("www.").rstrip("/")
                distinct.setdefault(key, contact)
            primary[field] = list(distinct.values())
        for item in members[1:]:
            for handle, source in item["telegram_candidates"].items():
                primary["telegram_candidates"].setdefault(handle, source)
        visited.update(cluster)
        removed.update(primary["aliases"])
    return [company for company in companies if company["id"] not in removed]


def main():
    current_rows = read(DATA / "participants.json")
    current_by_name = defaultdict(list)
    for row in current_rows:
        key = (country_name(row["country"]), company_key(CURRENT_ALIASES.get(row["name"], row["name"])))
        current_by_name[key].append(row)
    all_rows, coverage = [], []
    extra_current = []
    for year, (token, expected) in ARCHIVES.items():
        raw = read(CACHE / f"{year}-list.json")
        entries = [official_row(row) for row in raw]
        if len(entries) != expected:
            raise ValueError(f"Incomplete official list for {year}")
        if year == 2026:
            used = set()
            for entry in entries:
                matches = current_by_name[(entry["country"], company_key(entry["name"]))]
                if len(matches) != 1:
                    matches = [r for r in matches if set(r["stands"]) & set(entry["stands"])]
                if len(matches) == 1 and matches[0]["id"] not in used:
                    merge_current(entry, matches[0])
                    used.add(matches[0]["id"])
            for row in current_rows:
                if row["id"] in used:
                    continue
                source = row["sources"][0]["url"]
                supplemental = dict(id='2026-' + row['id'], year=2026, name=row['name'],
                                    country=country_name(row['country']), stands=row['stands'],
                                    source=source, city='', card_loaded=False, telegram_candidates={})
                merge_current(supplemental, row)
                extra_current.append(supplemental)
            print(f"Linked {len(used)} current local profiles", flush=True)
        all_rows.extend(entries)
        coverage.append(dict(year=year, entries=expected, detail_cards=sum(e["card_loaded"] for e in entries),
                             source=HOST + token + "/list", russia=sum(e["country"] == "Россия" for e in entries),
                             china=sum(e["country"] in ("Китай", "Гонконг, Китай") for e in entries)))
    companies = combine_companies(all_rows + extra_current)
    companies = merge_reviewed_companies(companies, read(DATA / "exhibitor_merges.json"))
    website_proofs = defaultdict(dict)
    successful_sites = set()
    for path in SITE_CACHE.glob("*.json"):
        row = read(path)
        domain = site_name(row["site"])
        website_proofs[domain].update(row["found"])
        if row["status"] == "checked":
            successful_sites.add(domain)
    sites_attempted = len(website_proofs)
    for domain, handle, source in known_factory_links():
        website_proofs.setdefault(domain, {}).setdefault(handle, source)
    domain_companies = defaultdict(list)
    for company in companies:
        for domain in {site_name(w["url"]) for w in company["websites"]}:
            domain_companies[domain].append(company)
    original_channels = read(DATA / "channels.json")
    original_by_handle = {slug_for(channel).casefold(): channel for channel in original_channels}
    original_by_company = defaultdict(list)
    for handle, channel in original_by_handle.items():
        for pid in channel.get("participant_ids", []):
            original_by_company[pid].append(handle)
        for source in channel.get("source_urls", []):
            if safe_url(source):
                website_proofs.setdefault(site_name(source), {}).setdefault(handle, source)
    new_channels = {path.stem: read(path) for path in TG_CACHE.glob("*.json")}
    old_post_ids = {post["id"] for post in read(DATA / "posts.json")}
    channel_catalog, posts = {}, []
    for company in companies:
        candidates = company.pop("telegram_candidates")
        for website in company["websites"]:
            domain = site_name(website["url"])
            # Shared catalog or holding domains do not identify one exhibitor's channel.
            if len(domain_companies[domain]) == 1:
                for handle, source in website_proofs.get(domain, {}).items():
                    candidates.setdefault(handle, source)
        profile_ids = company.get("profile_ids", [company.get("profile_id")])
        known_handles = {handle for pid in profile_ids for handle in original_by_company[pid]}
        for handle in sorted(known_handles):
            known = original_by_handle[handle]
            source = next((s for s in known.get("source_urls", []) if safe_url(s)), "")
            if source:
                candidates.setdefault(handle, source)
        company["telegram"] = []
        for handle, source in sorted(candidates.items()):
            if handle in UNRELATED_TELEGRAM and handle not in known_handles:
                continue
            original = original_by_handle.get(handle)
            record = new_channels.get(handle, {})
            refresh = record.get("channel", {})
            channel = original if original and original['status'] == 'public_preview' else refresh
            if channel.get("status") not in ("public_preview", "channel_no_public_posts") or not safe_url(source):
                continue
            linked = dict(handle=handle, title=channel["title"], url=channel["url"], source=source)
            company["telegram"].append(linked)
            if handle not in channel_catalog:
                channel_catalog[handle] = dict(id=channel["id"], handle=handle, title=channel["title"], url=channel["url"],
                    status=channel["status"], checked_at=channel["checked_at"], companies=[])
                if channel is refresh:
                    posts.extend({**post, "text": excerpt(post["text"], 45)}
                                 for post in record["posts"] if post["id"] not in old_post_ids)
            channel_catalog[handle]["companies"].append(dict(id=company["id"], source=source))
    channel_list = sorted(channel_catalog.values(), key=lambda c: c["title"].casefold())
    for name in {img for post in posts for img in post["photos"]}:
        if not re.fullmatch(r'media/tg/[a-f0-9]{24}\.webp', name):
            raise ValueError(f'Invalid Telegram media path: {name}')
        target = ROOT / "docs" / name
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            copyfile(MEDIA_CACHE / target.name, target)
    summary = dict(checked_at=date.today().isoformat(), editions=coverage, companies=len(companies),
                   supplemental_current=len(extra_current),
                   sites_attempted=sites_attempted, sites_checked=len(successful_sites),
                   companies_with_website=sum(bool(c["websites"]) for c in companies),
                   companies_with_email_or_phone=sum(bool(c["emails"] or c["phones"]) for c in companies),
                   channels=len(channel_list), new_channels=sum(c["handle"] not in original_by_handle for c in channel_list),
                   refreshed_channels=sum(c["handle"] in original_by_handle and
                       original_by_handle[c["handle"]]["status"] != "public_preview" for c in channel_list),
                   new_posts=len(posts))
    save(DATA / "exhibitor_archive.json", dict(summary=summary, companies=companies, channels=channel_list))
    save(DATA / "archive_posts.json", posts)
    print(summary)


if __name__ == "__main__":
    main()
