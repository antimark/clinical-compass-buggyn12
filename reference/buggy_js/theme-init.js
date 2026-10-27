/* Инициализация темы до отрисовки документа (предотвращает мигание). */
(() => {
  const key = 'designkit-theme';
  let saved = 'system';
  try { saved = localStorage.getItem(key) || 'system'; } catch {}
  const dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme = saved === 'dark' || (saved !== 'light' && dark) ? 'dark' : 'light';
})();
