# Clinical Compass — DESIGN.md · v0.7 integrated synthetic prototype

## Source of truth / how to edit

Visual baseline: **Buggy-18.10-01.32** (`reference/buggy_templates`, `reference/buggy_js`, `frontend/dist/assets/buggy`). Extended v0.6 components are in `frontend/dist/assets/css/{tokens,themes,base,components,prototype}.css`. The primary running page is `frontend/dist/index.html`, with a separate real-API evaluation page `frontend/dist/api-lab.html`.

**Editing rule:** no inline CSS for new components; use CSS tokens, semantic components and state-driven modifiers. Existing v0.6 prototype uses inline presentation and hardcoded markup in places; refactor progressively before treating it as the final UI codebase. Do not claim complete component unification until that refactor is done.

## Layering

1. `tokens.css`: scale of typography, spacing, radii, elevation, colors; **design primitives**.
2. `themes.css`: light/dark semantic color aliases, contrast; no route-specific colors.
3. `base.css`: reset, fonts, focus, body.
4. `components.css`: button, form-field, select, textarea, card, badges, tabs, table, modal, pill, toast, avatar; each with sizes `sm/md/lg`, states default/hover/focus/disabled/error/success/loading.
5. `prototype.css`: legacy v0.6 page layout, to be decomposed into role-specific layout files.
6. `assets/buggy`: original css preserved as baseline reference, not imported wholesale into the runtime to avoid conflicting selectors.

## Component API (target)

- `Button({variant:'primary'|'secondary'|'danger', size, disabled, loading, onClick})`
- `Field({id,label,help,error,required,value,onChange})`
- `Select({id,label,options,value,onChange})`
- `TextArea({id,label,maxLength,rows,value})`
- `DataTable({columns,rows,sort,filters,visibleColumns})`
- `PatientSummary({patientRef,visibilityScope})` — sensitive fields come **only** from server-authorized DTOs.
- `QuestionnaireRunner({instrumentVersion,assignmentId})` — validated score comes from a controlled clinical instrument definition.
- `ChatThread({threadId,threadType,participants,permissions})` — public page never renders history.
- `CaseIntake({caseId,snapshot,canEdit})`; `ConsentMatrix({grantId,scopes,version})`.
- `Graph({points,source,missingData,access})` — never infer missing clinical datapoints.

The prototype's markup functions are *implementation references*, not complete reusable library exports. Implement these components as individually testable modules during the next UI refactor.

## Layout and information hierarchy

Global: header, left navigation on desktop, mobile navigation, contextual page title, actions, content, empty/error states. Patient home: check-in -> tasks -> next consultation -> alerts/messages -> recent trends. Doctor home: assigned alerts -> incoming cases -> appointments -> patient list. AI chat, doctor chat and doctor peer chat are independent views.

`frontend/dist/docs/screen_inventory_v06.csv` is the route inventory. All 86 routes are planned; NOT all routes are implemented as full screens in the running prototype. Never silently substitute identical static content for different medical workflows. Extend `route_catalog.js` as routes move to an implemented status.

## Clinical & accessibility constraints

- All sample data synthetic; visibly label synthetic/demo context.
- Check-in on 1–5 ordinal scale; do not conflate with validated instruments.
- Multiple clinician-confirmed diagnoses and patient-reported concerns are separate repeatable records.
- `PrevisitCase` contents are isolated from full medical charts; no automatic clinical link after a visit.
- At most one outbound message from patient until first doctor reply in new previsit case.
- Shared-patient disclosure only with pair-specific patient authorization.
- AI summary requires review and explicit selection/approval of recipient; unvalidated suggestions never become signed medical decisions.
- Audio/video visualization is planning/UI only; no live calls or facial/speech analysis.
- Keyboard visible focus, associated labels, contrast >= WCAG AA targets, reduced-motion support, form errors next to inputs.

## Design and medical review workflow

Designer: adjust `tokens/themes/components` first, verify 360/768/1280px. Product owner: reorder components via page composition config, never by modifying authorization. Clinician: validate screen hierarchy, field necessity, questionnaire/source metadata, clinical wording and escalation. Security reviewer: verify role tests and every field read. Freeze approved snapshots of screen inventory and run tests before merging.

## Acceptance design checklist

[ ] Themes and basic form elements consistent across roles; [ ] all prominent actions lead to valid meaningful state; [ ] error/empty/loading states; [ ] direct URL navigation; [ ] mobile and keyboard UX; [ ] role/permission dependent fields only from API; [ ] patient can change consent; [ ] clinical terminology validated; [ ] no real PHI in fixtures; [ ] styles centralized; [ ] automated route/visual regression after UI refactor.
