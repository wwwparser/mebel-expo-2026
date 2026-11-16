"""Create an explicitly synthetic all-module project outside the distributable template."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from build_portal import ROOT, MODULES, analysis_hash


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def create(destination):
    destination = Path(destination).resolve()
    if destination == ROOT or destination.is_relative_to(ROOT) or ROOT.is_relative_to(destination):
        raise ValueError('Synthetic fixture must be outside the template directory')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Fixture destination must be empty')
    shutil.copytree(ROOT, destination, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '.venv', 'docs', '.env'))
    data = destination / 'data/portal'
    media = destination / 'docs/media'
    media.mkdir(parents=True, exist_ok=True)
    (media / 'synthetic.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360"><rect width="640" height="360" fill="#f3e4d4"/><text x="40" y="180" font-size="30" fill="#2a2018">СИНТЕТИЧЕСКИЙ ПРИМЕР</text></svg>', encoding='utf-8')
    config = {'name': 'СИНТЕТИЧЕСКИЙ ПРИМЕР — Форум материалов', 'edition': 'учебный выпуск',
              'start_date': '2034-04-08', 'end_date': '2034-04-10', 'dates_label': '',
              'place': 'Синтетический город, учебный павильон', 'timezone': 'Europe/Moscow',
              'base_url': 'https://example.example/nested/exhibition/',
              'official_url': 'https://example.example/', 'catalog_url': 'https://example.example/catalog/',
              'scheme_url': 'https://example.example/scheme/', 'checked_at': '2034-04-08T10:00:00+03:00',
              'output_dir': 'docs', 'modules': list(MODULES), 'feed_count': 2, 'labels': {}}
    write_json(destination / 'expo.json', config)
    source = [{'title': 'Синтетический источник для проверки шаблона', 'url': 'https://example.example/source/', 'date': '2034-04-08'}]
    def row(id, **values):
        return {'id': id, 'sources': source, **values}
    write_json(data / 'participants.json', [row('atelier', name='Синтетическая мастерская',
        about='Учебная карточка компании для проверки вёрстки. Эти сведения не описывают реального участника.',
        country='Учебная страна', stands=['A-12'], halls=['Учебный зал'], categories=['Материалы'], logo='media/synthetic.svg',
        checked_at=config['checked_at'], contacts=[{'label': 'Сайт', 'value': 'Синтетическая ссылка', 'url': 'https://example.example/company/'}],
        media=[{'title': 'Учебный документ', 'type': 'document', 'url': 'https://example.example/document.pdf', 'download_status': 'external_only'}],
        materials=[{'title': 'Учебное описание', 'text': 'Только синтетический текст.'}]),
        row('bureau', name='Синтетическое бюро', about='Вторая учебная запись, связанная с общим каналом.', country='Другая учебная страна')])
    write_json(data / 'people.json', [row('speaker', name='Учебный спикер', role='Синтетический эксперт', about='Учебный профиль.', photo='media/synthetic.svg')])
    write_json(data / 'program.json', [row('talk', title='Синтетическая встреча', date='2034-04-09', start='11:00', end='11:40',
        venue='Учебная сцена', people_ids=['speaker'], description='Анонс для проверки расписания.'),
        row('day', title='Учебный дневной анонс', date='2034-04-10', start=None),
        row('unknown', title='Синтетический анонс без даты', date=None, start=None)])
    write_json(data / 'channels.json', [{'id': 'shared', 'title': 'Синтетический общий канал', 'url': 'https://example.example/channel/',
        'participant_ids': ['atelier', 'bureau'], 'people_ids': ['speaker']}])
    posts = [row('post-a', channel_id='shared', text=' '.join(['Синтетический текст публикации'] * 35) + ' UNIQUE_FULL_BODY_END',
                 published_at='2034-04-08T08:30:00+03:00', url='https://example.example/channel/1',
                 participant_ids=['atelier'], people_ids=[], photos=['media/synthetic.svg']),
             row('post-b', channel_id='shared', text='Вторая синтетическая публикация для проверки общего канала.',
                 published_at='2034-04-08T09:00:00+03:00', url='https://example.example/channel/2')]
    write_json(data / 'posts.json', posts)
    analyses = [{'post_id': 'post-a', 'task_version': 'expo-post-v3', 'input_hash': analysis_hash(config, posts[0]),
                 'review_status': 'verified', 'classification': 'giveaway', 'relevance': 'current_expo'},
                {'post_id': 'post-b', 'task_version': 'expo-post-v3', 'input_hash': 'stale',
                 'review_status': 'verified', 'classification': 'STALE_MUST_NOT_RENDER'}]
    (data / 'post_analysis.jsonl').write_text('\n'.join(json.dumps(a, ensure_ascii=False) for a in analyses) + '\n', encoding='utf-8')
    write_json(data / 'giveaways.json', [row('upcoming', title='Учебный конкурс на стенде', when='2034-04-09T14:00:00+03:00',
        review_status='reviewed', kind='Синтетический конкурс', participant_ids=['atelier'], stand='A-12', prizes=['Учебный приз'],
        conditions=['Синтетические условия.'], entry_deadline='2034-04-09T12:00:00+03:00', results_at='2034-04-09T15:00:00+03:00'),
        row('uncertain', title='Учебное событие с неясной датой', when='2034-04-01', review_status='needs_review', status='cancelled'),
        row('cancelled', title='Учебное отменённое событие', when='2034-04-09', review_status='reviewed', status='cancelled'),
        row('past', title='Учебное прошедшее событие', when='2034-04-07', review_status='reviewed'),
        row('date-only', title='Учебный анонс без времени', when='2034-04-10', review_status='reviewed')])
    for module, title in [('services', 'Синтетическая услуга'), ('videos', 'Синтетическое видео'), ('novelties', 'Синтетическая новинка')]:
        write_json(data / f'{module}.json', [row(module + '-a', title=title, description='Учебная запись для проверки карточки.',
            url='https://example.example/' + module + '/', participant_ids=['atelier'], evidence='Синтетическая цитата источника.', image='media/synthetic.svg')])
    (data / 'article-demo.html').write_text('<section id="demo-section"><h2>Синтетическая заметка</h2><p>Это авторский учебный фрагмент. Он не содержит рыночных показателей и фактов о реальной выставке.</p></section>', encoding='utf-8')
    write_json(data / 'articles.json', [row('demo', title='Синтетический авторский материал',
        summary='Материал исключительно для проверки шаблона.', author='Учебный автор',
        checked_at=config['checked_at'], content_file='article-demo.html')])
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(create(args.destination))
