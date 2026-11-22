#!/usr/bin/env python3
"""Build the speaker social and post datasets from saved research artifacts."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/portal'; RAW=ROOT/'data/raw'
LOG=RAW/'speaker_search_log.json'; SNAP=RAW/'speaker_snapshot_raw.json'
SOCIALS={
'sp-fe94919984a7':('confirmed',[
 {'label':'Telegram · личный авторский канал','url':'https://t.me/averhovod','source_url':'https://alexeyverhovod.ru/','evidence':'Официальный сайт Алексея включает канал в список его официальных ресурсов; описание Telegram называет Алексея Верховода дизайнером интерьера.'},
 {'label':'Instagram · личный профиль','url':'https://www.instagram.com/alexeyverhovod/','source_url':'https://alexeyverhovod.ru/','evidence':'Ссылка Instagram дана на официальном сайте в списке личных официальных ресурсов.'},
 {'label':'ВКонтакте · группа автора','url':'https://vk.com/alexeyverhovodgroup','source_url':'https://alexeyverhovod.ru/','evidence':'Ссылка VK дана на официальном сайте Алексея в списке его официальных ресурсов.'},
 {'label':'YouTube · личный канал','url':'https://www.youtube.com/channel/UC4XrcTncK4fKthDIi8uzapA','source_url':'https://alexeyverhovod.ru/','evidence':'Сайт ссылается на YouTube как на официальный ресурс; канал подписан именем Алексея Верховода и описывает его дизайнерский блог.'}]),
'sp-50c76fbd153c':('confirmed',[{'label':'Telegram · GOLUBKOV Economics','url':'https://t.me/golubkov_economics','source_url':'https://golubkov-expert.ru/','evidence':'Официальный сайт Дмитрия Голубкова перечисляет Telegram в раскрытии информации; профиль канала описывает экономический блог его автора.'}]),
'sp-e17165f8b8e5':('confirmed',[{'label':'Telegram · авторский профессиональный блог','url':'https://t.me/Planirovka_pro','source_url':'https://planirovkaplus.ru/','evidence':'Официальный сайт называет Наталью Соло руководителем студии и автором блога «Планировка Плюс», ссылка ведёт прямо на этот Telegram-канал; профиль содержит её имя.'}]),
'sp-434ad79e9ae2':('confirmed',[{'label':'Telegram · профессиональный канал Елены Крюковой','url':'https://t.me/kriukova_lawyer','source_url':'https://t.me/kriukova_lawyer','evidence':'Публичное описание называет Елену Крюкову и её практику сопровождения дизайнеров; профиль Международной школы дизайна подтверждает специализацию.'}]),
'sp-221ad5957559':('organization_channel_only',[
 {'label':'Telegram · канал бюро Натальи Преображенской (организация)','url':'https://t.me/ukvartira','source_url':'https://t.me/s/ukvartira','evidence':'Название канала указывает бюро Натальи Преображенской; описание подписывает блог Натальей, в свежих постах она говорит от первого лица. Это канал бюро, не отдельный личный аккаунт.'},
 {'label':'ВКонтакте · сообщество бюро (организация)','url':'https://vk.com/ukvartira','source_url':'https://t.me/s/ukvartira','evidence':'Ссылка VK указана в описании Telegram-канала бюро.'}]),
'sp-5e5e9094f7f7':('organization_channel_only',[{'label':'Telegram · канал агентства АрхДиалог (организация)','url':'https://t.me/archdialog_friends','source_url':'https://t.me/s/archdialog_friends','evidence':'Описание канала содержит сайт archdialog.ru и представляет агентство; сообщения содержат обращения «На связи Светлана Котлукова», а профиль называет её администратором. Это канал организации, не личная страница.'}]),
'sp-578f8ffbbff5':('organization_channel_only',[{'label':'Telegram · Петербургская Биржа (организация)','url':'https://t.me/spimexofficial','source_url':'https://t.me/s/spimexofficial?after=3219&q=%23%D0%A6%D0%B5%D0%BD%D0%BE%D0%B2%D0%BE%D0%B5%D0%90%D0%B3%D0%B5%D0%BD%D1%82%D1%81%D1%82%D0%B2%D0%BE','evidence':'Пост официального канала биржи приводит прямую цитату Павла Попова и его должность; профиль канала указывает spimex.com. Это канал биржи, не личная страница.'}])}
DUP={'sp-fdc956891430':{'same_identity_as':'sp-7db6dc1c55b0','identity_note':'Повторная запись Венеры Али в people.json: то же имя и практически идентичная биография; отдельный аккаунт для дубля не заводился.'}}

def classify(cid,p):
 t=(p.get('text') or '').strip().lower()
 if cid=='tg-speaker-averhovod':
  if 'кош' in t: kind,tags='личный вопрос аудитории',['личное','обсуждение']
  elif 'телепередач' in t or 'смотри' in t: kind,tags='пост о телепередаче',['интерьер','телепередача']
  elif 'ламинат' in t: kind,tags='профессиональная дискуссия',['напольные покрытия','дизайн']
  else: kind,tags='разбор интерьерного проекта',['интерьер','проект']
 elif cid=='tg-speaker-golubkov-economics':
  if not t: kind,tags='медиа-пост без текста в превью',['медиа']
  elif 'золото' in t: kind,tags='комментарий о рынке золота',['финансы','рынки']
  elif 'книга' in t: kind,tags='авторская книга',['книга','экономика']
  elif 'форуме' in t or 'выступил' in t: kind,tags='профессиональное выступление',['выступление','экономика']
  else: kind,tags='экономический комментарий',['экономика','финансы']
 elif cid=='tg-speaker-planirovka-pro':
  if 'выставк' in t or 'неделя пройдет' in t: kind,tags='анонс профессиональных событий',['анонс','дизайн']
  elif 'помогите' in t or 'комментар' in t: kind,tags='задача для аудитории',['планировка','вовлечение']
  elif 'покупать' in t: kind,tags='разбор планировки перед покупкой',['планировка','покупка жилья']
  else: kind,tags='совет по планировке',['планировка','интерьер']
 elif cid=='tg-speaker-kryukova-lawyer':
  if 'суд' in t or 'иск' in t: kind,tags='разбор судебного дела',['право','судебная практика']
  elif 'выступать' in t or 'конференц' in t: kind,tags='анонс выступления',['анонс','право']
  elif 'договор' in t or 'техническое задание' in t: kind,tags='юридическая рекомендация',['договоры','дизайн']
  else: kind,tags='юридический разбор',['право','дизайн']
 else:
  if p.get('id')=='tgpost-ukvartira-15374': kind,tags='новость о финале дизайнерского конкурса',['дизайн','конкурс']
  else: kind,tags='показ проекта бюро',['интерьер','проект']
 contest=cid=='tg-speaker-ukvartira' and p.get('id')=='tgpost-ukvartira-15374'
 return {'content_type':kind,'tags':tags,'contest_announcement':contest,'giveaway_announcement':False,
  'giveaway_check':'Текст не содержит розыгрыша приза, условий участия или случайного выбора победителя.',
  'classification_basis':'Ручная смысловая разметка публичного текста.'}

def main():
 people=json.loads((DATA/'people.json').read_text(encoding='utf-8-sig'))
 log={x['person_id']:x for x in json.loads(LOG.read_text(encoding='utf-8'))}
 socials=[]
 for person in people:
  pid=person['id']; match=SOCIALS.get(pid); row=log.get(pid,{})
  errors=row.get('errors',[]); searches=row.get('searches',[]); fallback=row.get('fallback_searches',[]); residual=row.get('fallback_errors',[])
  item={'person_id':pid,'name':person['name'],'role':person.get('role',''),
   'status':match[0] if match else ('not_confirmed_serp_errors' if errors and row.get('final_search_status')=='serp_error_unresolved' else 'not_confirmed'),
   'links':match[1] if match else [],
   'search_summary':{'queries_attempted':2+(1 if errors else 0),'successful_queries':len(searches)+len(fallback),'errors':len(residual),'fallback_searches':len(fallback),'search_log':'data/raw/speaker_search_log.json','identity_source':(person.get('sources') or [{}])[0].get('url','')},
   'verification_note':'Профиль включён только при подтверждённой связке с официальным сайтом, профессиональным профилем или авторским описанием. Пустой links означает, что связь не удалось надёжно подтвердить.'}
  if pid in DUP:item.update(DUP[pid])
  if pid=='sp-5e5e9094f7f7':item['organization_channel_note']='Посты канала организации не включались в speaker_posts без явного авторства или интервью спикера.'
  socials.append(item)
 (DATA/'speaker_socials.json').write_text(json.dumps(socials,ensure_ascii=False,indent=2),encoding='utf-8')
 snap=json.loads(SNAP.read_text(encoding='utf-8')); channels={c['id']:c for c in snap['channels']}
 keep={'tg-speaker-averhovod','tg-speaker-golubkov-economics','tg-speaker-planirovka-pro','tg-speaker-kryukova-lawyer','tg-speaker-ukvartira'}
 author_posts={'tgpost-ukvartira-15348','tgpost-ukvartira-15359','tgpost-ukvartira-15361','tgpost-ukvartira-15374'}
 posts=[]
 for cid in sorted(keep):
  channel=channels[cid]; eligible=sorted([p for p in snap['posts'] if p['channel_id']==cid],key=lambda p:p.get('published_at') or '')
  if cid=='tg-speaker-ukvartira':eligible=[p for p in eligible if p.get('id') in author_posts]
  ids=channel.get('participant_ids',[]); attribution='Личный авторский канал'
  if cid=='tg-speaker-planirovka-pro':attribution='Авторский блог, связанный официальным сайтом с Натальей Соло'
  if cid=='tg-speaker-ukvartira':ids=['sp-221ad5957559'];attribution='Канал организации · авторство Натальи подтверждают описание канала и посты от первого лица'
  for p in eligible[-5:]:
   raw=(p.get('text') or '').strip(); summary=raw[:420].rstrip()+('…' if len(raw)>420 else '')
   item={'id':p['id'],'person_ids':ids,'channel_title':channel.get('title',''),'channel_url':channel['url'],'channel_attribution':attribution,
    'url':p['url'],'published_at':p.get('published_at'),'text':summary,'photos':p.get('photos',[]),'media_status':p.get('media_status'),
    'source_url':p.get('source_url'),'checked_at':p.get('checked_at'),'is_current_expo':p.get('id')=='tgpost-Planirovka_pro-3472',**classify(cid,p)}
   if item['contest_announcement']:item['contest_evidence']='Пост сообщает о финальной защите 13-го сезона «Битвы дизайнеров»: это новость о ходе конкурса, не розыгрыш и не случайный выбор победителя.'
   posts.append(item)
 posts.sort(key=lambda p:p.get('published_at') or '')
 (DATA/'speaker_posts.json').write_text(json.dumps(posts,ensure_ascii=False,indent=2),encoding='utf-8')
 print(f'profiles={len(socials)} linked={sum(bool(x["links"]) for x in socials)} posts={len(posts)} contests={sum(p["contest_announcement"] for p in posts)}')
if __name__=='__main__':main()
