# Интеграция Clinical Compass v4

1. Храните JSON каталога как версионированный **read-only контент**, отдельно от медицинских записей и прав пациента.
2. Backend Flask: `GET /api/v1/clinical-library/instruments` и `.../:instrumentId` выдают метаданные. `GET .../diagnoses` и `.../:code` выдают справочник. ACL отделяют разрешённую врачебную справку от полей пациента.
3. Возвращайте пациентские вопросы только если `publication.clinical_release_approved && localization.release_approved && availability.usable_for_patient && rights.digital_clearance` и сервер подтвердил одобрение именно этой версии.
4. Запрещено выдавать draft translation и метаданные `licensed` как готовый бланк. Два вида числовых идентификаторов: `instrument_id + instrument_version` для инструмента и UUID записи ответа; код диагноза не выводится автоматически.
5. Нормализация ответов: `item_id`, `option_id`, `score` только после проверки соответствующего утверждённого ключа; `raw_answer`, timestamps, `language_version`, `license_version` сохраните с независимым аудитом.
6. Для нескольких шкал: храните `{scale_id, raw_score, normalized_score, calculation_version, validity_indicators, missingness}` отдельно; интерпретации `patient` и `clinician` различаются.
7. Лечащая команда получает только ответы, явно разрешённые пользователем и правами сервера; не полагайтесь на сокрытие компонентов фронтенда. Отдельный аудит доступа к диагнозам, чувствительным ответам и результатам.
8. При использовании МКБ-11 диагностического алгоритма выдавайте только информативный вывод; основные поля `diagnosis_code` и `coding_system` в рабочем релизе должны оставаться МКБ-10 по вашей спецификации. Не делайте ложного автоматического соответствия МКБ-11/МКБ-10.
9. Перед коммерческим релизом отдельно провести legal-review лицензии цифрового администрирования, открытия текста, оплаты исследования, русской версии и разрешения показывать результат пациенту; не переносить ключи PAI/SCID/MINI и др. из сторонних публикаций.
10. Допустимые состояния `draft`, `pending_clinician`, `approved`, `retired`. Расширение UI базовых PHQ-9/GAD-7 вместо дублирования существующего дневника.

## Бэкенд: предложенные сущности

- `InstrumentDefinition(id, version, language, legal_status, medical_status, json_digest, publication_status)`
- `InstrumentAssignment(id, patient_id, clinician_id, instrument_version, purpose, due_at, status)`
- `InstrumentResponse(id, assignment_id, answers_encrypted, submitted_at, visibility, revision)`
- `InstrumentScaleResult(id, response_id, scale_id, raw_score, normalized_score, interpretation_version, quality_flags)`
- `ClinicalDiagnosisReference(code, locale, version, criteria, clinician_description, patient_description)`
- `PatientDiagnosis(id, patient_id, code, clinician_id, confirmed_at, evidence_refs, status)` — **создаёт только уполномоченный врач**, не код опросника.

Контракты предложены, в текущий Flask-код ещё не вносились.
