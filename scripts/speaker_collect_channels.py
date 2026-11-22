#!/usr/bin/env python3
"""Fetch verified public Telegram previews without changing channels.json."""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from telegram_snapshot import fetch
# All channels are individually identity-checked in speaker_socials.json.
CHANNELS=[
 {'id':'tg-speaker-averhovod','url':'https://t.me/averhovod','preview_url':'https://t.me/s/averhovod','participant_ids':['sp-fe94919984a7'],'source_urls':['https://alexeyverhovod.ru/','https://t.me/averhovod'],'account_type':'personal'},
 {'id':'tg-speaker-golubkov-economics','url':'https://t.me/golubkov_economics','preview_url':'https://t.me/s/golubkov_economics','participant_ids':['sp-50c76fbd153c'],'source_urls':['https://golubkov-expert.ru/','https://t.me/golubkov_economics'],'account_type':'personal'},
 {'id':'tg-speaker-planirovka-pro','url':'https://t.me/Planirovka_pro','preview_url':'https://t.me/s/Planirovka_pro','participant_ids':['sp-e17165f8b8e5'],'source_urls':['https://planirovkaplus.ru/','https://t.me/Planirovka_pro'],'account_type':'personal_professional_brand'},
 {'id':'tg-speaker-kryukova-lawyer','url':'https://t.me/kriukova_lawyer','preview_url':'https://t.me/s/kriukova_lawyer','participant_ids':['sp-434ad79e9ae2'],'source_urls':['https://designschool.ru/teachers/elena-kryukova/','https://t.me/kriukova_lawyer'],'account_type':'personal'},
 {'id':'tg-speaker-ukvartira','url':'https://t.me/ukvartira','preview_url':'https://t.me/s/ukvartira','participant_ids':[],'source_urls':['https://t.me/s/ukvartira','https://www.meb-expo.ru/ru/events/'],'account_type':'organization'},
 {'id':'tg-org-spimex','url':'https://t.me/spimexofficial','preview_url':'https://t.me/s/spimexofficial','participant_ids':[],'source_urls':['https://t.me/s/spimexofficial','https://spimex.com'],'account_type':'organization'},
 {'id':'tg-org-roslesinforg','url':'https://t.me/roslesinforg_official','preview_url':'https://t.me/s/roslesinforg_official','participant_ids':[],'source_urls':['https://t.me/s/roslesinforg_official','https://roslesinforg.ru'],'account_type':'organization'},
 {'id':'tg-org-archdialog','url':'https://t.me/archdialog_friends','preview_url':'https://t.me/s/archdialog_friends','participant_ids':[],'source_urls':['https://t.me/s/archdialog_friends','https://archdialog.ru'],'account_type':'organization'}]
def main():
 result={'channels':[],'posts':[]}; checked=datetime.now(timezone.utc).isoformat()
 for channel in CHANNELS:
  row, posts=fetch({**channel,'status':'public_preview'},checked,ROOT/'docs/media/tg')
  result['channels'].append(row); result['posts'].extend(posts)
  print(channel['id'],row.get('status'),len(posts))
 target=ROOT/'data/raw/speaker_snapshot_raw.json';target.parent.mkdir(parents=True,exist_ok=True)
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print('saved',len(result['posts']),'posts')
if __name__=='__main__':main()
