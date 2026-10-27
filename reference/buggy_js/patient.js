/* Clinical Compass | Patient dashboard demo
   All content and state are mock data. No network requests, credentials or persistence. */
(() => {
  'use strict';
  const root = document.getElementById('patientDashboard');
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const dateId = (d) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const plusDays = (from, n) => new Date(from.getFullYear(), from.getMonth(), from.getDate() + n);
  const fmt = (d, opts) => new Intl.DateTimeFormat('ru-RU', opts).format(d);
  $('patientToday').textContent = fmt(today, {day:'numeric',month:'long',weekday:'long'});
  $('patientToday').dateTime = dateId(today);

  // Daily survey: the first prompt rotates based on the local calendar day.
  const dailyIndex = Math.floor((today - new Date(today.getFullYear(), 0, 1)) / 86400000);
  const rotating = [
    {question:'Как вы оцениваете своё самочувствие сегодня?',hint:'Выберите наиболее подходящий ответ.',labels:['Очень плохо','Плохо','Средне','Хорошо','Отлично']},
    {question:'Насколько комфортно вы чувствовали себя в течение дня?',hint:'Подумайте о своём общем состоянии.',labels:['Совсем нет','Скорее нет','Нейтрально','Скорее да','Полностью']},
    {question:'Сколько сил у вас было сегодня?',hint:'Оцените уровень энергии в течение дня.',labels:['Очень мало','Мало','Умеренно','Много','Очень много']},
    {question:'Как в целом прошло ваше утро?',hint:'Оцените самочувствие после пробуждения.',labels:['Очень тяжело','Тяжело','Обычно','Хорошо','Отлично']}
  ];
  const questions = [
    rotating[dailyIndex % rotating.length],
    {question:'Насколько спокойным был ваш день?',hint:'Оцените ощущения, а не отдельные события.',labels:['Совсем нет','Немного','Умеренно','В основном','Полностью']},
    {question:'Насколько хорошо вы спали прошлой ночью?',hint:'Опирайтесь на собственное ощущение качества сна.',labels:['Очень плохо','Плохо','Средне','Хорошо','Отлично']}
  ];
  const answers = [null,null,null];
  let surveyStep = 0;
  const responseOptions = $('surveyOptions');
  const surveyBack = $('surveyBack');
  const surveyNext = $('surveyNext');
  const renderSurvey = () => {
    const q = questions[surveyStep];
    $('surveyProgressLabel').textContent = `Вопрос ${surveyStep+1} из ${questions.length}`;
    $('surveyProgressPercent').textContent = `${Math.round((surveyStep+1)/questions.length*100)}%`;
    root.querySelector('.patient-survey-progress').dataset.progress = String(surveyStep+1);
    $('surveyQuestionLabel').textContent = q.question;
    $('surveyQuestionHint').textContent = q.hint;
    responseOptions.replaceChildren();
    q.labels.forEach((label, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'patient-response-option' + (answers[surveyStep] === index ? ' is-selected':'');
      button.setAttribute('aria-pressed', String(answers[surveyStep] === index));
      const number = document.createElement('span');
      number.className='patient-response-number';
      number.textContent = String(index+1);
      const caption = document.createElement('span');
      caption.className='patient-response-caption';
      caption.textContent=label;
      button.append(number, caption);
      button.addEventListener('click', () => {answers[surveyStep]=index;renderSurvey();});
      responseOptions.appendChild(button);
    });
    surveyBack.hidden = surveyStep === 0;
    surveyNext.disabled = answers[surveyStep] === null;
    surveyNext.innerHTML = surveyStep === questions.length-1 ? 'Завершить <span aria-hidden="true">✓</span>':'Продолжить <span aria-hidden="true">→</span>';
  };
  surveyNext.addEventListener('click', () => {
    if (answers[surveyStep] === null) return;
    if (surveyStep < questions.length - 1) {surveyStep++;renderSurvey();}
    else {$('surveyContent').hidden=true;$('surveyComplete').hidden=false;$('surveyTimeTag').textContent='Готово';}
  });
  surveyBack.addEventListener('click', () => {if (surveyStep > 0){surveyStep--;renderSurvey();}});
  $('surveyRestart').addEventListener('click', () => {answers.fill(null);surveyStep=0;$('surveyContent').hidden=false;$('surveyComplete').hidden=true;$('surveyTimeTag').textContent='~ 2 минуты';renderSurvey();});
  renderSurvey();

  // Sample trend data, deliberately unrelated to user responses.
  const weekly = [5.4,6.4,6.1,7.1,6.7,7.4,6.8];
  const monthly = [5.2,5.5,5.3,5.9,6.1,5.7,6.2,6.5,6.1,6.4,6.2,6.8,6.9,6.7,7.1,6.8,7.2,7,6.8,7.3,7,6.9,7.5,7.2,7.1,7.4,7.3,7,7.1,6.8];
  function drawChart(range) {
    const values = range===30 ? monthly : weekly;
    const points = values.map((v,i) => [i*650/(values.length-1),180-v*17]);
    const curve = points.map(([x,y],i)=>`${i===0?'M':'L'}${x.toFixed(2)} ${y.toFixed(2)}`).join(' ');
    $('patientChartLine').setAttribute('d', curve);
    $('patientChartFill').setAttribute('d', `${curve} L650 180 L0 180 Z`);
    const group=$('patientChartPoints'); group.replaceChildren();
    const markIndices = range===30 ? [0,6,12,18,24,29] : [0,1,2,3,4,5,6];
    markIndices.forEach(i => {
      const circ=document.createElementNS('http://www.w3.org/2000/svg','circle');
      circ.setAttribute('cx',points[i][0]);circ.setAttribute('cy',points[i][1]);circ.setAttribute('r','3.7');circ.setAttribute('class','patient-chart-point');group.appendChild(circ);
    });
    const positions = range===30 ? [29,22,15,8,0] : [6,5,4,3,2,1,0];
    const dates=$('patientChartDates'); dates.replaceChildren();
    for (const x of positions.reverse()) {
      const item=document.createElement('span'); item.textContent=fmt(plusDays(today,-x),{day:'numeric',month:'short'});dates.appendChild(item);
    }
    root.querySelectorAll('[data-range]').forEach(b => {const active=Number(b.dataset.range)===range;b.classList.toggle('is-active',active);b.setAttribute('aria-pressed',String(active));});
    root.querySelector('.patient-trend-summary strong').firstChild.textContent = range === 30 ? '6,6 ' : '6,8 ';
  }
  root.querySelectorAll('[data-range]').forEach(b=>b.addEventListener('click',()=>drawChart(Number(b.dataset.range))));
  drawChart(7);

  // Appointments: sample events + in-memory additions only.
  const appointments=[
    {date:plusDays(today,4), time:'11:30', title:'Повторная консультация', kind:'Врач-психиатр · онлайн'},
    {date:plusDays(today,12),time:'15:00',title:'Плановый приём',kind:'Врач-психиатр · очно'}
  ];
  const appointmentList=$('patientAppointmentsList');
  function renderAppointments() {
    appointments.sort((a,b) => a.date-b.date || a.time.localeCompare(b.time));
    appointmentList.replaceChildren();
    $('patientAppointmentsCount').textContent=String(appointments.length);
    appointments.forEach(item => {
      const row=document.createElement('div');row.className='patient-appointment-row';
      const badge=document.createElement('div');badge.className='patient-date-badge';
      const day=document.createElement('strong');day.textContent=String(item.date.getDate());
      const month=document.createElement('span');month.textContent=fmt(item.date,{month:'short'});
      badge.append(day,month);
      const info=document.createElement('div');info.className='patient-appointment-info';
      const title=document.createElement('strong');title.textContent=item.title;
      const sub=document.createElement('p');sub.textContent=item.kind;info.append(title,sub);
      const time=document.createElement('span');time.className='patient-time-badge';time.textContent=item.time;
      row.append(badge,info,time);appointmentList.append(row);
    });
  }
  renderAppointments();
  const dialog=$('patientAppointmentDialog');
  const form=$('patientAppointmentForm');
  const dateInput=form.elements.namedItem('appointmentDate');
  dateInput.min=dateId(today);
  dateInput.value=dateId(plusDays(today,7));
  $('patientAddAppointment').addEventListener('click',()=>dialog.showModal());
  $('patientModalClose').addEventListener('click',()=>dialog.close());
  $('patientModalCancel').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close();});
  form.addEventListener('submit',e=>{
    e.preventDefault();
    if (!form.reportValidity()) return;
    const candidate=new Date(`${dateInput.value}T12:00:00`);
    if (candidate < today) {dateInput.setCustomValidity('Выберите текущую или будущую дату.');dateInput.reportValidity();return;}
    dateInput.setCustomValidity('');
    appointments.push({date:candidate,time:form.elements.namedItem('appointmentTime').value,title:form.elements.namedItem('appointmentType').value,kind:'Демо-запись · не подтверждена'});
    renderAppointments();dialog.close();
  });
  dateInput.addEventListener('input',()=>dateInput.setCustomValidity(''));

  // Medication calendar: fictional plan; only today's toggles are editable.
  let displayedMonth=new Date(today.getFullYear(),today.getMonth(),1);
  let selectedDay=new Date(today);
  const todaysChecks=[false,false];
  const prescriptions=[{name:'Препарат А',details:'Утренний приём',time:'08:00'},{name:'Препарат Б',details:'Вечерний приём',time:'20:00'}];
  const calendar=$('patientCalendarGrid');
  function countForDay(date) {
    if (dateId(date)===dateId(today)) return todaysChecks.filter(Boolean).length;
    if (date > today) return 0;
    const pastDays=Math.round((today-date)/86400000);
    return pastDays % 5 === 0 ? 1:2;
  }
  function renderMeds() {
    const todaySelected=dateId(selectedDay)===dateId(today);
    const inPast=selectedDay < today;
    $('patientMedDayTitle').textContent=todaySelected?'Приём сегодня':`Приём ${fmt(selectedDay,{day:'numeric',month:'long'})}`;
    const total = countForDay(selectedDay);
    $('patientMedProgress').textContent = `${total} из 2`;
    const list=$('patientMedicationList');list.replaceChildren();
    prescriptions.forEach((item,i)=>{
      const checked=todaySelected ? todaysChecks[i] : inPast ? (total===2 || i===0 && total===1) : false;
      const row=document.createElement('div');row.className='patient-med-item'+(checked?' is-complete':'')+(!todaySelected?' is-disabled':'');
      const check=document.createElement('input');check.type='checkbox';check.className='patient-med-check';check.id=`patientMedCheck${i}`;check.checked=checked;check.disabled=!todaySelected;
      const label=document.createElement('label');label.htmlFor=check.id;
      const name=document.createElement('strong');name.textContent=item.name;
      const hint=document.createElement('span');hint.textContent=item.details;
      label.append(name,hint);
      const time=document.createElement('span');time.className='patient-med-time';time.textContent=item.time;
      row.append(check,label,time);list.append(row);
      check.addEventListener('change',()=>{todaysChecks[i]=check.checked;renderMeds();renderCalendar();});
    });
  }
  function renderCalendar() {
    $('patientCalendarMonth').textContent=fmt(displayedMonth,{month:'long',year:'numeric'});
    calendar.replaceChildren();
    const year=displayedMonth.getFullYear(),month=displayedMonth.getMonth();
    const weekOffset=(new Date(year,month,1).getDay()+6)%7;
    const daysInMonth=new Date(year,month+1,0).getDate();
    const cellCount=Math.ceil((weekOffset+daysInMonth)/7)*7;
    for(let i=0;i<cellCount;i++) {
      const date=new Date(year,month,1+i-weekOffset);
      const outside=date.getMonth()!==month;
      const selected=dateId(date)===dateId(selectedDay);
      const isToday=dateId(date)===dateId(today);
      const btn=document.createElement('button');btn.type='button';btn.textContent=String(date.getDate());
      btn.className=(outside?'is-outside ':'')+(selected?'is-selected ':'')+(isToday?'is-today ':'')+(date<=today && countForDay(date)>0?'has-taken ':'')+(date>today?'has-plan':'');
      btn.setAttribute('aria-label',fmt(date,{day:'numeric',month:'long',year:'numeric'}));
      if(selected)btn.setAttribute('aria-pressed','true');
      btn.addEventListener('click',()=>{selectedDay=date;if(outside)displayedMonth=new Date(date.getFullYear(),date.getMonth(),1);renderCalendar();renderMeds();});
      calendar.appendChild(btn);
    }
  }
  $('patientCalPrev').addEventListener('click',()=>{displayedMonth=new Date(displayedMonth.getFullYear(),displayedMonth.getMonth()-1,1);selectedDay=new Date(displayedMonth);renderCalendar();renderMeds();});
  $('patientCalNext').addEventListener('click',()=>{displayedMonth=new Date(displayedMonth.getFullYear(),displayedMonth.getMonth()+1,1);selectedDay=new Date(displayedMonth);renderCalendar();renderMeds();});
  renderCalendar();renderMeds();
})();
