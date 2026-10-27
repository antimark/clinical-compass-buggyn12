/* Переключение темы через data-theme и сохранение пользовательского выбора. */
(() => {
  const button = document.getElementById('themeToggle');
  if (!button) return;
  button.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('designkit-theme', next); } catch {}
  });
})();
