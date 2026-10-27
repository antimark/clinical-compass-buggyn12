# Clinical Compass: AI demo and acceptance notes (2026-10-27)

## Modes shown to evaluators

1. **Illustrative UI preview** in `/#/doctor/clinical-copilot`: expandable synthetic walkthrough of evidence-linked NLP tags, draft clinical note, referral considerations, and catalog links. Static example only. Never persisted; not AI inference.
2. **Working server-backed prototype**: choose an authorized patient in the same hub, choose an actual synthetic intake, click **Запустить анализ**, review tags with evidence and approve/reject individually, edit a draft note and explicitly save as unsigned draft, manually confirm a referral, and open a physician chat. Server enforces grants and checks revisions; these controls are not bypassed for jurors.
3. **Patient AI assistant** in `/#/patient/assistant`: add a private diary record, choose context, open a new chat and ask questions. Ollama/Qwen availability and CI flags govern generation. Private journal is not automatically shared with a physician.
4. **Questionnaires** in `/#/patient/tasks`: patient self-assigns PHQ-9, PHQ-2, GAD-7, GAD-2 in an explicitly labeled **evaluation-draft** mode, completes and reads stored sum/results. Clinically approved/usable form status is a separate publication gate.
5. **Catalog** in `/#/clinical-library`: all paginated medication records, related diagnostic/therapy pages and source instructions display stored nonempty source fields. No invented fields or diagnosis/medication decisions.

## Honest limits

- Illustrative preview does not demonstrate model accuracy, clinical validity or persistence. Production model clinical validation remains pending.
- AI server workflow requires a granted patient/intake, role permissions, CI feature flags and compatible local model. If these are absent, static preview is available independently.
- No autonomous diagnosis, prescription, approval, record publication or patient-to-physician private diary sharing.
- Native Flask dependencies and full browser/network E2E could not be executed in the packaging environment. Manual macOS integration and real API exercise required before claiming end-to-end success.

## Evaluator quick flow

Doctor: `/#/doctor/clinical-copilot` → expand example → choose authorized patient → select intake → analyze → review tags → edit/save note → confirm manual referral → open physician chat → visit catalog.

Patient: `/#/patient/tasks` → PHQ/GAD self-assessment → results; then `/#/patient/assistant` → create diary → choose entry → begin chat.

Testing note: these scenarios should be performed with synthetic test accounts and informed role/consent flows.
