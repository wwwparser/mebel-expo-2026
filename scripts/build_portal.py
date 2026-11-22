"""Offline, deterministic exhibition portal builder. See PROJECT.md and CONTRACT.md."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
MODULES = {
    'participants': ('catalog.html', 'Участники'),
    'program': ('program.html', 'Программа'),
    'people': ('people.html', 'Спикеры'),
    'posts': ('feed.html', 'Публикации'),
    'giveaways': ('giveaways.html', 'Розыгрыши'),
    'services': ('services.html', 'Услуги'),
    'videos': ('videos.html', 'Видео'),
    'novelties': ('novelties.html', 'Новинки'),
    'articles': ('articles.html', 'Материалы'),
    'map': ('map.html', 'Схема'),
}


def digest(value):
    return hashlib.sha256(value.encode('utf-8') if isinstance(value, str) else value).hexdigest()


def safe_url(value, contact=False):
    """No executable, protocol-relative, credential-bearing or malformed URLs."""
    if not isinstance(value, str) or not value or re.search(r'[\x00-\x20\x7f\\<>"\']', value):
        return ''
    try:
        u = urlsplit(value)
        if u.scheme in ('https', 'http') and u.hostname and not u.username and not u.password:
            return value
        if contact and u.scheme in ('tel', 'mailto') and u.path:
            return value
    except ValueError:
        pass
    return ''


def local_path(value):
    """A literal relative POSIX path; do not decode URL escapes into filesystem paths."""
    if not isinstance(value, str) or not value or re.search(r'[\\\x00-\x20\x7f:%?#]', value):
        return None
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or value.startswith('//'):
        return None
    return p


def inside(root, value):
    p = local_path(value)
    if p is None:
        raise ValueError(f'Unsafe relative path: {value!r}')
    target = (root / str(p)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f'Path escapes its root: {value!r}')
    return target


def output_file(root, value):
    """Generated paths cannot follow a symlink into media or someone else's files."""
    target = inside(root, value)
    current = root
    for part in local_path(value).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f'Generated output cannot follow symlinks: {value}')
    if target.is_relative_to(root / 'media'):
        raise ValueError('Media is read-only')
    return target


def asset(value, output):
    if safe_url(value):
        return value
    if not value:
        return ''
    p = local_path(value)
    if p and p.parts[0] == 'media' and inside(output, value).is_file():
        return quote(value, safe='/.-_')
    return ''


def read_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def date_value(value, tz):
    """Require complete ISO dates. Never infer a year from text or build time."""
    if not value:
        return None
    if not isinstance(value, str) or not re.match(r'^\d{4}-\d{2}-\d{2}(?:$|T)', value):
        raise ValueError(f'Expected complete ISO date, got {value!r}')
    if 'T' not in value:
        return date.fromisoformat(value)
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return result.replace(tzinfo=tz) if result.tzinfo is None else result.astimezone(tz)


def date_text(value, tz):
    result = date_value(value, tz)
    if result is None:
        return ''
    return result.strftime('%d.%m.%Y %H:%M' if isinstance(result, datetime) else '%d.%m.%Y')


def excerpt(value, words=25):
    tokens = re.sub(r'\s+', ' ', str(value or '')).strip().split()
    return ' '.join(tokens[:words]) + ('…' if len(tokens) > words else '')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError(f'ID must contain ASCII letters, digits, _ or -: {value!r}')
    return value


def analysis_hash(config, post):
    """Same contract as the skill's optional analysis_queue.py; no runtime dependency."""
    keys = ('name', 'edition', 'start_date', 'end_date', 'timezone', 'catalog_url')
    payload = {'task_version': 'expo-post-v3', 'context': {k: config.get(k) for k in keys}, 'post': {
        'post_id': str(post['id']), 'text': post.get('text', ''),
        'date': post.get('date') or post.get('published_at'),
        'url': post.get('url') or post.get('permalink'), 'edited_at': post.get('edited_at'),
        'participant_ids': post.get('participant_ids', []), 'people_ids': post.get('people_ids', []),
        'media': post.get('grouped_message_ids', []),
        'photos': post.get('photos', post.get('remote_photos', [])),
        'media_revision': post.get('media_revision')}}
    return digest(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False))


def sources(item):
    result = []
    for source in item.get('sources', []):
        if not isinstance(source, dict) or not safe_url(source.get('url')) or not source.get('title'):
            raise ValueError(f'Invalid source on {item.get("id", "record")}')
        result.append(source)
    if not result:
        raise ValueError(f'Missing source bibliography on {item.get("id", "record")}')
    return result


