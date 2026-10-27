/* Демо-вход: роль выбирается на странице, учётные данные не проверяются сервером. */
(() => {
  'use strict';

  const form = document.getElementById('loginForm');
  if (!form) return;

  const fieldLogin = document.getElementById('loginName');
  const fieldPassword = document.getElementById('loginPassword');
  const notice = document.getElementById('loginNotice');
  const toggle = form.querySelector('.access-password-toggle');

  // Ссылка /login?role=patient или /login?role=specialist заранее выбирает роль.
  // При переходе на обычный /login роль также можно выбрать вручную.
  const initialRole = new URLSearchParams(window.location.search).get('role');
  if (initialRole === 'patient' || initialRole === 'specialist') {
    const radio = form.querySelector(`input[name="role"][value="${initialRole}"]`);
    if (radio) radio.checked = true;
  }

  toggle.addEventListener('click', () => {
    const show = fieldPassword.type === 'password';
    fieldPassword.type = show ? 'text' : 'password';
    toggle.setAttribute('aria-pressed', String(show));
    toggle.setAttribute('aria-label', show ? 'Скрыть пароль' : 'Показать пароль');
  });

  form.addEventListener('submit', event => {
    event.preventDefault();
    notice.hidden = false;

    if (!fieldLogin.value.trim() || !fieldPassword.value) {
      notice.textContent = 'Введите логин и пароль.';
      (!fieldLogin.value.trim() ? fieldLogin : fieldPassword).focus();
      return;
    }

    const selectedRole = form.querySelector('input[name="role"]:checked')?.value;
    if (selectedRole === 'patient') {
      // Только навигация в прототипе, не настоящая авторизация.
      window.location.assign('/patient');
      return;
    }

    if (selectedRole === 'specialist') {
      window.location.assign('/specialist');
      return;
    }

    notice.textContent = 'Выберите роль, чтобы продолжить.';
  });
})();
