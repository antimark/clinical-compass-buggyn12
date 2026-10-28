"""Offline editorial revision: real footage, explicit synthetic demo credentials only."""
import json,csv,subprocess,shutil,hashlib,datetime,os
from pathlib import Path
from record_jury_screencast import OUT,PRIVATE,ROOT,FF,caption,probe,duration,append
CLIPS=PRIVATE/'sanitized-source-clips';backup=PRIVATE/'before-jury-caption-review';backup.mkdir(exist_ok=True)
C={
'00a_invitation':('Врач приглашает пациента','Врач определяет категории доступа. Пациент сможет подтвердить связь по ссылке, QR-коду или коду.'),
'00b_guest_registration':('От первого опросника — к личной истории','PHQ-9 можно заполнить до регистрации. После создания аккаунта результат сохраняется в профиле.'),
'00c_invite_consent':('Пациент выбирает, какие данные открыть','Связь с врачом создаётся после проверки приглашения и явного подтверждения категорий доступа.'),
'00d_doctor_new_link':('Подтверждённая связь — в кабинете врача','Новый пациент появляется у врача после регистрации и согласия на передачу данных.'),
'00e_invitation_detail':('Приглашение удобно передать','Ссылка, QR-код и код — реальные учебные значения. Это приглашение отозвано после записи.'),
'01a_existing_today':('Сегодня: самочувствие и заметки','Оценка и комментарий сохраняются в личной истории и дополняют график динамики.'),
'01b_existing_questionnaires':('Опросник: ответы → результат → история','GAD-2: два ответа по 1 дают сумму 2. Пилотная форма, без клинической интерпретации.'),
'01c_plan_message_completed':('План лечения и связь с врачом','Пациент видит опубликованный план и может написать связанному специалисту.'),
'01d_profile_photo':('Личный профиль и фото','Синтетический аватар сохраняется в профиле и остаётся после перезагрузки.'),
'01e_access_revoke':('Контроль доступа — у пациента','Для врачей заданы разные категории. Пациент может отозвать конкретную связь.'),
'01f_doctor_access_denied':('Отзыв применяется на сервере','После отзыва новый запрос врача больше не открывает карточку пациента.'),
'01g_four_form_results':('Четыре формы — единая история','PHQ-9, PHQ-2, GAD-7 и GAD-2: доступны формы и сохранённые результаты. Версии пилотные.'),
'02a_doctor_overview':('Врач видит цельную картину','Карточка объединяет анамнез, динамику, результаты опросников и историю наблюдений.'),
'02b_visit_created_part':('Начало приёма: черновик','Врач сохраняет запись и уточняет её перед подписью.'),
'02b_visit_lifecycle':('Отредактировать → подписать → опубликовать','Врач управляет каждым этапом. Пациент получает доступ к записи после публикации.'),
'02c_plan_lifecycle':('План составляет врач','Учебная запись «Авиандр»: авторские поля, отдельные подпись и публикация. Без подбора дозы.'),
'02d_patient_receives':('План доступен пациенту','Опубликованное назначение появляется в кабинете. Пациент сохраняет отметку выполнения.'),
'02e_behavioral':('Поведенческий план — в той же системе','Врач задаёт содержание, периодичность и длительность. Документ пока остаётся черновиком.'),
'02f_patient_intake':('Обращение становится источником для разбора','Пациент описывает самочувствие и отдельно разрешает врачу использовать текст обращения.'),
'02g_qwen_nlp':('Clinical Intelligence: факты и основания','Локальный Qwen выделяет симптомы и точные цитаты. Предложения проверяет и подтверждает врач.'),
'02h_qwen_chat':('AI-чат с контекстом и источниками','Новый ответ локального Qwen на справочный вопрос врача. Реальное ожидание сохранено.'),
'02i_signals_message':('Сигнал → оценка врача → действие','Врач проверяет основание сигнала, сохраняет оценку и отвечает пациенту.'),
'02j_patient_answer':('Пациент получает ответ','Переписка связанной пары сохраняется на сервере и доступна после перезагрузки.'),
'02k_doctor_adherence':('Врач видит обратную связь','В опубликованном плане отображается сохранённая пациентом отметка выполнения.'),
'02l_patient_adverse':('Наблюдение можно передать врачу','Сообщение о возможном событии сохраняется для рассмотрения специалистом.'),
'02m_doctor_review_decision':('Клиническое решение принимает врач','Врач оценивает сообщение и сохраняет самостоятельное решение. Рядом доступен каталог специалистов.'),
'02n_dark_signal':('Сигналы: читаемо в любой теме','Тёмное оформление сохраняет основания и врачебную оценку. Сигнал не равен прогнозу клинического риска.'),
'03a_admin_hidden':('Администратор работает со своей клиникой','Сотрудники, записи и разрешённые сведения доступны в отдельном кабинете.'),
'03b_patient_name_optin':('Отдельное согласие на имя для клиники','Пациент сохраняет имя и явно разрешает передать выбранные поля администрации.'),
'03c_admin_name_visible':('Клиника получает только разрешённые данные','ФИО появляется после отдельного согласия. Медицинская карта не раскрывается.'),
'03d_patient_revoke_name':('Согласие можно отозвать','Пациент прекращает передачу ФИО администрации, сохраняя связь с врачом.'),
'03e_admin_revoked':('Изменение разрешений видно сразу','После повторного запроса ФИО снова скрыто: отзыв действует и на стороне сервера.'),
'03f_admin_partial':('Подключение клиники: следующий этап','Сотрудники доступны; профессиональное подключение, OIDC/MFA и лицензии требуют настройки.'),
'04_researcher':('Исследователь: от выборки к показателю','Учебные группы A/B, пропуски и среднее рассчитываются по синтетическому набору с явной методикой.'),
'04b_csv_readback':('Результат можно выгрузить','Настоящий CSV содержит общий синтетический агрегат всего набора, без строк отдельных пациентов.'),
'04c_research_partial':('Расширенные исследования','Часть наборов и конструктора когорт требует отдельных грантов доступа; учебный путь доступен.'),
'05a_experimental':('Экспериментальные инструменты рядом с практикой','Clinical Copilot и NLP помогают разбирать данные; решение, подпись и публикация остаются за врачом.'),
'05b_planned':('Развитие платформы','Далее: календарь приверженности, валидация AI и шкал, OIDC/MFA, исследования и автономный Docker-LLM.'),
'06_catalog_and_assessments':('Справочник для связного клинического поиска','242 записи, включая 77 препаратов: исходные разделы, показания, ограничения и ссылки.'),
'06b_catalog_links':('Материалы можно найти по названию','Поиск открывает карточку над списком результатов; информация представлена в разделах источника.'),
'06c_catalog_connected':('От препарата — к диагнозу, терапии и шкале','Реальные связи объединяют сертралин, диагноз, КПТ и GAD-7. Карточка не является назначением.')}
experimental={'02g_qwen_nlp','02h_qwen_chat','05a_experimental'};partial={'03f_admin_partial','04c_research_partial'}
def status(k):return 'Планируется' if k=='05b_planned' else 'Экспериментально · решение за врачом' if k in experimental else 'Частично реализовано' if k in partial else 'Работает в прототипе'
actors=json.load(open('/private/tmp/clinical-compass-jury-handoff-20261027/jury-actors.json'));actors['patient']=json.load(open('/private/tmp/clinical-compass-jury-handoff-20261027/jury-demo-patient.json'));state=json.load(open(PRIVATE/'state.json'))
credentials={
'00b_guest_registration':('Новый пациент: учебные реквизиты регистрации',state['new_email'],state['new_password'],30.21,42.2),
'01a_existing_today':('Пациент: учебные реквизиты входа',actors['patient']['email'],actors['patient']['password'],0,8),
'02a_doctor_overview':('Врач: учебные реквизиты входа',actors['doctor']['email'],actors['doctor']['password'],0,8),
'03a_admin_hidden':('Клиника: учебные реквизиты входа',actors['clinic_admin']['email'],actors['clinic_admin']['password'],0,8),
'04_researcher':('Исследователь: учебные реквизиты входа',actors['researcher']['email'],actors['researcher']['password'],0,8)}
# No credential values are written into source, reports or Git; they appear only in the authorized video captions.
policy=json.load(open(OUT/'INVITATION_DISPLAY_POLICY.json'));policy.update(show_synthetic_login_password=True,authorization='Explicit user request: show all prototype invitation values and synthetic login/passwords; improve jury captions truthfully',credential_presentation='Actual synthetic values in timed captions; native password inputs remain dots as in original UI')
(OUT/'INVITATION_DISPLAY_POLICY.json').write_text(json.dumps(policy,ensure_ascii=False,indent=2))
review=[]
for key,(title,desc) in C.items():
 path=CLIPS/(key+'.mp4')
 if not path.exists():continue
 old=backup/path.name
 if not old.exists():shutil.copy2(path,old)
 cap=PRIVATE/('review-'+key+'.png');caption(cap,title,desc,status(key))
 args=[FF,'-y','-v','error','-i',str(old),'-i',str(cap)];filters='[0:v][1:v]overlay=0:990[v]';output='[v]'
 if key in credentials:
  heading,email,password,start,end=credentials[key];credcap=PRIVATE/('review-credential-'+key+'.png');caption(credcap,heading,'Логин: '+email+'    Пароль: '+password,'Синтетический демоаккаунт');os.chmod(credcap,0o600);args+=['-i',str(credcap)];filters+=f';[v][2:v]overlay=0:990:enable=\'between(t,{start},{end})\'[auth]';output='[auth]'
 args+=['-filter_complex',filters,'-map',output,'-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(path)];subprocess.run(args,check=True)
 review.append({'scene':key,'title':title,'annotation':desc,'status':status(key),'credential_caption':key in credentials});print('CAPTION',key,flush=True)
with (OUT/'CAPTION_REVIEW.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(review[0]));w.writeheader();w.writerows(review)
edl=json.load(open(OUT/'EDIT_DECISION_LIST.json'));metrics=json.load(open(OUT/'TECHNICAL_VALIDATION.json'))
for file,edits in edl.items():
 target=OUT/file;saved=backup/Path(file).name
 if not saved.exists():shutil.copy2(target,saved)
 parts=[]
 for i,e in enumerate(edits):
  source=CLIPS/(e['scene']+'.mp4');start=e['source_start'];end=e['source_end']
  if start==0 and abs(duration(source)-end)<.02:part=source
  else:
   part=PRIVATE/'cuts'/(Path(file).stem+'-review-'+str(i)+'.mp4');subprocess.run([FF,'-y','-v','error','-ss',str(start),'-i',str(source),'-t',str(end-start),'-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(part)],check=True)
  parts.append(part)
 spec=PRIVATE/(Path(file).stem+'-review-concat.txt');spec.write_text('\n'.join("file '"+str(x)+"'" for x in parts));subprocess.run([FF,'-y','-v','error','-f','concat','-safe','0','-i',str(spec),'-c','copy','-movflags','+faststart',str(target)],check=True)
 data=probe(target);v=next(x for x in data['streams'] if x['codec_type']=='video');old=next(x for x in metrics if x['file']==file);seconds=float(data['format']['duration']);assert abs(seconds-old['duration_seconds'])<.05 and seconds<=old['limit_seconds'];assert v['codec_name']=='h264' and v['avg_frame_rate']=='30/1'
 decoded=subprocess.run([FF,'-v','error','-i',str(target),'-f','null','-'],capture_output=True,text=True);assert decoded.returncode==0 and not decoded.stderr
 old.update(bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),duration_seconds=seconds,revision='Jury benefit captions; authorized synthetic invitation and credential display')
 print('FINAL DECODE',file,flush=True)
(OUT/'TECHNICAL_VALIDATION.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
# Descriptions in the final index follow the edited annotations; historical SCENES stays append-only.
rows=list(csv.DictReader(open(OUT/'VIDEO_INDEX.csv')));fields=list(rows[0])
for r in rows:
 if r['scenario_id'] in C:r['action']=C[r['scenario_id']][1]
with (OUT/'VIDEO_INDEX.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
append(OUT/'VIDEO_REVISION_LOG.jsonl',{'revision':'Jury caption review and explicit synthetic credential display','videos':9,'result':'full decode PASS','new_app_actions':0,'new_ai_requests':0,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat()})
print('ALL CAPTIONS AND NINE VIDEOS READY',flush=True)
