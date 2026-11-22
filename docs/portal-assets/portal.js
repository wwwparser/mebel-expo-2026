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
