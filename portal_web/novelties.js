const noveltyStream = document.getElementById('novelties');
const noveltyRoute = document.getElementById('route');

function revealNovelty(fragment) {
  if (fragment === '#route' && noveltyRoute) noveltyRoute.open = true;
  const card = document.getElementById(fragment.slice(1));
  if (!card?.hidden || !noveltyStream.contains(card)) return;
  noveltyStream.querySelector('.reset').click();
  const more = noveltyStream.querySelector('.more');
  while (card.hidden && !more.hidden) more.click();
}

noveltyRoute?.querySelectorAll('a[href^="#"]').forEach(link => {
  link.addEventListener('click', () => revealNovelty(link.hash));
});
window.addEventListener('hashchange', () => revealNovelty(location.hash));
revealNovelty(location.hash);
