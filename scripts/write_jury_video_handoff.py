"""Build the final handoff from measured video files and edit decisions."""
import json,csv,hashlib,datetime,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'deliverables/jury_screencast';PRIVATE=Path('/private/tmp/cc-jury-screencast-20261028')
metrics=json.load(open(OUT/'TECHNICAL_VALIDATION.json'));edl=json.load(open(OUT/'EDIT_DECISION_LIST.json'));privacy=json.load(open(OUT/'PRIVACY_FRAME_SCAN.json'));black=json.load(open(OUT/'BLACK_FREEZE_ANALYSIS.json'));playback=[json.loads(x) for x in (OUT/'PLAYBACK_RESULTS.jsonl').read_text().splitlines()]
display_policy=json.load(open(OUT/'INVITATION_DISPLAY_POLICY.json')) if (OUT/'INVITATION_DISPLAY_POLICY.json').exists() else {}
assert len(metrics)==9 and len(playback)>=9 and (display_policy.get('show_synthetic_login_password') or not privacy['findings']) and all(not x['black_intervals_over_0_7s'] for x in black)
assert not any(y['classification']=='REVIEW_REQUIRED' for x in black for y in x['static_intervals_over_15s'])
rows=list(csv.DictReader(open(OUT/'VIDEO_INDEX.csv')));inventory=[r for r in rows if r['scenario_id']=='route_inventory'];assert len(inventory)==102
captured=sum(r['verification_status']!='NOT_CAPTURED' for r in inventory)
def clock(x):
 m=int(x//60);return f'{m:02d}:{x-m*60:05.2f}'
def link(file):return '['+Path(file).name+']('+str(OUT/file)+')'
def table():
 return '\n'.join(['| Видео | Длительность | Размер |','|---|---:|---:|']+[f"| {link(r['file'])} | {clock(r['duration_seconds'])} | {r['bytes']/1048576:.2f} MiB |" for r in metrics])
labels={'00':'Гость / новый пациент и приглашение','01':'Существующий пациент','02':'Врач ↔ пациент, приём, Qwen, публикация','03':'Клиника: согласие на ФИО и отзыв','04':'Исследователь: A/B, методика и CSV','06':'Справочник и связи','05':'Экспериментальное и запланированное'}
groups=[]
for x in edl['Clinical_Compass_Jury_Full_Walkthrough_RU.mp4']:
 key=x['scene'][:2]
 if groups and groups[-1]['key']==key:groups[-1]['end']=x['output_end']
 else:groups.append({'key':key,'start':x['output_start'],'end':x['output_end']})
timeline='\n'.join(f"- {clock(g['start'])}–{clock(g['end'])}: {labels[g['key']]}" for g in groups)
limitations='''# Раскрытые ограничения

Это настоящий браузерный учебный прототип с синтетическими данными, не клинически валидированная медицинская система.

- Связанная основная история — ранее зарегистрированный пациент и его врач; новый пациент отдельно обозначен и реально зарегистрирован, сохранил PHQ-9 и дал согласие. Для демонстрации отзыва основной связанный пациент не лишался врача: отозвана связь нового пациента. Второй врач получил только симптомы через обычное адресное приглашение и явное согласие, без изменения серверных ролей.
- Новая полная отправка PHQ-9 и GAD-2 записана. PHQ-2/GAD-7 показаны как интерактивные формы и реальные ранее сохранённые результаты; это не новые полные прохождения этих двух форм. Все четыре формы проверялись ранее. Русские формы не утверждены; баллы — механическая сумма.
- Qwen3:4b-instruct: новые реальные локальные генерации, NLP24.409s, врачебный чат10.875s. Полное ожидание сохранено, ускорения и подмены ответа нет. NLP/маршрутизация экспериментальны; врач подтверждает и редактирует. Снимок NLP живёт5мин, сохранённые решения/документы — дольше. Копилот/лаборатория показаны с маркировкой экспериментального прототипа.
- Авиандр — вручную введённое учебное название, без подбора действующей дозы и без лечебной схемы. Подпись и публикация отдельные; отметка пациента — самоотчёт, не полноценный календарь пропусков. Календарь и расширенная валидация запланированы.
- Реальное правило наблюдений и оценка врача показаны; критические алерты не выдумывались, прогноз риска и экстренное мониторирование не заявлены.
- Исследователь: настоящий синтетический набор, A/B-запросы, наблюдаемые/пропуски/среднее, методика и CSV. График в этом потоке отсутствует и не подменялся картинкой. CSV содержит общий агрегат всего набора, фильтр A/B к экспорту не применяется. Малые группы защищены; результаты не клиническое доказательство. Отдельные study grants, cohort builder и импорт остаются частичными/ограниченными.
- ФИО показано только после отдельного name-only согласия и исчезает после отзыва. Роль клиники не получила медицинскую карту/личный дневник. Настоящие OIDC/MFA и профессиональное подключение в этом контуре не настроены; лицензии не выдавались за подтверждённые.
- 242 записи/77 препаратов подтверждены ранее собранными native/Docker тестами, не новым полным обходом в этой записи. В ролике — репрезентативные карточки, разделы источника и реальные связи. Доступность всех внешних сайтов не заявлена.
- Видео сняты в native8769. Docker8768 и Ollama11434 ответили200 перед записью; прежнее доказательство Docker/Qwen находится в reports/phase3/DOCKER_TEST_REPORT.md. Работающий мост к MacGPU не выдаётся за автономный CPU-sidecar: тот не принят. Новая Docker-регрессия ради видео не запускалась.
- Индекс содержит все102 исходных маршрута:49 имеют видео,53 NOT_CAPTURED. Это не приёмка1883 индивидуальных действий. Условные/закрытые/незаписанные пути не выданы за доказанные в видео.

Технические первые дубли не скрыты: неверный селектор secondary-кнопок прервал запись после успешного создания черновика и перед загрузкой фото; продолжение выполнено с тем же документом, создание включено отдельным фрагментом с пояснением. Открытие CSV в Chromium запускало повторное скачивание — фактический выгруженный файл открыт как текст отдельно. Ожидание завершения входа второго врача и клик по видимой дорожке темы исправлены только в скрипте. Неуспешные дубли и все исходные WebM сохранены приватно; они не считаются успешными тестами приложения.

В итоговых роликах нет озвучки/музыки; русские поясняющие титры намеренны. Есть обычные паузы для чтения и24-секундное реальное ожидание Qwen; это не потерянные кадры. По прямому запросу владельца прототипа показаны настоящие учебные QR, ссылки, коды приглашений, логины и пароли синтетических аккаунтов. Реквизиты входа даны в поясняющих титрах: штатные password-поля исходного интерфейса отрисованы точками. Это не добавленная функция раскрытия пароля. Показанные приглашения к настоящему времени приняты либо отозваны; их повторная активация не выполнялась. Системные ключи, cookies и приватные файлы никогда не были частью записи.
'''
(OUT/'DISCLOSED_LIMITATIONS.md').write_text(limitations)
report=f'''# Итог записи Clinical Compass — 2026-10-28

Готовы девять настоящих MP4: основной {clock(metrics[0]['duration_seconds'])}, короткий {clock(metrics[1]['duration_seconds'])}, семь глав. Все укладываются в жёсткие лимиты. Исходный Git HEAD080e9a850680f23c6be208b8d3b37fe00e2781e3, ветка codex/jury-ux-docker-20261027. Архитектура, backend, frontend, клинические правила и Docker-конфигурация не менялись; добавлены только инструменты записи/монтажа/проверки и документы. git diff080e9a8 -- backend frontend docker compose.yaml Dockerfile пуст. Полная регрессия не повторялась.

{table()}

Настоящий headless Chromium record_video_dir, отдельные контексты ролей, Flask/SQLite текущего частного synthetic workspace. 1440×900, deviceScale1/zoom100%; кадр1584×990 с сохранением пропорций в1920×1080, боковые поля и90px полоса русских титров вне приложения. Видимый оранжевый указатель — индикатор мыши записи. H.264, yuv420p,30fps, faststart; звук намеренно отсутствует. Статичные мокапы/старые PNG не использованы как видеоряд. ffmpeg7.1 через imageio-ffmpeg0.6 и ffprobe9.0 установлены только в /private/tmp/cc-video-tools; Conda не обновлялся. Перед записью свободно53GiB.

Реальные новые генерации: NLP24.408975s, чат10.874674s (inference_wall9660ms, jobwall9674ms). Модель qwen3:4b-instruct, digest0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0. Отдельный безопасный one-token warmup2.715s отдельно, не объявлен клиническим анализом. Все фактические ожидания Qwen сохранены в основном ролике, короткой версии NLP и главах; монтаж ответа не имитирует новую генерацию.

Каждая сцена сохранялась и fsync добавлялась в SCENES.jsonl и reports/phase3/raw/screencast-recording-20261028.jsonl. .agent/CHECKPOINT.md и EXECPLAN обновлялись после каждой сцены. Первые технические неудачи перечислены в DISCLOSED_LIMITATIONS, исходники сохранены, успешные API-действия повторно не создавались ради исправления селектора. Подпись/публикация, согласия, CSRF и разграничение доступа не обходились.

## Редакторская проверка титров

Титры проверены по фактическим действиям: короткое действие и польза для каждой роли; статусы «Работает в прототипе», «Экспериментально · решение за врачом», «Частично реализовано», «Планируется» разделены. Польза не выдаётся за клиническую валидацию. Полный список — CAPTION_REVIEW.csv. Сцены, длительности, AI-ответы и порядок действий не изменены. Учебные реквизиты раскрыты только по прямому запросу владельца прототипа.

## Основной ролик: фактический монтаж

{timeline}

VIDEO_INDEX.csv: {captured}/102 маршрута с реальным видео, {102-captured} явно NOT_CAPTURED. Дополнительные строки дают интервалы функций в главах, полном и коротком роликах. Таймкоды рассчитаны по сохранённым исходным меткам и измеренному EDIT_DECISION_LIST.json; округление до секунды, приблизительная граница сцены±0.2s. Ни видео, ни прежние102 маршрута не считаются проверкой всех1883 действий.

## Проверка итоговых файлов

- ffprobe: все9 —1920×1080/H.264/30fps/yuv420p, лимиты PASS.
- Полное декодирование всех9 ffmpeg без ошибок PASS; настоящее воспроизведение Chromium, начало>0.6s, seek в середину/конец, mediaError=null PASS.
- Начало/середина/конец всех9 —27 кадров просмотрены; контакты и оригинальные кадры сохранены приватно в {PRIVATE}/caption-revision-qa. Контроль: читаемые титры и окна, реальные результаты, нет debug-панелей/браузерной адресной строки/посторонних окон.
- Blackdetect:0 интервалов>0.7s. Freezedetect:3 интервала>15s, все совпадают с явно обозначенным реальным ожиданием Qwen в трёх версиях. Непояснённых длинных остановок не обнаружено.
- По явному запросу пользователя полностью восстановлены настоящие учебные QR/ссылки/коды. В проверенных кадрах QR действительно читается. Для пяти синтетических аккаунтов логин и пароль показаны в точных поясняющих титрах; исходные password-поля остаются штатно замаскированными браузером. Скрывающих областей монтажа больше нет. Первые результаты проверки замаскированной версии архивированы и не описывают текущие видео.

Машиночитаемые доказательства: TECHNICAL_VALIDATION.json, PLAYBACK_RESULTS.jsonl, BLACK_FREEZE_ANALYSIS.json, PRIVACY_FRAME_SCAN.json, AI_TIMINGS.jsonl, EDIT_DECISION_LIST.json. Точный порядок сцен и первые дубли — SCENES.jsonl. Все исходные WebM остаются в {PRIVATE}/raw; промежуточные MP4 в {PRIVATE}/sanitized-source-clips и previous-mp4/failed-attempts. Ничего из этого не загружать на Drive. Приватные учётные файлы/ключи/БД не скопированы в deliverables. Исторические отчёты и исходные архивы сохранены.

Google Drive не изменялся, Git push/merge master не выполнялись. Для пересъёмки нужны работающий8769, прежний private synthetic workspace, Chromium и инструменты /private/tmp/cc-video-tools. Сначала сохранить текущий пакет; выбрать только нужную функцию scripts/record_jury_screencast.py, не запускать полный аудит/сброс. При удалении временных инструментов восстановить imageio-ffmpeg/Pillow в отдельный target и ffprobe; не обновлять cc-m1. Для редактирования без новых действий достаточно сохранённых WebM/MP4 и EDIT_DECISION_LIST. Повторный монтаж не является новым успешным AI-запросом.
'''
(OUT/'RECORDING_REPORT.md').write_text(report)
# Replaceable storyboard points to actual final intervals; raw attempts remain append-only.
story=['# Сценарий и фактическая запись','', 'Предусловия: настоящий localhost8769, обычные раздельные сессии, синтетический пациент и его врач, действующие явные согласия; Qwen локален. Ожидание каждого действия — сохранённое сервером состояние или честное ограничение.','']
for file,edits in edl.items():
 story.append('## '+file)
 for e in edits:
  matches=[r for r in rows if r['video_file']==file and r['scenario_id']==e['scene']];role=matches[0]['role'] if matches else 'doctor';status=matches[0]['implementation_status'] if matches else 'LIVE_VERIFIED'
  story.append(f"- {clock(e['output_start'])}–{clock(e['output_end'])}: {e['scene']} / {role} / {status}. Реальные кадры; источник {e['source_start']:.2f}–{e['source_end']:.2f}s. Факт результата и маршруты: VIDEO_INDEX.csv; исходный дубль: SCENES.jsonl.")
story+=['','Точные действия, ожидания и результаты каждой исходной сцены сохранены в SCENES.jsonl.description/result/events. Исправления инструмента записи и неснятые возможности раскрыты в DISCLOSED_LIMITATIONS.md. Все новые поколения Qwen подтверждены AI_TIMINGS.jsonl; старые ответы не выдаются за новые.']
(OUT/'STORYBOARD.md').write_text('\n'.join(story)+'\n')
handoff=f'''# Clinical Compass — видео для жюри

Готово: настоящий интерфейс и действия всех четырёх ролей, новый и существующий синтетические пациенты. Основной **{clock(metrics[0]['duration_seconds'])}**, короткий **{clock(metrics[1]['duration_seconds'])}**. 1080p/H.264/30fps, русские титры, без звука. Папка: `{OUT}`.

{table()}

Основной ролик:

{timeline}

Все102 маршрута перечислены в [VIDEO_INDEX.csv]({OUT}/VIDEO_INDEX.csv):49 сняты,53 NOT_CAPTURED. Это не приёмка1883 действий. Детали и реальные времена Qwen: [отчёт]({OUT}/RECORDING_REPORT.md). Планируемое обозначено в финале полного ролика и главе05. По вашему запросу учебные QR, ссылки, коды, логины и пароли показаны открыто; значения паролей добавлены в титры, поскольку исходный интерфейс рисует их точками. Исследовательский график отсутствует; OIDC/MFA, часть исследований/импорта и автономный Docker-LLM ограничены. [Полные ограничения]({OUT}/DISCLOSED_LIMITATIONS.md).

Загрузка на Google Drive: создайте новую папку «Clinical Compass — Jury videos — 2026-10-28», загрузите эти9 MP4 и VIDEO_INDEX.csv/JURY_VIDEO_HANDOFF.md/DISCLOSED_LIMITATIONS.md. Дождитесь обработки и проверьте начало, перемотку и качество1080p полного/короткого видео. Выберите разрешения для нужных зрителей и проверьте доступ из другой сессии. Старый Drive-файл не заменять; ссылка на новую папку будет новой. ZIP — для передачи/скачивания, для онлайн-показа загрузите MP4 отдельно. Ничего не загружено автоматически, Git push не выполнялся.

Исходники для пересъёмки сохранены только локально: `{PRIVATE}/raw` и `sanitized-source-clips`; не загружайте приватный workspace, учётные файлы, первые дубли или сессии. Контрольные суммы: SHA256SUMS.txt; техническое воспроизведение всех9 PASS. Код приложения не менялся.
'''
(OUT/'JURY_VIDEO_HANDOFF.md').write_text(handoff)
# Preserve source clips privately, keeping the public handoff to exactly nine MP4s.
source=OUT/'source_clips';dest=PRIVATE/'sanitized-source-clips'
if source.exists():
 assert not dest.exists();shutil.move(str(source),str(dest))
manifest=json.load(open(OUT/'SOURCE_CLIP_MANIFEST.json'))
for x in manifest:x['file']=str(dest/Path(x['file']).name)
(OUT/'SOURCE_CLIP_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
(OUT/'VISUAL_REVIEW.json').write_text(json.dumps({'result':'PASS','reviewed_frames':27,'positions':['start','middle','end'],'videos':9,'method':'current-caption start/middle/end contact-sheet review plus full-size restored QR and credential samples','checks':['readable UI/captions','prototype invitations and synthetic credentials intentionally visible by explicit user request','no debug panels or foreign windows','real result states','intentional Qwen wait disclosed']},ensure_ascii=False,indent=2))
# Final checkpoint preserves previous release handoff and raw data.
section=f'''\n\n## Screencast COMPLETE — 2026-10-28
Nine MP4 ready: Full527.63s / Quick169.67s, seven chapters within caps. Native real Chromium/Flask/SQLite; fresh Qwen NLP24.409s + doctorchat10.875s. All9 full-decode/actual Chromium play+seek PASS;27 beginning/middle/end frames reviewed; black>0.7s0;3 static>15s intervals are explicitly labelled real Qwen waits;Prototype QR/link/code and synthetic login/password values visible by explicit user request; credentials are truthful timed captions, not a new app feature.49/102 routes captured,53 NOT_CAPTURED; no1883-action claim. Reports/videos: deliverables/jury_screencast/JURY_VIDEO_HANDOFF.md, VIDEO_INDEX.csv, RECORDING_REPORT.md, TECHNICAL_VALIDATION.json. All raw/first attempts private {PRIVATE}; no original raw deleted. App/backend/frontend/Docker source unchanged from080e9a8; only recording scripts/docs/checkpoints added. No push or Drive modification; subagents1/4. Existing native8769/Docker8768 and their durable state retained. Next action: open deliverables/jury_screencast/Clinical_Compass_Jury_Full_Walkthrough_RU.mp4 or Quick file; upload only after user action/authorization. Do not rerun finished recording/audit.\n'''
for name in ['.agent/CHECKPOINT.md','.agent/EXECPLAN_ACTIVE.md']:
 p=ROOT/name;p.write_text(p.read_text().split('\n\n## Screencast 2026-10-28')[0].split('\n\n## Screencast COMPLETE')[0]+section)
with (ROOT/'reports/phase3/PROGRESS.md').open('a') as f:f.write(section)
summary=ROOT/'docs/final_demo/JURY_VIDEO_HANDOFF.md';summary.write_text(handoff)
# Hash all final deliverables except the self-referential checksum file.
paths=sorted(p for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256SUMS.txt')
(OUT/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(OUT))+'\n' for p in paths))
archive=ROOT/'deliverables/Clinical_Compass_Jury_Videos_RU_20261028.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_STORED) as z:
 for p in sorted(OUT.rglob('*')):
  if p.is_file():z.write(p,'jury_screencast/'+str(p.relative_to(OUT)))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
(ROOT/'deliverables/Clinical_Compass_Jury_Videos_RU_20261028.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
print('HANDOFF PASS; nine MP4, index102, ZIP',archive.stat().st_size,flush=True)
