"""Executable offline positive/negative checks, entirely within an OS temp directory."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from build_portal import build, digest, safe_url, local_path, analysis_hash
from check_portal import check
from demo_fixture import create, write_json


def rejects(function, text):
    try:
        function()
    except (ValueError, OSError) as exc:
        assert text in str(exc), (text, str(exc))
    else:
        raise AssertionError(f'Expected rejection containing: {text}')


def main():
    with tempfile.TemporaryDirectory(prefix='expo-portal-smoke-') as temp:
        root = create(Path(temp) / 'project')
        data = root / 'data/portal'
        out = build(root)
        assert check(out) == 15
        text = (out / 'feed.html').read_text(encoding='utf-8')
        assert 'UNIQUE_FULL_BODY_END' not in text, 'Only excerpts may be publicly rendered'
        assert 'Розыгрыш · Текущая выставка' in text
        assert 'STALE_MUST_NOT_RENDER' not in text and 'Разбор ожидается' in text
        for profile in ['participants/atelier.html', 'participants/bureau.html', 'people/speaker.html']:
            assert 'Синтетический общий канал' in (out / profile).read_text(encoding='utf-8')
        assert 'Синтетическая встреча' in (out / 'people/speaker.html').read_text(encoding='utf-8')
        assert 'https://example.example/nested/exhibition/participants/atelier.html' in (out / 'participants/atelier.html').read_text(encoding='utf-8')
        html = (out / 'giveaways.html').read_text(encoding='utf-8')
        assert html.index('Требует уточнения') < html.index('Учебное событие с неясной датой') < html.index('Отменённые')
        assert 'Время не указано' in html
        # No legacy brand/domain/numeric catalog or year facts are injected.
        published = '\n'.join(p.read_text(encoding='utf-8') for p in out.rglob('*.html'))
        assert not any(s in published.lower() for s in ['mitex', 'mitexpo', '7054', '745'])
        assert 'Рынок инструмента' not in published
        before = {p.relative_to(out): (p.read_bytes(), p.stat().st_mtime_ns) for p in out.rglob('*') if p.is_file()}
        build(root)
        after = {p.relative_to(out): (p.read_bytes(), p.stat().st_mtime_ns) for p in out.rglob('*') if p.is_file()}
        assert before == after, 'Identical builds must preserve bytes, mtimes and lastmod'
        foreign = Path(temp) / 'foreign-output'
        foreign.mkdir()
        (foreign / 'index.html').write_text('Existing unrelated page', encoding='utf-8')
        rejects(lambda: build(root, foreign), 'foreign existing output')
        assert (foreign / 'index.html').read_text(encoding='utf-8') == 'Existing unrelated page'
        assert len(list(foreign.iterdir())) == 1, 'Output collision must fail before any mutations'
        # Source stylesheet changes propagate to every page's cache key.
        css = root / 'portal_web/style.css'
        old_hash = digest(css.read_bytes())[:16]
        css.write_bytes(css.read_bytes() + b'\n/* synthetic cache-key smoke check */\n')
        build(root)
        assert check(out) == 15
        assert old_hash != digest(css.read_bytes())[:16]
        assert '?v=' + old_hash not in (out / 'index.html').read_text(encoding='utf-8')
        # Context and text edits invalidate a previously accepted analysis.
        config = json.loads((root / 'expo.json').read_text(encoding='utf-8'))
        original_config = dict(config)
        config['edition'] = 'другой синтетический выпуск'
        write_json(root / 'expo.json', config)
        build(root)
        assert 'Розыгрыш · Текущая выставка' not in (out / 'feed.html').read_text(encoding='utf-8')
        write_json(root / 'expo.json', original_config)
        posts = json.loads((data / 'posts.json').read_text(encoding='utf-8'))
        original_posts = json.loads(json.dumps(posts))
        posts[0]['text'] += ' Изменённый текст.'
        write_json(data / 'posts.json', posts)
        build(root)
        assert 'Розыгрыш · Текущая выставка' not in (out / 'feed.html').read_text(encoding='utf-8')
        write_json(data / 'posts.json', original_posts)
        analysis = data / 'post_analysis.jsonl'
        original_analysis = analysis.read_text(encoding='utf-8')
        values = [json.loads(line) for line in original_analysis.splitlines()]
        values[0]['review_status'] = 'needs_review'
        analysis.write_text('\n'.join(json.dumps(value) for value in values) + '\n', encoding='utf-8')
        build(root)
        assert 'Розыгрыш · Текущая выставка' not in (out / 'feed.html').read_text(encoding='utf-8')
        analysis.write_text(original_analysis, encoding='utf-8')
        # Empty and disabled modules disappear from pages/nav; cleanup touches owned outputs only.
        (out / 'media').mkdir(exist_ok=True)
        (out / 'media/keep.txt').write_text('Keep source media', encoding='utf-8')
        (out / 'manual.html').write_text('Keep manually authored output', encoding='utf-8')
        write_json(data / 'videos.json', [])
        config = dict(original_config, modules=['participants', 'videos'])
        write_json(root / 'expo.json', config)
        build(root)
        assert check(out) == 4
        home = (out / 'index.html').read_text(encoding='utf-8')
        assert 'videos.html' not in home and 'program.html' not in home and 'people.html' not in home
        assert not (out / 'videos.html').exists() and not (out / 'program.html').exists()
        assert (out / 'media/keep.txt').exists() and (out / 'manual.html').exists()
        # Invalid or missing required data never silently falls back.
        participants = json.loads((data / 'participants.json').read_text(encoding='utf-8'))
        (data / 'participants.json').unlink()
        rejects(lambda: build(root), 'at least one participant')
        write_json(data / 'participants.json', participants)
        for invalid in ('2034', '04-08'):
            write_json(root / 'expo.json', dict(config, start_date=invalid))
            rejects(lambda: build(root), 'complete ISO date')
        write_json(root / 'expo.json', config)
        rejects(lambda: build(root, root / 'portal_web'), 'overlaps project source')
        rejects(lambda: build(root, out / 'media'), 'overlaps project source')
        assert not safe_url('javascript:alert(1)') and not safe_url('//example.example/x')
        assert local_path('../secret') is None and local_path('media/%2e%2e/secret') is None
        # Authored article HTML rejects active code instead of publishing it.
        write_json(root / 'expo.json', dict(config, modules=['participants', 'articles']))
        article = data / 'article-demo.html'
        original_article = article.read_text(encoding='utf-8')
        article.write_text('<script>alert(1)</script>', encoding='utf-8')
        rejects(lambda: build(root), 'disallows <script>')
        article.write_text('<p><a href="javascript:alert(1)">Bad</a></p>', encoding='utf-8')
        rejects(lambda: build(root), 'Unsafe article reference')
        article.write_text(original_article, encoding='utf-8')
        build(root)
        assert check(out) == 6
    print('PASS: all-module build, links, idempotency, hashes, attribution, shared channels, dates, stale analysis, optional cleanup and negative safety checks')


if __name__ == '__main__':
    main()
