# REST API: проектный контракт для Flask-фронтенда

**Статус:** [ПРОЕКТНОЕ ПРЕДЛОЖЕНИЕ]; маршруты и формы ответа **не утверждены реализованным кодом**. Документ — отправная точка согласования frontend/backend.

## Общие соглашения

- Базовый префикс `/api/v1`.
- JSON UTF-8; ошибки содержат `error.code`, `error.message`, `request_id`, **без скрытых значений**.
- Аутентификация: защищённая серверная сессия / HttpOnly cookie с CSRF (для Flask web); отдельное решение для мобильного клиента — открыто.
- Активный контекст организации выбирается явно и проверяется; нельзя доверять `organization_id` из тела запроса.
- Для коллекций: `limit`, `cursor`/`page`, разрешённые `sort`, `filter`; политика применяется до выдачи списка и подсчёта.
- `PATCH`: атомарная проверка **всех** полей, отклонять запрос целиком при недостаточном доступе.
- `DELETE`: в клинических разделах, как правило, контролируемая деактивация/архивирование, не обязательное физическое удаление.
- Idempotency keys для приглашений, принятия ключей, назначения лицензий и создания критических событий — [ПРОЕКТНОЕ ПРЕДЛОЖЕНИЕ].

## Таблица ресурсов

| Область | Эндпоинты (примерные) |
|---|---|
| Identity | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| Организации | `GET/POST /organizations`, `GET/PATCH /organizations/{org_id}` |
| Участники клиники | `GET /organizations/{org_id}/members`, `POST /organizations/{org_id}/members/{id}/deactivate` |
| Лицензии | `GET /organizations/{org_id}/licenses`, `PATCH /organizations/{org_id}/license-settings` |
| Приглашения | `POST /invitations`, `GET /invitations/{code}/preview`, `POST /invitations/redeem`, `POST /invitations/{id}/revoke` |
| Свои пациенты врача | `GET /doctors/me/patients`, `GET /doctors/me/patients/{patient_id}` |
| Свой профиль пациента | `GET /patients/me`, `GET /patients/me/records` |
| Клинические измерения | `GET /patients/{id}/observations`, `POST /patients/me/observations` |
| Динамические поля | `GET/POST /field-definitions`, `GET/POST /patients/{id}/field-values`, `PATCH /field-values/{value_id}` |
| Доступ | `GET /access/effective`, `POST /access/grants`, `POST /access/grants/{id}/revoke` |
| Шаблоны | `GET/POST /access-templates`, `POST /access-templates/{id}/versions` |
| Согласия | `GET/POST /consents`, `POST /consents/{id}/withdraw` |
| Врачи/пациенты | `POST /doctor-patient-links`, `GET /patients/me/doctors` |
| Оповещения | `GET /doctors/me/alerts`, `POST /alerts/{id}/acknowledge`, `POST /alerts/{id}/resolve` |
| Приёмы | `GET/POST /appointments`, `PATCH /appointments/{id}` |
| Исследования | `GET /research/datasets`, `GET /research/datasets/{id}/records` |
| Публикация stats | `POST /research/publication-jobs`, `GET /research/publication-jobs/{id}` |
| Аудит | `GET /admin/audit` только без чувствительных содержимых |

Это **ресурсная карта**, не приказ создавать все маршруты до первой интеграции. Для MVP сначала завершить сквозной сценарий регистрации, доступа и записи динамического значения.

## Пример: приглашение пациента

Запрос врача, в разрешённом контексте клиники:

```http
POST /api/v1/invitations
Content-Type: application/json

{
  "kind": "patient",
  "organization_id": "org_a",
  "doctor_id": "doc_a",
  "access_template_version_id": "tmpl_psych_v3",
  "expires_in_hours": 72
}
```

Ответ содержит статус и одноразовую ссылку/код **только при первичном выпуске**, а в БД хранится проверочное значение токена; наружу не отправлять прямые персональные данные.

## Пример: новая дефиниция поля

```json
{
  "field_key": "homework_completion",
  "display_name": "Выполнение задания",
  "data_type": "boolean",
  "category": "psychotherapy",
  "sensitivity_level": "clinical_sensitive",
  "validation": {"nullable": false}
}
```

Регистрация нового поля **не подразумевает** автоматическую выдачу разрешений старым пользователям или администратору клиники.

## Пример: запись динамического наблюдения

```http
POST /api/v1/patients/me/field-values
Content-Type: application/json

{
  "field_key": "homework_completion",
  "value": true,
  "recorded_at": "2026-10-17T12:00:00Z",
  "context": {"organization_id": "org_a"}
}
```

Ответ содержит `value_id`, `status`, `created_at`, `field_definition_version_id`. `patient_id` берётся из аутентифицированной сессии, не из произвольного тела запроса.

## Пример: чтение карточки разными врачами

Врач A имеет READ `mood_score` и `medication_history`; врач B — только `mood_score`. Оба вызывают `GET /doctors/me/patients/{patient_id}`. Результат **не обязан быть одинаковым**: поля фильтруются на сервере. Запрещённые поля должны быть опущены или отображены безопасными метаданными в согласованном контракте, без значения.

## Пример: запрос прав

```http
GET /api/v1/access/effective?patient_id=pat_a&organization_id=org_a
```

```json
{
  "patient_id": "pat_a",
  "organization_id": "org_a",
  "permissions": {
    "mood_score": ["READ"],
    "homework_completion": []
  },
  "evaluated_at": "2026-10-17T12:00:05Z"
}
```

Этот endpoint тоже не должен раскрывать существование полей/связей неавторизованному пользователю.

## Соглашения об ошибках

```json
{
  "error": {"code": "FORBIDDEN", "message": "Недостаточно прав для операции"},
  "request_id": "req_123"
}
```

Стандартизировать `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`. Для чужих объектов выбирать однородное поведение, не допускающее перечисления пациентов. Никогда не отдавать значения запрещённых полей в error details.

## Интеграционный контракт с фронтендом

Согласовать до кодирования интерфейса: формат авторизации, CSRF, раздельные активные роли, выбор клиники, контракт «поле отсутствует» vs «закрыто», пагинацию, дату/таймзону, фильтры по динамическим полям, ошибки, механизм подписки на алерты. Приложить OpenAPI и тестовый seed с **синтетическими** пользователями.
