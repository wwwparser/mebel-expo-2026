document.querySelector('.theme')?.addEventListener('click',()=>{const r=document.documentElement; r.dataset.theme=r.dataset.theme==='dark'?'light':'dark';try{localStorage.setItem('expo-portal-theme',r.dataset.theme)}catch(e){}});
function searchable(value) {
 const letters = {'а':'a','в':'b','с':'c','е':'e','н':'h','к':'k','м':'m','р':'p','т':'t','х':'x'};
 return value.toLocaleLowerCase('ru').replace(/ё/g,'е').replace(/(\d{2})\s*([a-zавсенкмртх])\s*(\d{3})/g,
  (_, hall, letter, number) => hall + (letters[letter] || letter) + number);
}
document.querySelectorAll('.filter-scope').forEach(scope=>{
 const cards=[...scope.querySelectorAll('.filter-item')], search=scope.querySelector('input[type=search]'), selects=[...scope.querySelectorAll('select[data-field]')], more=scope.querySelector('.more'), count=scope.querySelector('.result-count'), empty=scope.querySelector('.empty');
 const step=Number(scope.dataset.limit)||24;let limit=step;
 const searchIndex = new Map(cards.map(card => [card, searchable(card.dataset.search || '')]));
 function update(reset=false){if(reset)limit=step;const q=searchable((search?.value||'').trim());let matches=0,shown=0;
 for(const card of cards){const ok=(!q||searchIndex.get(card).includes(q))&&selects.every(s=>!s.value||(card.dataset[s.dataset.field]||'').split(' | ').includes(s.value));const show=ok&&matches++<limit;card.hidden=!show;if(show)shown++;}
 if(count)count.textContent=`Найдено: ${matches}. Показано: ${shown}.`;if(more)more.hidden=matches<=limit;if(empty)empty.hidden=matches>0;}
 search?.addEventListener('input',()=>update(true));selects.forEach(s=>s.addEventListener('change',()=>update(true)));more?.addEventListener('click',()=>{limit+=step;update()});scope.querySelector('.reset')?.addEventListener('click',()=>{if(search)search.value='';selects.forEach(s=>s.value='');update(true)});update();
});
document.querySelectorAll('[data-telegram]').forEach(button=>button.addEventListener('click',()=>{const id=button.dataset.telegram;if(!/^[A-Za-z][A-Za-z0-9_]+\/\d+$/.test(id))return;const box=document.createElement('div'),script=document.createElement('script');script.src='https://telegram.org/js/telegram-widget.js?22';script.async=true;script.dataset.telegramPost=id;script.dataset.width='100%';box.appendChild(script);button.replaceWith(box)}));

const menuToggle = document.querySelector('.menu-toggle');
const siteMenu = document.querySelector('#site-menu');
if (menuToggle && siteMenu) {
 const mobile = matchMedia('(max-width:720px)');
 function setMenu(open) {
   siteMenu.hidden = mobile.matches && !open;
   menuToggle.hidden = !mobile.matches;
   menuToggle.setAttribute('aria-expanded', String(!siteMenu.hidden));
 }
 menuToggle.addEventListener('click', () => setMenu(siteMenu.hidden));
 mobile.addEventListener('change', () => setMenu(false));
 setMenu(false);
}
const calculator = document.querySelector('.calculator');
if (calculator) {
 const fields = [...calculator.querySelectorAll('input[data-cost]')];
 function calculate() {
   const out = calculator.querySelector('output');
   if (fields.some(input => !input.value.trim() || !input.validity.valid)) {
     out.textContent = 'Заполните все поля суммами от нуля.';
     return;
   }
   const [price,...costs] = fields.map(input => Number(input.value));
   const sum = price - costs.reduce((x,y) => x+y,0);
   out.textContent = 'Остаток с заказа — ' + sum.toLocaleString('ru-RU',{maximumFractionDigits:2}) + ' ₽';
 }
 calculator.addEventListener('input',calculate);
 calculate();
}

const factoryStream = document.querySelector('#factory-stream');
if (factoryStream) {
 const directory = new Map([...document.querySelectorAll('[data-factory]')].map(el => [el.dataset.factory, el.dataset]));
 const controls = factoryStream.querySelector('.filters');
 const query = controls.querySelector('input');
 const kind = document.querySelector('#factory-kind');
 const topic = document.querySelector('#factory-topic');
 const count = document.querySelector('#factory-count');
 const grid = document.querySelector('#factory-posts');
 const more = document.querySelector('#factory-more');
 const empty = document.querySelector('#factory-empty');
 const dateFormat = new Intl.DateTimeFormat('ru-RU', {dateStyle:'short',timeStyle:'short',timeZone:'Europe/Moscow'});
 let limit = 12;
 let loading;
 function node(tag, css, label) {
   const el = document.createElement(tag);
   if (css) el.className = css;
   if (label) el.textContent = label;
   return el;
 }
 function link(url, label, css) {
   const el = node('a',css,label);
   el.href = url;
   return el;
 }
 function card(post) {
   const brand = directory.get(post.handle);
   const article = node('article','post');
   const heading = node('div','post-who');
   heading.append(link('https://t.me/'+post.handle,brand.name),node('span','tag',brand.kind));
   article.append(heading);
   if (post.image) {
     const photo = node('img');
     photo.loading='lazy'; photo.alt='Иллюстрация из канала '+brand.name; photo.src=post.image;
     const cover = link(post.url,'','post-preview'); cover.append(photo); article.append(cover);
   }
   const body = node('div','post-content');
   if (post.quote) body.append(link('#attendance','Анонс поездки','topic'));
   body.append(node('p','',post.text || 'Фото или видео без подписи.'));
   const footer = node('div','post-footer');
   const when = node('time','',dateFormat.format(new Date(post.date)));
   when.dateTime=post.date; footer.append(when, link(post.url,'Пост в Telegram ↗'));
   body.append(footer); article.append(body);
   return article;
 }
 async function refresh() {
   try {
     if (!loading) loading = fetch(factoryStream.dataset.source).then(r => {
       if (!r.ok) throw new Error('feed');
       return r.json();
     });
     const all = await loading;
     const needle = searchable(query.value.trim());
     const matches = all.filter(p => {
       const c = directory.get(p.handle);
       return (!kind.value || c.kind===kind.value) && (!topic.value || (topic.value==='visit' ? p.quote : p.image))
         && (!needle || searchable([c.name,c.city,p.handle,p.text,p.quote || ''].join(' ')).includes(needle));
     });
     grid.replaceChildren(...matches.slice(0,limit).map(card));
     count.textContent='Найдено: '+matches.length+'. Показано: '+Math.min(limit,matches.length)+'.';
     more.hidden=matches.length<=limit; empty.hidden=matches.length>0;
   } catch {
     loading=null;
     count.textContent='Не удалось загрузить остальные сообщения. Проверьте соединение и повторите поиск.';
   }
 }
 controls.addEventListener('input',()=>{limit=12;refresh()});
 controls.querySelector('.reset').addEventListener('click',()=>{query.value='';kind.value='';topic.value='';limit=12;refresh()});
 more.addEventListener('click',()=>{limit+=12;refresh()});
}
