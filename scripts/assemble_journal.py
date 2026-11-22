"""Assemble reviewed exhibitor batches into the public journal. Run from the repository root."""
import argparse
import json
from datetime import date
from pathlib import Path

from analysis_queue import validate_record
from build_portal import analysis_hash

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/portal'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save(name, value):
    path = DATA / name
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--as-of', required=True, type=date.fromisoformat)
    args = parser.parse_args()
    day = args.as_of.isoformat()
    cfg = read(ROOT / 'expo.json')
    posts, channels, analyses, findings = {}, {}, {}, []
    for batch in sorted(args.directory.glob('*.json')):
        if not (labels := batch.with_name(batch.stem+'-analysis.jsonl')).exists():
            continue
        snapshot = read(batch)
        medialist = batch.with_name(batch.stem+'-media.json')
        media = read(medialist)['posts'] if medialist.exists() else {}
        for c in snapshot['channels']:
            if c['id'] in channels or c['status'] == 'fetch_error':
                raise ValueError('Duplicate or failed channel: '+c['id'])
            channels[c['id']] = c
        for p in snapshot['posts']:
            if p['id'] in posts:
                raise ValueError('Duplicate post: '+p['id'])
            p['media'] = media.get(p['id'], p.get('media', []))
            posts[p['id']] = p
        for line in labels.read_text(encoding='utf-8-sig').splitlines():
            row = json.loads(line)
            post = posts[row['post_id']]
            validate_record(row, dict(post, post_id=post['id'], input_hash=analysis_hash(cfg,post)), cfg)
            analyses[post['id']] = row
        findings.extend(read(batch.with_name(batch.stem+'-new.json')))
    if set(posts) != set(analyses) or set(channels) != {c['id'] for c in read(DATA/'channels.json')}:
        raise ValueError('Incomplete journal snapshot')
    overrides = args.directory/'adjudicated.jsonl'
    if overrides.exists():
        for line in overrides.read_text(encoding='utf8').splitlines():
            row = json.loads(line)
            post = posts[row['post_id']]
            validate_record(row, dict(post,post_id=post['id'], input_hash=analysis_hash(cfg,post)),cfg)
            analyses[post['id']] = row
    media_notes = [
        ('tgpost-west_line-448','SWITCH — контроллер для светодиодных лент','На иллюстрации Westline указана поддержка системы Tuya. Контроллер предназначен для управления светодиодной лентой.'),
        ('tgpost-artrobot_su-248','PROFI MAXI — робот-маляр','АРТРОБОТ показывает окрашивающую установку и указывает на постере диапазон от четырёх до девяти степеней свободы. Конфигурацию для конкретного изделия нужно уточнять у производителя.')]
    for pid,title,description in media_notes:
        if pid in posts and not any(f['post_id']==pid for f in findings):
            findings.append(dict(post_id=pid,title=title,description=description,expo=False,image_evidence=True))
    findings.extend(read(DATA/'editorial_novelties.json'))
    firms = {p['name']:p['id'] for p in read(DATA/'participants.json')}
    reported_exhibitors = {'tgpost-mebclub-6710': firms['ТБМ'], 'tgpost-mebclub-6717': firms['ДЕГОН-СЕРВИС']}
    novelties = read(DATA/'website_novelties.json')
    seen = set()
    for f in findings:
        pid = f['post_id']
        p = posts[pid]
        if pid in seen or not p.get('photos') or pid in ('tgpost-ramkad173-786','tgpost-kalinka_mebel-766','tgpost-dik_mebel-1472','tgpost-souz_m_company-2328'):
            continue
        evidence = f.get('evidence')
        poster_source = f.get('source') in p['photos'] and not p['text']
        if evidence and not poster_source and not any(q in p['text'] for q in ([evidence] if isinstance(evidence,str) else evidence)):
            raise ValueError('Product evidence absent: '+pid)
        seen.add(pid)
        novelties.append(dict(id=pid,title=f['title'],description=f['description'],expo=f['expo'],
                              participant_ids=[reported_exhibitors[pid]] if pid in reported_exhibitors else p['participant_ids'],url=p['url'],image=p['photos'][0],
                              checked_at=day,source_type='Telegram',published_at=p['published_at'],
                              sources=[dict(title=channels[p['channel_id']]['title'],url=p['url'])]))
    novelties.sort(key=lambda r:(r['expo'],r.get('published_at') or day),reverse=True)
    offers=[]
    for item in read(DATA/'promotion_notes.json'):
        p=posts.get(item['post_id'])
        if not p:
            continue
        offers.append(dict(item,url=p['url'],published_at=p['published_at'],participant_ids=p['participant_ids'],
                           image=next(iter(p['photos']),None),channel=channels[p['channel_id']]['title']))
    dated=sorted(posts.values(),key=lambda p:p.get('published_at') or '', reverse=True)
    save('channels.json',list(channels.values()))
    save('posts.json',dated)
    save('novelties.json',novelties)
    save('promotions.json',offers)
    path=DATA/'post_analysis.jsonl'
    temp=path.with_suffix('.tmp')
    temp.write_text(''.join(json.dumps(analyses[p['id']],ensure_ascii=False)+'\n' for p in dated),encoding='utf8')
    temp.replace(path)
    print(f'{len(dated)} posts, {len(offers)} offer cards, {len(novelties)} product cards')


if __name__=='__main__':
    main()
