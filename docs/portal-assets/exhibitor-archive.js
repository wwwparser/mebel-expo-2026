const directory = document.querySelector('.archive-directory');
function showExhibitor() {
  const card = document.getElementById(location.hash.slice(1));
  if (!card?.classList.contains('archive-company')) return;
  if (card.hidden) {
    directory.querySelector('.reset').click();
    const more = directory.querySelector('.more');
    while (card.hidden && !more.hidden) more.click();
  }
  requestAnimationFrame(() => card.scrollIntoView());
}
window.addEventListener('hashchange', showExhibitor);
showExhibitor();