class Fragment(HTMLParser):
    """Reject executable markup. Authored text is never rewritten or generated."""
    TAGS = set('p h2 h3 h4 ul ol li strong em b i a img figure figcaption blockquote table thead tbody tr th td caption div span br hr section details summary code pre'.split())
    ATTRS = {'id', 'class', 'href', 'src', 'alt', 'title', 'loading', 'colspan', 'rowspan'}

    def __init__(self, output):
        super().__init__(convert_charrefs=True)
        self.output = output

    def handle_starttag(self, tag, attrs):
        if tag not in self.TAGS:
            raise ValueError(f'Article HTML disallows <{tag}>')
        for key, value in attrs:
            if key not in self.ATTRS or value is None:
                raise ValueError(f'Article HTML disallows attribute {key}')
            if key in ('href', 'src'):
                local = local_path(value)
                if not (safe_url(value) or (key == 'href' and re.fullmatch(r'#[A-Za-z][\w-]*', value)) or
                        (local and local.parts[0] == 'media')):
                    raise ValueError(f'Unsafe article reference: {value!r}')
                if local and local.parts[0] == 'media' and not asset(value, self.output):
                    raise ValueError(f'Missing article media: {value}')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag not in self.TAGS:
            raise ValueError(f'Article HTML disallows </{tag}>')


def load_rows(root, name):
    rows = read_json(root / 'data/portal' / f'{name}.json', [])
    if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows):
        raise ValueError(f'{name}.json must be an array of objects')
    seen = set()
    for row in rows:
        if name == 'posts' and isinstance(row.get('id'), str) and re.fullmatch(r'[A-Za-z0-9_-]+(?:/[0-9]+)?', row['id']):
            pass  # Native channel/message IDs are data keys, never filesystem paths.
        else:
            row['id'] = identifier(row.get('id'))
        if row['id'] in seen:
            raise ValueError(f'Duplicate ID in {name}: {row["id"]}')
        seen.add(row['id'])
    return rows


