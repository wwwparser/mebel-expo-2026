"""Offline structural/link/hash check. Browser and six-visitor audits remain necessary."""
from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from build_portal import ROOT, digest, safe_url, read_json, inside


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs, self.ids, self.errors = [], set(), []
        self.h1_count = 0
        self.canonical = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            if attrs['id'] in self.ids:
                self.errors.append(f'Duplicate HTML ID {attrs["id"]}')
            self.ids.add(attrs['id'])
        if tag == 'h1':
            self.h1_count += 1
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical = attrs.get('href', '')
        for name in ('href', 'src'):
            if name in attrs:
                self.refs.append((tag, name, attrs[name]))
        if tag == 'img' and 'alt' not in attrs:
            self.errors.append('Image without alt attribute')


def check(output):
    output = Path(output).resolve()
    manifest = json.loads((output / '.portal-manifest.json').read_text(encoding='utf-8'))
    errors, pages = [], {}
    if manifest.get('generator') != 'expo-portal':
        errors.append('Unexpected manifest owner')
    for name, record in manifest['files'].items():
        path = (output / name).resolve()
        if not path.is_relative_to(output) or not path.is_file():
            errors.append(f'Missing generated file: {name}')
            continue
        if digest(path.read_bytes()) != record['sha256']:
            errors.append(f'Content hash mismatch: {name}')
        if path.suffix == '.html':
            page = Page()
            page.feed(path.read_text(encoding='utf-8'))
            pages[path] = page
            errors.extend(f'{name}: {message}' for message in page.errors)
            if page.h1_count != 1:
                errors.append(f'{name}: expected exactly one h1')
    for path, page in pages.items():
        for tag, attr, ref in page.refs:
            if not ref:
                errors.append(f'{path.name}: empty {tag}.{attr}')
                continue
            parsed = urlsplit(ref)
            if parsed.scheme:
                if not safe_url(ref, contact=tag == 'a'):
                    errors.append(f'{path.name}: unsafe URL {ref}')
                continue
            if parsed.netloc or ref.startswith('/') or '\\' in ref:
                errors.append(f'{path.name}: reference breaks relative subpath hosting: {ref}')
                continue
            target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if not target.is_relative_to(output) or not target.is_file():
                errors.append(f'{path.name}: missing relative reference {ref}')
            elif parsed.fragment and target in pages and parsed.fragment not in pages[target].ids:
                errors.append(f'{path.name}: missing anchor {ref}')
            if tag == 'link' and parsed.path.endswith('portal-assets/style.css'):
                expected = digest(target.read_bytes())[:16] if target.is_file() else ''
                if parsed.query != 'v=' + expected:
                    errors.append(f'{path.name}: stylesheet version is not its content hash')
        if page.canonical and not safe_url(page.canonical):
            errors.append(f'{path.name}: invalid canonical URL')
    if errors:
        raise ValueError('\n'.join(errors))
    return len(pages)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    config = read_json(ROOT / 'expo.json', {})
    parser.add_argument('output', type=Path, nargs='?', default=inside(ROOT, config.get('output_dir', 'docs')))
    args = parser.parse_args()
    try:
        print(f'OK: {check(args.output)} pages; local references and asset hashes verified')
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc
