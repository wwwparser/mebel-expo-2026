"""Find exhibitor Telegram links on catalog-listed websites and snapshot public channels."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import ipaddress
from pathlib import Path
import re
import time
from urllib.parse import unquote, urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, SoupStrainer

from build_portal import safe_url
from collect_archive_catalogs import CACHE, ROOT, UA, read, save
from telegram_snapshot import fetch, slug_for

DATA = ROOT / "data/portal"
SITE_CACHE = CACHE / "sites"
TG_CACHE = CACHE / "telegram"
MEDIA_CACHE = CACHE / "telegram-media"
TG_LINK = re.compile(r'(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/(?:s/)?([A-Za-z][A-Za-z0-9_]{3,31})\b', re.I)
RESERVED = {'share', 'proxy', 'addstickers', 'addemoji', 'joinchat', 'login', 'iv',
            'resolve', 'setlanguage', 'boost', 'contact', 'confirmphone', 'username'}
CONTACT_PAGE = re.compile(r'(?:контакты|contact(?:s|[-_ ]us)?\b|about-us|о компании)', re.I)
HTML_CAP = 2_000_000


def site_name(url):
    hostname = urlsplit(url).hostname or ''
    return hostname.lower().removeprefix('www.').rstrip('.')


def website_urls(field):
    result = []
    for raw in field.get("urls", []) or re.split(r"[,;\s]+", field.get("text", "")):
        raw = raw.strip(' .,;')
        if not raw or '@' in raw or TG_LINK.search(raw):
            continue
        if not re.match(r'^https?://', raw, re.I):
            raw = 'https://' + raw
        if not safe_url(raw):
            continue
        parts = urlsplit(raw)
        host = site_name(raw)
        if not host or '.' not in host or host.endswith(('.local', '.localhost', '.example', '.invalid')):
            continue
        try:
            ipaddress.ip_address(host)
        except ValueError:
            result.append(parts._replace(fragment='').geturl())
    return list(dict.fromkeys(result))


def handles(value):
    return {match.lower() for match in TG_LINK.findall(unquote(value or ''))
            if match.lower() not in RESERVED and not match.lower().endswith('bot')}


def profile_handles(value):
    """A social navigation link points to a profile, not a quoted Telegram post."""
    value = unquote(value.strip())
    if value.startswith('//'):
        value = 'https:' + value
    if not safe_url(value):
        return set()
    parts = urlsplit(value)
    if site_name(value) not in {'t.me', 'telegram.me', 'telegram.dog'}:
        return set()
    if not re.fullmatch(r'/(?:s/)?[A-Za-z][A-Za-z0-9_]{3,31}/?', parts.path):
        return set()
    return handles(value)


def page(url, session):
    with session.get(url, timeout=(4, 7), stream=True) as response:
        response.raise_for_status()
        if site_name(response.url) != site_name(url) or 'html' not in response.headers.get('content-type', ''):
            raise ValueError("different domain or non-HTML response")
        blocks, size = [], 0
        for block in response.iter_content(65536):
            size += len(block)
            if size > HTML_CAP:
                raise ValueError("HTML size limit")
            blocks.append(block)
        html = BeautifulSoup(b''.join(blocks), "html.parser", parse_only=SoupStrainer(["title", "a"]))
        if html.title and re.search(r'домен (?:припаркован|прода[её]тся)|domain for sale|parking page',
                                    html.title.get_text(" ", strip=True), re.I):
            raise ValueError("parked domain")
        return response.url, html


def scan_site(url, review=False):
    key = hashlib.sha256(url.encode()).hexdigest()[:26]
    path = SITE_CACHE / f"{key}.json"
    if path.exists() and not review:
        return read(path)
    found = {}
    result = dict(site=url, found=found, status="unavailable")
    try:
        with requests.Session() as session:
            session.headers["User-Agent"] = UA
            final, soup = page(url, session)
            result["status"] = "checked"
            candidates = []
            for tag in soup.select("a[href]"):
                href = tag["href"].strip()
                for handle in profile_handles(href):
                    found[handle] = final
                dest = urljoin(final, href)
                if (safe_url(dest) and site_name(dest) == site_name(final)
                        and CONTACT_PAGE.search(tag.get_text(" ", strip=True) + ' ' + urlsplit(dest).path)):
                    candidates.append(dest)
            if not found:
                for dest in list(dict.fromkeys(candidates))[:1]:
                    try:
                        actual, extra = page(dest, session)
                        for tag in extra.select("a[href]"):
                            for handle in profile_handles(tag["href"]):
                                found[handle] = actual
                    except (requests.RequestException, ValueError):
                        pass
    except (requests.RequestException, ValueError):
        pass
    save(path, result)
    return result


def get_sites():
    known = {site_name(s) for c in read(DATA / 'channels.json') for s in c.get('source_urls', [])
             if safe_url(s)}
    sites = {}
    for path in sorted(CACHE.glob('202[3456]/*.json')):
        if path.name.endswith('.error.json'):
            continue
        detail = read(path)
        for url in website_urls(detail.get('fields', {}).get('Сайт', {})):
            domain = site_name(url)
            if domain not in known and domain not in {'t.me', 'vk.com', 'instagram.com', 'facebook.com', 'ozon.ru', 'avito.ru'}:
                sites.setdefault(domain, url)
    return sites.values()


def known_factory_links():
    """Reuse directory research when its public proof identifies the same site."""
    domains = set()
    for path in CACHE.glob('202[3456]/*.json'):
        if not path.name.endswith('.error.json'):
            fields = read(path)['fields']
            domains.update(site_name(u) for u in website_urls(fields.get('Сайт', {})))
    for row in read(DATA / 'factory_channels.json'):
        site, evidence = row.get('website', ''), row.get('source_url', '')
        if not safe_url(site) or not safe_url(evidence) or site_name(site) not in domains:
            continue
        if site_name(evidence) == site_name(site) or (
                site_name(evidence) == '2gis.ru' and 'Домен компании упоминается в канале' in row.get('evidence', '')):
            yield site_name(site), row['handle'].casefold(), evidence


def poll_sites(workers, until):
    SITE_CACHE.mkdir(parents=True, exist_ok=True)
    seen = set()
    with ThreadPoolExecutor(workers) as pool:
        deadline = time.monotonic() + until
        while True:
            batch = [url for url in get_sites() if url not in seen]
            seen.update(batch)
            done, found = 0, 0
            for job in as_completed([pool.submit(scan_site, url) for url in batch]):
                record = job.result()
                done += 1
                found += bool(record['found'])
                if done % 100 == 0 or done == len(batch):
                    print(f"Sites this batch: {done}/{len(batch)}, Telegram links on {found}", flush=True)
            if time.monotonic() >= deadline:
                break
            time.sleep(5)


def review_sites(workers):
    candidates = [r['site'] for path in SITE_CACHE.glob('*.json') if (r := read(path))['found']]
    with ThreadPoolExecutor(workers) as pool:
        records = list(pool.map(lambda url: scan_site(url, review=True), candidates))
    print('Direct profile links on', sum(bool(r['found']) for r in records), 'of', len(candidates), 'reviewed sites', flush=True)


def snapshot_channel(handle, item, checked):
    path = TG_CACHE / (handle + '.json')
    if path.exists() and read(path)['channel']['status'] != 'fetch_error':
        return read(path)
    channel = dict(id=item.get('id', 'archive-tg-' + handle), url='https://t.me/' + handle,
                   preview_url='https://t.me/s/' + handle, title=item['title'])
    metadata, posts = fetch(channel, checked, MEDIA_CACHE)
    # No public message previews is distinct from a confirmed broadcast channel.
    if metadata['status'] == 'preview_no_messages':
        try:
            response = requests.get(channel['url'], timeout=(4, 8), headers={'User-Agent': UA})
            response.raise_for_status()
            preview = BeautifulSoup(response.content, 'html.parser')
            node = preview.select_one('.tgme_page_extra')
            if node and re.search(r'\bsubscribers?\b|подписчик', node.get_text(' ', strip=True), re.I):
                metadata['status'] = 'channel_no_public_posts'
        except requests.RequestException:
            pass
    result = dict(channel=metadata, posts=posts)
    save(path, result)
    return result


def snapshots(workers):
    TG_CACHE.mkdir(parents=True, exist_ok=True)
    known = {slug_for(c).casefold(): c for c in read(DATA/'channels.json')}
    candidates = {}
    for path in SITE_CACHE.glob('*.json'):
        row = read(path)
        for handle in row['found']:
            candidates.setdefault(handle, dict(title='@' + handle))
    for path in CACHE.glob('202[3456]/*.json'):
        if path.name.endswith('.error.json'):
            continue
        row = read(path)
        for url in row['telegram']:
            for handle in handles(url):
                candidates.setdefault(handle, dict(title='@' + handle))
        for field in row['fields'].values():
            for handle in handles(field['text']):
                candidates.setdefault(handle, dict(title='@' + handle))
    for _, handle, _ in known_factory_links():
        candidates.setdefault(handle, dict(title='@' + handle))
    for handle, old in known.items():
        if old['status'] == 'public_preview':
            candidates.pop(handle, None)
        elif handle and re.fullmatch(r'[a-z][a-z0-9_]{3,31}', handle) and not handle.endswith('bot'):
            candidates[handle] = dict(title=old['title'], id=old['id'])
    checked = datetime.now(ZoneInfo('Europe/Moscow')).isoformat(timespec='seconds')
    with ThreadPoolExecutor(workers) as pool:
        done, counts = 0, {}
        for future in as_completed([pool.submit(snapshot_channel, key, row, checked) for key, row in candidates.items()]):
            result = future.result()
            status = result['channel']['status']
            counts[status] = counts.get(status, 0) + 1
            done += 1
            if done % 25 == 0 or done == len(candidates):
                print(f"Telegram checked: {done}/{len(candidates)}", counts, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('sites', 'review-sites', 'telegram'))
    parser.add_argument('--workers', type=int, default=12)
    parser.add_argument('--poll', type=int, default=0, help="Minimum time in seconds to watch for new catalog cards")
    args = parser.parse_args()
    if args.mode == 'sites':
        poll_sites(args.workers, args.poll)
    elif args.mode == 'review-sites':
        review_sites(args.workers)
    else:
        snapshots(args.workers)
