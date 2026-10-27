/* ===========================================================================
   REGISTRATION WIZARD — один интерфейс, три точки входа

   /register            -> выбор роли (нулевой шаг)
   /register/patient    -> сразу ключ пациента
   /register/specialist -> сразу ключ специалиста

   Поведение: выбор роли, переключение слайдов, валидация только текущего шага,
   переход назад и переключение видимости пароля. Никаких CSS-размеров или
   анимаций здесь нет: всё задаётся в static/css/register.css.

   ВАЖНО: прототип не отправляет персональные данные и не создаёт аккаунты.
   =========================================================================== */
(() => {
  'use strict';

  const form = document.getElementById('registrationForm');
  const page = document.querySelector('.registration-page');
  if (!form || !page) return;

  // 0 — роль, 1 — ключ, 2 — логин, 3 — пароль, 4 — данные, 5 — итог.
  const LAST_INPUT_STEP = 4;
  const FINISH_STEP = 5;
  const ROLE_NAMES = {
    patient: 'Пациент',
    specialist: 'Специалист',
  };

  const STEP_LABELS = {
    0: 'ШАГ 00 — НАЧАЛО',
    1: 'ШАГ 01 — ДОСТУП',
    2: 'ШАГ 02 — УЧЁТНАЯ ЗАПИСЬ',
    3: 'ШАГ 03 — БЕЗОПАСНОСТЬ',
    4: 'ШАГ 04 — ЛИЧНЫЕ ДАННЫЕ',
    5: 'ШАГ 04 — ГОТОВО',
  };

  const track = document.getElementById('slideTrack');
  const viewport = form.querySelector('.registration-viewport');
  const slides = Array.from(track.querySelectorAll('.registration-slide'));
  const backButton = document.getElementById('backStep');
  const nextButton = document.getElementById('nextStep');
  const nextLabel = nextButton.querySelector('span');
  const stepCount = document.getElementById('stepCount');
  const progress = document.getElementById('progressIndicator');
  const segments = Array.from(progress.querySelectorAll('.progress-segment'));
  const stepLabel = document.getElementById('registrationStepLabel');
  const roleContent = page.querySelectorAll('[data-role-only]');
  const initialRole = Object.hasOwn(ROLE_NAMES, page.dataset.initialRole)
    ? page.dataset.initialRole : null;

  let selectedRole = initialRole;
  let step = initialRole ? 1 : 0;

  function setFieldError(input, message = '') {
    const error = input.closest('.registration-field')?.querySelector('.field-error');
    if (error) error.textContent = message;
    if (message) input.setAttribute('aria-invalid', 'true');
    else input.removeAttribute('aria-invalid');
  }

  function clearErrors() {
    form.querySelectorAll('.registration-input').forEach(input => setFieldError(input));
  }

  // Показываем поля конкретной роли и отключаем поля другой роли,
  // чтобы они не участвовали в проверке или отправке формы в будущем.
  function applyRole(role) {
    selectedRole = role;
    page.dataset.role = role ?? '';
    roleContent.forEach(element => {
      const visible = element.dataset.roleOnly === role;
      element.hidden = !visible;
      element.querySelectorAll('.registration-input').forEach(input => {
        input.disabled = !visible;
      });
    });
  }

  function validateCurrentStep() {
    const inputs = slides[step].querySelectorAll('.registration-input:not(:disabled)');
    let firstInvalid = null;

    inputs.forEach(input => {
      const value = input.value.trim();
      let message = '';

      if (input.required && !value) {
        message = 'Заполните это поле.';
      } else if (value && input.minLength > 0 && value.length < input.minLength) {
        message = `Минимум ${input.minLength} символа(ов).`;
      } else if (value && input.type === 'email' && !input.checkValidity()) {
        message = 'Проверьте адрес электронной почты.';
      } else if (value && !input.checkValidity()) {
        message = 'Проверьте введённое значение.';
      }

      if (input.id === 'regRepeatPassword' && !message &&
          input.value !== document.getElementById('regPassword').value) {
        message = 'Пароли не совпадают.';
      }

      setFieldError(input, message);
      if (message && !firstInvalid) firstInvalid = input;
    });

    if (firstInvalid) firstInvalid.focus({ preventScroll: false });
    return firstInvalid === null;
  }

  // Меняем только состояние; transform и переходы остаются в CSS.
  function render({ focusTitle = false } = {}) {
    const finished = step === FINISH_STEP;
    const choosingRole = step === 0;
    track.dataset.step = String(step);
    form.classList.toggle('is-finished', finished);

    slides.forEach((slide, index) => {
      const active = index === step;
      slide.inert = !active;
      slide.setAttribute('aria-hidden', String(!active));
      if (active) slide.scrollTop = 0;
    });

    // Выбор роли не считается одним из четырёх этапов регистрации.
    segments.forEach((segment, index) => {
      segment.classList.toggle('is-active', !finished && index + 1 === step);
      segment.classList.toggle('is-complete', index + 1 < step);
    });

    const shownStep = finished ? LAST_INPUT_STEP : step;
    stepCount.innerHTML = `${String(shownStep).padStart(2, '0')} <span>/ 04</span>`;
    progress.setAttribute('aria-valuenow', String(shownStep));
    progress.setAttribute('aria-valuetext', choosingRole ? 'Выбор роли' :
      finished ? 'Все шаги пройдены' : `Шаг ${step} из ${LAST_INPUT_STEP}`);

    stepLabel.textContent = STEP_LABELS[step] ?? STEP_LABELS[0];

    backButton.hidden = choosingRole;
    nextButton.hidden = choosingRole;
    nextLabel.textContent = finished ? 'Начать заново'
      : step === LAST_INPUT_STEP ? 'Завершить' : 'Продолжить';

    if (focusTitle) slides[step].querySelector('.slide-title')?.focus({ preventScroll: true });
    viewport.scrollLeft = 0;
  }

  // Роль выбирается на этой же странице: при клике track уходит влево.
  form.querySelectorAll('[data-select-role]').forEach(button => {
    button.addEventListener('click', () => {
      const chosen = button.dataset.selectRole;
      if (!Object.hasOwn(ROLE_NAMES, chosen)) return;
      if (selectedRole && selectedRole !== chosen) {
        // Ключ и личные данные от другой роли не сохраняем при переключении.
        form.reset();
        clearErrors();
      }
      applyRole(chosen);
      step = 1;
      render({ focusTitle: true });
    });
  });

  function resetWizard() {
    form.reset();
    clearErrors();
    form.querySelectorAll('[data-toggle-password]').forEach(button => {
      const input = document.getElementById(button.dataset.togglePassword);
      input.type = 'password';
      button.setAttribute('aria-pressed', 'false');
      button.setAttribute('aria-label', input.id === 'regKey' ? 'Показать ключ' : 'Показать пароль');
    });
    // При прямом входе роль уже выбрана; при /register снова выбор роли.
    step = initialRole ? 1 : 0;
    applyRole(initialRole);
    render({ focusTitle: true });
  }

  form.addEventListener('submit', event => {
    event.preventDefault(); // Демонстрация: никогда не отправляем данные на сервер.
    if (step === FINISH_STEP) {
      resetWizard();
      return;
    }
    if (step === 0 || !selectedRole || !validateCurrentStep()) return;

    // После завершения последнего шага открываем демо-кабинет по роли.
    // Данные не сохраняются и аккаунт не создаётся.
    if (step === LAST_INPUT_STEP) {
      const dashboard = selectedRole === 'patient' ? '/patient' : '/specialist';
      window.location.assign(dashboard);
      return;
    }

    step += 1;
    render({ focusTitle: true });
  });

  backButton.addEventListener('click', () => {
    if (step === 0) return;
    clearErrors();
    step -= 1; // С шага ввода ключа возвращаемся к выбору роли.
    render({ focusTitle: true });
  });

  form.querySelectorAll('.registration-input').forEach(input => {
    input.addEventListener('input', () => setFieldError(input));
    input.addEventListener('change', () => setFieldError(input));
  });

  form.querySelectorAll('[data-toggle-password]').forEach(button => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.togglePassword);
      const wasHidden = input.type === 'password';
      input.type = wasHidden ? 'text' : 'password';
      button.setAttribute('aria-pressed', String(wasHidden));
      button.setAttribute('aria-label', wasHidden ? 'Скрыть значение'
        : input.id === 'regKey' ? 'Показать ключ' : 'Показать пароль');
      input.focus({ preventScroll: true });
    });
  });

  applyRole(initialRole);
  render();

  // Снимаем блокировку анимации после первой отрисовки.
  // При переходе с главной шаг 1 виден сразу, следующие переходы анимируются.
  if (track.classList.contains('is-initializing')) {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => track.classList.remove('is-initializing'));
    });
  }
})();
