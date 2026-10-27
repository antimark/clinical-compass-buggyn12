/* Кабинет врача: только синтетические данные и UI. API, хранение, клинические выводы отсутствуют. */
(() => {
  'use strict';

  const root = document.getElementById('doctorDashboard');
  if (!root) return;

  const patients = [
    { id:'PT-001', name:'Синтетический пациент А', priority:'urgent', state:'Тяжёлое состояние', trend:'Ухудшение', trendType:'negative', seen:'17.10 · 14:10', action:'Оценить сигнал', key:'signal-001' },
    { id:'PT-002', name:'Синтетический пациент Б', priority:'elevated', state:'Умеренное состояние', trend:'Нет изменений', trendType:'neutral', seen:'10.10 · 11:20', action:'Запросить анкету', key:'patient-002' },
    { id:'PT-003', name:'Синтетический пациент В', priority:'routine', state:'Лёгкое состояние', trend:'Улучшение', trendType:'positive', seen:'16.10 · 08:30', action:'Плановый визит', key:'patient-003' },
    { id:'PT-004', name:'Синтетический пациент Г', priority:'elevated', state:'Нет свежей оценки', trend:'Недостаточно данных', trendType:'neutral', seen:'09.10 · 09:40', action:'Уточнить контакт', key:'patient-004' }
  ];
  const requests = [
    { id:'REQ-001', name:'Синтетический пациент Б', patientId:'PT-002', priority:'elevated', subject:'Повторная консультация', date:'19.10 · 12:00', state:'Ожидает ответа', key:'request-001' },
    { id:'REQ-002', name:'Синтетический пациент В', patientId:'PT-003', priority:'routine', subject:'Плановый приём', date:'21.10 · 10:30', state:'Ожидает ответа', key:'request-002' },
    { id:'REQ-003', name:'Синтетический пациент А', patientId:'PT-001', priority:'urgent', subject:'Запрос на контакт', date:'18.10 · 16:00', state:'Ожидает ответа', key:'request-003' }
  ];
  const signals = [
    { id:'signal-001', name:'Синтетический пациент А', patientId:'PT-001', priority:'urgent', subject:'Критический сигнал по демо-правилу', seen:'17.10 · 14:10', status:'Требует просмотра' },
    { id:'signal-002', name:'Синтетический пациент Б', patientId:'PT-002', priority:'elevated', subject:'Изменение самочувствия в анкете', seen:'15.10 · 11:20', status:'Информационный' },
    { id:'signal-003', name:'Синтетический пациент Г', patientId:'PT-004', priority:'elevated', subject:'Нет свежих ответов', seen:'09.10 · 09:40', status:'Информационный' }
  ];
  const tasks = [
    ['PT-001', 'Ответить на ежедневную анкету'],
    ['PT-001', 'Подготовить вопросы к консультации'],
    ['PT-002', 'Заполнить анкету самочувствия'],
    ['PT-002', 'Подтвердить удобное время приёма'],
    ['PT-003', 'Завершить недельный опрос'],
    ['PT-004', 'Обновить контактные сведения'],
    ['PT-004', 'Заполнить пропущенную анкету']
  ];
  const priorityLabels = { urgent:'Срочно', elevated:'Повышенный', routine:'Плановый' };
  const priorityScores = { urgent:0, elevated:1, routine:2 };
  const descriptions = {
    'signal-001': 'По предварительно заданному демонстрационному правилу появилось событие, которое требуется просмотреть врачу. Система не делает клинических выводов.',
    'signal-002': 'Условный пример записи в журнале: изменение ответа на ежедневный опрос.',
    'signal-003': 'Условный пример записи в журнале: пропущено несколько дней наблюдения.',
    'patient-002': 'Можно запросить новую анкету у пациента. В прототипе реальное уведомление не отправляется.',
    'patient-003': 'Сведения о плановом визите пациента. Фактическая запись через прототип не создаётся.',
    'patient-004': 'Напоминание о необходимости уточнить данные контакта. В прототипе сообщения не отправляются.'
  };
  const el = id => document.getElementById(id);
  const tbody = el('doctorTableBody');
  const head = el('doctorTableHead');
  const search = el('doctorSearch');
  const filter = el('doctorFilter');
  const empty = el('doctorEmpty');
  const dialog = el('doctorDialog');
  const confirm = el('doctorDialogConfirm');
  const escape = value => String(value).replace(/[&<>"']/g, character => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[character]));
  let currentView = 'patients';
  let criticalViewed = false;
  const reviewedRequests = new Set();
  let dialogAction = null;

  function priorityTag(level) {
    return `<span class="doctor-priority ${level}">${priorityLabels[level]}</span>`;
  }
  function rowAction(key, label) {
    return `<button class="doctor-action doctor-row-action" type="button" data-open="${escape(key)}">${escape(label)} <span aria-hidden="true">→</span></button>`;
  }
  function patientCell(name,id) {
    return `<span class="doctor-patient-name">${escape(name)}</span><span class="doctor-patient-id">${escape(id)}</span>`;
  }
  function tableHeaders(labels) {
    head.innerHTML = `<tr>${labels.map(label => `<th scope="col">${escape(label)}</th>`).join('')}</tr>`;
  }
  function matchSearch(item) {
    const q = search.value.trim().toLocaleLowerCase('ru');
    return !q || [item.name,item.id,item.patientId,item.subject,item.state,item.status].filter(Boolean).join(' ').toLocaleLowerCase('ru').includes(q);
  }
  function matchPriority(item) { return filter.value === 'all' || item.priority === filter.value; }
  function sortPriority(a,b) { return priorityScores[a.priority] - priorityScores[b.priority]; }

  function render() {
    let records;
    if (currentView === 'patients') {
      records = patients.filter(item => matchPriority(item) && matchSearch(item)).sort(sortPriority);
      tableHeaders(['ПРИОРИТЕТ','ПАЦИЕНТ','СОСТОЯНИЕ','ДИНАМИКА','ПОСЛЕДНЕЕ НАБЛЮДЕНИЕ','ЧТО СДЕЛАТЬ']);
      tbody.innerHTML = records.map(item => `<tr><td>${priorityTag(item.priority)}</td><td>${patientCell(item.name,item.id)}</td><td>${escape(item.state)}</td><td><span class="doctor-trend ${item.trendType}">${escape(item.trend)}</span></td><td>${escape(item.seen)}</td><td>${rowAction(item.key,item.action)}</td></tr>`).join('');
    } else if (currentView === 'requests') {
      records = requests.filter(item => !reviewedRequests.has(item.id) && matchPriority(item) && matchSearch(item)).sort(sortPriority);
      tableHeaders(['ПРИОРИТЕТ','ПАЦИЕНТ','ТИП ЗАПРОСА','ЖЕЛАЕМОЕ ВРЕМЯ','СТАТУС','ДЕЙСТВИЕ']);
      tbody.innerHTML = records.map(item => `<tr><td>${priorityTag(item.priority)}</td><td>${patientCell(item.name,item.patientId)}</td><td>${escape(item.subject)}</td><td>${escape(item.date)}</td><td><span class="doctor-trend ${reviewedRequests.has(item.id) ? 'positive' : 'neutral'}">${reviewedRequests.has(item.id) ? 'Просмотрен' : escape(item.state)}</span></td><td>${rowAction(item.key, 'Рассмотреть')}</td></tr>`).join('');
    } else {
      records = signals.filter(item => matchPriority(item) && matchSearch(item)).sort(sortPriority);
      tableHeaders(['ПРИОРИТЕТ','ПАЦИЕНТ','СОБЫТИЕ','ОТМЕТКА ВРЕМЕНИ','СТАТУС','ДЕЙСТВИЕ']);
      tbody.innerHTML = records.map(item => `<tr><td>${priorityTag(item.priority)}</td><td>${patientCell(item.name,item.patientId)}</td><td>${escape(item.subject)}</td><td>${escape(item.seen)}</td><td><span class="doctor-trend ${item.id === 'signal-001' && criticalViewed ? 'positive' : 'neutral'}">${item.id === 'signal-001' && criticalViewed ? 'Просмотрен' : escape(item.status)}</span></td><td>${rowAction(item.id,'Открыть событие')}</td></tr>`).join('');
    }
    tbody.hidden = records.length === 0;
    empty.hidden = records.length > 0;
  }
  function setView(view, priority='all') {
    if (!['patients','requests','signals'].includes(view)) return;
    currentView = view;
    filter.value = priority;
    search.value = '';
    root.querySelectorAll('.doctor-tab').forEach(tab => {
      const active = tab.dataset.view === view;
      tab.classList.toggle('is-active',active);
      tab.setAttribute('aria-selected',String(active));
      tab.tabIndex = active ? 0 : -1;
      if (active) el('doctorPanel').setAttribute('aria-labelledby',tab.id);
    });
    el('doctorSortDescription').textContent = view === 'patients'
      ? 'По умолчанию: необходимость внимания ↓'
      : view === 'requests' ? 'Демо-заявки · без отправки' : 'Синтетические события · без клинических выводов';
    render();
  }
  function refreshCounters() {
    const openCount = requests.filter(item => !reviewedRequests.has(item.id)).length;
    el('doctorRequestsCount').textContent = String(openCount);
    el('doctorTabRequestsCount').textContent = String(openCount);
    el('doctorCriticalCount').textContent = criticalViewed ? '0' : '1';
    if (criticalViewed) {
      el('doctorAlert').classList.add('is-reviewed');
      el('doctorAlertLabel').textContent = 'СИГНАЛ ПРОСМОТРЕН · SYNTHETIC';
      el('doctorAlertTitle').textContent = 'Синтетический пациент А — отметка о просмотре';
      el('doctorAlertCaption').textContent = 'Сигнал просмотрен в рамках демо. Это не означает клинической оценки или закрытия риска.';
      el('doctorAlertOpen').textContent = 'Открыть событие →';
    }
  }
  function dialogOpen(title, description, pairs, action=null, actionLabel='') {
    el('doctorDialogTitle').textContent = title;
    el('doctorDialogDescription').textContent = description;
    const dl = document.createElement('dl');
    pairs.forEach(([name,value]) => {
      const holder = document.createElement('div');
      const dt = document.createElement('dt');
      const dd = document.createElement('dd');
      dt.textContent = name;
      dd.textContent = value;
      holder.append(dt,dd);
      dl.append(holder);
    });
    el('doctorDialogInfo').replaceChildren(dl);
    dialogAction = action;
    confirm.hidden = !action;
    if (action) confirm.textContent = actionLabel;
    if (!dialog.open) dialog.showModal();
  }
  function openByKey(key) {
    if (key.startsWith('request-')) {
      const request = requests.find(item => item.key === key);
      if (!request) return;
      const viewed = reviewedRequests.has(request.id);
      dialogOpen('Запрос на приём', `${request.name}. ${request.subject}. Действия доступны только в этой демонстрации.`,
        [['Запрос',request.id],['Пациент',request.patientId],['Желаемое время',request.date],['Состояние',viewed ? 'Просмотрен' : request.state]],
        viewed ? null : {type:'request',id:request.id}, 'Отметить просмотренным');
      return;
    }
    const signal = signals.find(item => item.id === key);
    if (signal) {
      const viewed = signal.id === 'signal-001' && criticalViewed;
      dialogOpen(signal.name, descriptions[key],
        [['Пациент',signal.patientId],['Сигнал',signal.subject],['Последнее наблюдение',signal.seen],['Приоритет',priorityLabels[signal.priority]]],
        signal.id === 'signal-001' && !viewed ? {type:'signal',id:key} : null,
        'Отметить просмотренным');
      return;
    }
    const patient = patients.find(item => item.key === key);
    if (patient) {
      dialogOpen(patient.name, descriptions[key],
        [['Пациент',patient.id],['Приоритет',priorityLabels[patient.priority]],['Состояние',patient.state],['Последнее наблюдение',patient.seen]]);
    }
  }
  function openTasks() {
    dialogOpen('Задания пациентам', 'Всего 7 условных заданий ожидают выполнения. Ни одно задание не отправлено реальным пациентам.',
      tasks.map(([id,task],i) => [`Задание ${i+1} · ${id}`,task]));
  }

  root.addEventListener('click', event => {
    const open = event.target.closest('[data-open]');
    if (open) { openByKey(open.dataset.open); return; }
    const nav = event.target.closest('[data-view]');
    if (!nav) return;
    const view = nav.dataset.view;
    if (view === 'tasks') openTasks();
    else setView(view,nav.dataset.status === 'new' ? 'urgent' : 'all');
  });
  // Стрелки переключают вкладки с клавиатуры, как принято для ARIA tabs.
  el('doctorDashboard').querySelector('.doctor-tabs').addEventListener('keydown', event => {
    if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault();
    const views = ['patients','requests','signals'];
    let i = views.indexOf(currentView);
    if (event.key === 'Home') i = 0;
    if (event.key === 'End') i = views.length-1;
    if (event.key === 'ArrowRight') i = (i+1)%views.length;
    if (event.key === 'ArrowLeft') i = (i+views.length-1)%views.length;
    setView(views[i]);
    root.querySelector(`.doctor-tab[data-view="${views[i]}"]`).focus();
  });
  search.addEventListener('input',render);
  filter.addEventListener('change',render);
  el('doctorSpecialty').addEventListener('change',event => {
    const labels = { psychiatrist:'Психиатр',therapist:'Терапевт',neurologist:'Невролог' };
    const role = labels[event.target.value] || 'Психиатр';
    el('doctorIntro').textContent = `Конфигурация «${role}» (демо). Приоритет не равен тяжести диагноза.`;
  });
  el('doctorDialogClose').addEventListener('click',() => dialog.close());
  el('doctorDialogCancel').addEventListener('click',() => dialog.close());
  confirm.addEventListener('click',() => {
    if (dialogAction?.type === 'signal') criticalViewed = true;
    if (dialogAction?.type === 'request') reviewedRequests.add(dialogAction.id);
    dialog.close();
    refreshCounters();
    render();
    dialogAction = null;
  });
  refreshCounters();
  setView('patients');
})();