def build(root=ROOT, output_override=None):
    root = Path(root).resolve()
    config = read_json(root / 'expo.json')
    if not isinstance(config, dict):
        raise ValueError('expo.json is required')
    for key in ('name', 'edition', 'place', 'timezone', 'checked_at'):
        if not config.get(key):
            raise ValueError(f'expo.json: {key} is required')
    tz = ZoneInfo(config['timezone'])
    date_value(config['checked_at'], tz)
    start, end = date_value(config.get('start_date'), tz), date_value(config.get('end_date'), tz)
    if not start or not end or type(start) is not date or type(end) is not date or end < start:
        raise ValueError('start_date/end_date must be complete ISO dates in ascending order')
    for key in ('base_url', 'official_url', 'catalog_url', 'scheme_url'):
        value = config.get(key, '')
        if value and not safe_url(value):
            raise ValueError(f'expo.json: unsafe {key}')
    if config.get('base_url') and (urlsplit(config['base_url']).query or urlsplit(config['base_url']).fragment):
        raise ValueError('base_url must have no query or fragment')
    base = config.get('base_url', '').rstrip('/') + '/' if config.get('base_url') else ''
    selected = config.get('modules', ['participants'])
    if not isinstance(selected, list) or set(selected) - MODULES.keys():
        raise ValueError('modules must be an array of supported module names')
    if 'participants' not in selected:
        raise ValueError('participants is a required module')
    feed_count = config.get('feed_count', 6)
    if type(feed_count) is not int or feed_count < 1:
        raise ValueError('feed_count must be a positive integer')
    out = Path(output_override).resolve() if output_override else inside(root, config.get('output_dir', 'docs'))
    protected = [root, root / 'data', root / 'scripts', root / 'portal_web']
    if any(out == p or out.is_relative_to(p) for p in protected[1:]) or out == root or root.is_relative_to(out) or 'media' in out.parts:
        raise ValueError('Output directory overlaps project source')

    rows = {name: load_rows(root, name) for name in MODULES if name != 'map'}
    if not rows['participants']:
        raise ValueError('data/portal/participants.json must contain at least one participant; no legacy fallback')
    active = {name for name in selected if name == 'participants' or (config.get('scheme_url') if name == 'map' else (rows[name] or name == 'services'))}
    # Disabled inputs are not public and do not need to satisfy module contracts.
    rows = {name: value if name in active else [] for name, value in rows.items()}
    journal = config.get('journal', False)
    participants = rows['participants']
    people = rows['people']
    participant_map = {p['id']: p for p in participants}
    person_map = {p['id']: p for p in people}
    for name, values in rows.items():
        for item in values:
            item['sources'] = sources(item)
            if item.get('checked_at'):
                date_value(item['checked_at'], tz)
            for field in ('participant_ids', 'people_ids'):
                ids = item.get(field, [])
                if not isinstance(ids, list):
                    raise ValueError(f'{field} must be an array')
                known = participant_map if field == 'participant_ids' else person_map
                # A link to a disabled people module is omitted, never dangling.
                if field == 'participant_ids' and set(ids) - known.keys():
                    raise ValueError(f'Unknown participant reference in {name}: {item["id"]}')
            if name not in ('posts',) and not (item.get('name') or item.get('title')):
                raise ValueError(f'Missing name/title in {name}: {item["id"]}')

    for name, values, folder in [('participants', participants, 'participants'), ('people', people, 'people')]:
        for item in values:
            item.setdefault('name', item.get('title', ''))
            item['page'] = f'{folder}/{item["id"]}.html'
            for key in ('about', 'country', 'role', 'contacts_text'):
                item.setdefault(key, '')
            for key in ('stands', 'halls', 'categories', 'rubrics', 'materials', 'news'):
                item.setdefault(key, [])
            item['image_view'] = asset(item.get('logo' if name == 'participants' else 'photo'), out)
            item['screenshot_view'] = asset(item.get('screenshot'), out)
            contacts = item.get('contacts') or item.get('links') or []
            item['links'] = []
            for link in contacts:
                if not isinstance(link, dict) or not link.get('label') or not link.get('value'):
                    raise ValueError(f'Invalid contact on {item["id"]}')
                item['links'].append({**link, 'url': safe_url(link.get('url', ''), contact=True)})
            item['media_view'] = []
            for medium in item.get('media', []):
                href = asset(medium.get('path') or medium.get('url'), out)
                status = medium.get('download_status', 'not_downloaded')
                if not href and status == 'downloaded':
                    raise ValueError(f'Missing downloaded media on {item["id"]}')
                item['media_view'].append({**medium, 'href': href, 'download_status': status})

    channels = load_rows(root, 'channels') if rows['posts'] else []
    channel_map = {c['id']: c for c in channels}
    for channel in channels:
        if not safe_url(channel.get('url')) or not channel.get('title'):
            raise ValueError(f'Invalid channel {channel["id"]}')
        if set(channel.get('participant_ids', [])) - participant_map.keys():
            raise ValueError(f'Unknown participant on channel {channel["id"]}')
    analysis_path = root / 'data/portal/post_analysis.jsonl'
    analysis_rows = [json.loads(line) for line in analysis_path.read_text(encoding='utf-8-sig').splitlines() if line.strip()] if rows['posts'] and analysis_path.exists() else []
    analyses = {}
    for a in analysis_rows:
        post_id = str(a.get('post_id', ''))
        if not post_id or post_id in analyses:
            raise ValueError('post_analysis.jsonl must have unique nonempty post_id values')
        analyses[post_id] = a
    for post in rows['posts']:
        if post.get('channel_id') not in channel_map or not safe_url(post.get('url')):
            raise ValueError(f'Invalid post channel or source URL: {post["id"]}')
        if not isinstance(post.get('text', ''), str):
            raise ValueError('Post text must be plain text')
        date_value(post.get('published_at'), tz)
        channel = channel_map[post['channel_id']]
        post['channel'] = channel
        input_hash = analysis_hash(config, post)
        post['participant_ids'] = list(dict.fromkeys(post.get('participant_ids', []) + channel.get('participant_ids', [])))
        post['people_ids'] = list(dict.fromkeys(post.get('people_ids', []) + channel.get('people_ids', [])))
        post['excerpt'] = excerpt(post.get('text', ''), 45)
        post['photos_view'] = [v for x in post.get('photos', []) if (v := asset(x, out))]
        post['preview_kind'] = next((m.get('type') for m in post.get('media', [])
                                     if post['photos_view'] and m.get('local_path')==post['photos_view'][0]), None)
        a = analyses.get(post['id'], {})
        kind_labels = {'giveaway': 'Розыгрыш', 'prize_contest': 'Призовой конкурс', 'gift_for_visit': 'Подарок за визит', 'discount': 'Скидка', 'other': '', 'unclear': 'Условия уточняются'}
        relevance_labels = {'current_expo': 'Текущая выставка', 'online_only': 'Онлайн', 'other_event': 'Другое событие', 'unclear': 'Связь не уточнена'}
        current = (a.get('input_hash') == input_hash and a.get('task_version') == 'expo-post-v3'
                   and a.get('review_status') in ('verified','reused_text') and a.get('classification') in kind_labels
                   and a.get('relevance') in relevance_labels)
        if current:
            if a.get('checked_at'):
                date_value(a['checked_at'], tz)
        post['analysis_label'] = ' · '.join(v for v in (kind_labels[a['classification']], relevance_labels[a['relevance']]) if v) if current and a.get('classification') != 'other' else ''
        post['analysis_status'] = 'Разбор относится к этому тексту и выпуску' if current else 'Разбор ожидается'
        post['is_current_expo'] = bool(current and a.get('relevance') == 'current_expo')
    rows['posts'].sort(key=lambda p: p.get('published_at') or '', reverse=True)

    days = defaultdict(list)
    for event in rows['program']:
        event_date = date_value(event.get('date'), tz)
        if event_date is not None and type(event_date) is not date:
            raise ValueError('program.date must be an ISO date, not datetime')
        for key in ('start', 'end'):
            if event.get(key) and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', event[key]):
                raise ValueError(f'program.{key} must be HH:MM or null')
        if event.get('start') and not event_date:
            raise ValueError('Program time without a complete date is ambiguous')
        days[event.get('date') or ''].append(event)
    days = sorted(days.items(), key=lambda pair: (not bool(pair[0]), pair[0]))
    for _, events in days:
        events.sort(key=lambda e: (not bool(e.get('start')), e.get('start') or '', e['id']))

    giveaways = defaultdict(list)
    snapshot = date_value(config['checked_at'], tz)
    snapshot_date = snapshot.date() if isinstance(snapshot, datetime) else snapshot
    for g in rows['giveaways']:
        when = date_value(g.get('when'), tz)
        for key in ('entry_deadline', 'results_at'):
            date_value(g.get(key), tz)
        # Uncertainty outranks cancellation and elapsed dates. No inferred "confirmed" status.
        uncertain = g.get('review_status') != 'reviewed' or not when
        if uncertain:
            group = 'Требует уточнения'
        elif g.get('status') == 'cancelled':
            group = 'Отменённые'
        elif (when.date() if isinstance(when, datetime) else when) < snapshot_date or (
            isinstance(when, datetime) and isinstance(snapshot, datetime) and when < snapshot
        ):
            group = 'Прошедшие по расписанию'
        else:
            group = 'Предстоящие по расписанию'
        g['group'] = group
        g['date_only'] = type(when) is date
        giveaways[group].append(g)

    for name in ('services', 'videos', 'novelties'):
        for item in rows[name]:
            if item.get('url') and not safe_url(item['url']):
                raise ValueError(f'Unsafe {name} URL')
            item['image_view'] = asset(item.get('image'), out)
    for article in rows['articles']:
        fragment = inside(root / 'data/portal', article.get('content_file'))
        article['html'] = fragment.read_text(encoding='utf-8')
        Fragment(out).feed(article['html'])
        article['page'] = f'article-{article["id"]}.html'

    labels = {key: value[1] for key, value in MODULES.items()}
    labels.update(config.get('labels', {}))
    nav = [('index.html', 'Главная')] + [(MODULES[k][0], labels[k]) for k in MODULES if k in active]
    speaker_items, business_guides, promotions = [], [], []
    if journal:
        nav.extend([('speaker-feed.html', 'Лента спикеров'), ('giveaways.html', 'Розыгрыши'), ('business.html', 'Карта бизнеса')])
        for social in read_json(root / 'data/portal/speaker_socials.json', []):
            person = person_map[social['person_id']]
            person['socials'] = social.get('links', [])
        for p in read_json(root / 'data/portal/speaker_posts.json', []):
            p['people_ids'] = p['person_ids']
            p['channel'] = {'title': p['channel_title'], 'url': p['channel_url']}
            p['excerpt'] = excerpt(p.get('text', ''), 45)
            p['photos_view'] = [img for x in p.get('photos', []) if (img := asset(x, out))]
            speaker_items.append(p)
        speaker_items.sort(key=lambda p: p.get('published_at') or '', reverse=True)
        business_guides = read_json(root / 'data/portal/business.json', [])
        promotions = read_json(root / 'data/portal/promotions.json', [])
        for guide in business_guides:
            identifier(guide['id'])
            if set(guide['people']) - participant_map.keys():
                raise ValueError('Unknown business guide exhibitor')
    style = (root / 'portal_web/style.css').read_text(encoding='utf-8').encode('utf-8')
    script = (root / 'portal_web/portal.js').read_text(encoding='utf-8').encode('utf-8')
    env = Environment(loader=FileSystemLoader(root / 'portal_web'), autoescape=select_autoescape(['html', 'xml']))
    env.filters.update(excerpt=excerpt, date_text=lambda value: date_text(value, tz), url=safe_url)
    env.tests['contains_id'] = lambda ids, value: value in ids
    featured_posts = [post for post in rows['posts'] if post.get('is_current_expo')]
    context = dict(config=config, labels=labels, nav=nav, enabled=active, participants=participants,
                   participant_map=participant_map, person_map=person_map, people=people, posts=rows['posts'],
                   featured_posts=featured_posts,
                     channel_count=len(channels),
                     channel_preview_count=sum(1 for c in channels if c.get('status') == 'public_preview'), days=days,
                   giveaway_groups=list(giveaways.items()), rows=rows, feed_count=feed_count,
                   style_version=digest(style)[:16], script_version=digest(script)[:16],
                   dates_label=config.get('dates_label') or f'{start:%d.%m.%Y} — {end:%d.%m.%Y}')
    context.update(speaker_items=speaker_items, business_guides=business_guides,
                   business_groups=sorted({g['group'] for g in business_guides}),
                   booth_draws=any(p['scope']=='На выставке' and p['kind']=='Розыгрыш' for p in promotions),
                   promotion_sections=[(group,[p for p in promotions if p['group']==group])
                                       for group in dict.fromkeys(p['group'] for p in promotions)])
    screening_path = root / 'data/portal/service_screening.json'
    screening = read_json(screening_path, {}) if screening_path.exists() else {}
    context['service_summary'] = screening.get('summary', {})
    context['service_candidates'] = [c for c in screening.get('candidates', [])
                                     if c.get('participant_id') in participant_map]
    context['service_categories'] = sorted({category for item in rows['services'] for category in item.get('categories', [])})
    event_name = config.get('brand_name') or f'{config["name"]} {config["edition"]}'
    context['event_schema'] = {'@context': 'https://schema.org', '@type': 'Event',
        'name': event_name, 'startDate': config['start_date'],
        'endDate': config['end_date'], 'location': {'@type': 'Place', 'name': config['place']}}
    if config.get('official_url'):
        context['event_schema']['url'] = config['official_url']
    favicon = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#223b32"/><text x="32" y="45" text-anchor="middle" font-family="Georgia,serif" font-weight="700" font-size="42" fill="#fffdf9">M</text></svg>'
    generated = {'portal-assets/style.css': style, 'portal-assets/portal.js': script, 'favicon.svg': favicon}

    def render(path, template, title, **extra):
        prefix = '../' * (len(PurePosixPath(path).parts) - 1)
        canonical = base + path if base else ''
        title = f'{title} · {event_name}'
        html = env.get_template(template).render(**context, prefix=prefix, canonical=canonical,
                                                active=path, title=title, description=extra.pop('description', title), **extra)
        generated[path] = re.sub(r'^[ \t]+$', '', html, flags=re.MULTILINE).encode('utf-8')

    if journal:
        render('speaker-feed.html', 'posts.html', 'Лента спикеров', speaker_feed=True)
        render('giveaways.html', 'promotions.html', 'Розыгрыши и акции')
        render('business.html', 'business.html', 'Карта бизнеса', guide=None)
        for guide in business_guides:
            render(f"business/{guide['id']}.html", 'business.html', guide['title'], guide=guide)
    render('index.html', 'index.html', 'Навигатор выставки')
    render('catalog.html', 'catalog.html', labels['participants'],
           countries=sorted({p['country'] for p in participants if p['country']}),
           categories=sorted({v for p in participants for v in p['categories']}),
           halls=sorted({v for p in participants for v in p['halls']}))
    for name, values in [('participants', participants), ('people', people)]:
        for item in values:
            related = [p for p in rows['posts'] if item['id'] in p.get('participant_ids' if name == 'participants' else 'people_ids', [])]
            if name == 'people' and speaker_items:
                related = [p for p in speaker_items if item['id'] in p['people_ids']] + related
            render(item['page'], 'profile.html', item['name'], item=item, profile_type=name, item_posts=related[:feed_count])
    for name in MODULES:
        if name not in active or name == 'participants':
            continue
        template = 'services.html' if name == 'services' else (f'{name}.html' if name in ('people', 'program', 'posts', 'giveaways', 'articles', 'map', 'novelties') else 'listing.html')
        render(MODULES[name][0], template, labels[name], module=name, items=rows.get(name, []))
    for article in rows['articles']:
        render(article['page'], 'article.html', article['title'], item=article, description=article.get('summary') or article['title'])
    generated['exports/participants.json'] = (json.dumps(participants, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if 'services' in active:
        generated['exports/services.json'] = (json.dumps(rows['services'], ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        generated['exports/service-screening.json'] = (json.dumps(screening, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        service_csv = io.StringIO(newline='')
        sw = csv.writer(service_csv)
        sw.writerow(['id', 'title', 'categories', 'participant_ids', 'description', 'evidence', 'url', 'sources'])
        for service in rows['services']:
            sw.writerow([service['id'], service['title'], '; '.join(service.get('categories', [])),
                         '; '.join(service.get('participant_ids', [])), service.get('description', ''),
                         service.get('evidence', ''), service.get('url', ''),
                         '; '.join(source['url'] for source in service['sources'])])
        generated['exports/services.csv'] = service_csv.getvalue().encode('utf-8-sig')
    output_csv = io.StringIO(newline='')
    writer = csv.writer(output_csv)
    writer.writerow(['id', 'name', 'country', 'stands', 'sources'])
    def csv_cell(value):
        return "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
    for p in participants:
        writer.writerow([csv_cell(v) for v in [p['id'], p['name'], p['country'], '; '.join(p['stands']), '; '.join(s['url'] for s in p['sources'])]])
    generated['exports/participants.csv'] = output_csv.getvalue().encode('utf-8-sig')
    # Content hashes retain lastmod and filesystem mtime across identical builds.
    manifest_path = output_file(out, '.portal-manifest.json')
    previous = read_json(manifest_path, {})
    if previous and (not isinstance(previous, dict) or previous.get('generator') != 'expo-portal' or not isinstance(previous.get('files'), dict)):
        raise ValueError('Output manifest belongs to a different generator or has an invalid schema')
    old_files = previous.get('files', {})
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    pages = {}
    for path, content in generated.items():
        old = old_files.get(path, {})
        content_hash = digest(content)
        pages[path] = {'sha256': content_hash, 'lastmod': old.get('lastmod', now) if old.get('sha256') == content_hash else now}
    if base:
        entries = ''.join(f'<url><loc>{escape(base + p)}</loc><lastmod>{pages[p]["lastmod"]}</lastmod></url>' for p in sorted(pages) if p.endswith('.html'))
        generated['sitemap.xml'] = ('<?xml version="1.0" encoding="utf-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + entries + '</urlset>').encode('utf-8')
    generated['.portal-manifest.json'] = (json.dumps({'generator': 'expo-portal', 'files': pages,
        'auxiliary': ['sitemap.xml'] if base else []}, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    # Only delete entries previously owned by this generator, never media or arbitrary files.
    owned = set(old_files) | set(previous.get('auxiliary', []))
    if previous:
        owned.add('.portal-manifest.json')
    # Preflight every destination before writing or deleting anything.
    for path in generated:
        target = output_file(out, path)
        if target.exists() and path not in owned:
            raise ValueError(f'Refusing to overwrite foreign existing output: {path}')
    for path in set(old_files) | set(previous.get('auxiliary', [])):
        if path not in generated:
            p = local_path(path)
            if not p or p.parts[0] == 'media':
                raise ValueError('Unsafe previous output manifest')
            target = output_file(out, path)
            if target.is_file():
                target.unlink()
    for path, content in generated.items():
        target = output_file(out, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != content:
            target.write_bytes(content)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, help='Explicit output override; synthetic smoke tests use a temporary directory')
    args = parser.parse_args()
    try:
        print(build(args.root, args.output))
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(f'Portal build failed: {exc}') from exc


if __name__ == '__main__':
    main()
