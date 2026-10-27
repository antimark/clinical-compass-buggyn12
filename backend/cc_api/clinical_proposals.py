"""Versioned educational propositions. No inference, clinical writes or approval API.

Only exact, explicitly installed fixture events can match experimental rules.
This registry is deployment-versioned source, not an NLP output or a medical approval.
"""
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import quote
from .clinical_intelligence_sources import digest
from .clinical_catalog_v3 import get_item, VERSION as CATALOG_VERSION
from .clinical_proposal_fixtures import FIXTURES
from .verification import workspace_enabled, evaluation_enabled

VERSION = 'educational-proposals-2026-10-26.1'
LABEL = 'Демо / непроверенное правило'
SOURCE = {
    'source_id': 'phase03a-educational-script', 'source_type': 'synthetic_teaching_fixture',
    'source_version': '1', 'provenance_uri': 'repo:backend/cc_api/clinical_proposal_fixtures.py',
    'verification_status': 'unverified', 'verification_date': None,
    'qualified_clinical_reviewer': None, 'reviewer_timestamp': None,
    'author': 'Clinical Compass synthetic UX fixture',
}
REGISTRY = tuple({
    'rule_id': 'teaching-'+branch, 'version': '1', 'ruleset_version': VERSION,
    'effective_at': '2026-10-26T00:00:00+00:00', 'expires_at': '2027-10-26T00:00:00+00:00',
    'status': 'experimental_synthetic', 'source': SOURCE,
    'permitted_scope': ['symptoms'], 'permitted_population': 'explicit canonical synthetic fixture only',
    'age_constraints': 'not_assessed; no eligibility inferred',
    'contraindication_constraints': 'not_assessed; no eligibility inferred',
    'inclusion': 'exact patient, case and full source digest',
    'exclusion': 'any other patient/case/text, missing source or expired rule',
    'missing_data_behavior': 'unknown; clinician assessment required',
    'validation_dataset_version': 'phase03a-explicit-fixtures-v1',
    'approval_evidence': None, 'supersedes': None,
    'referral_category': 'desired' if branch == 'routine' else None,
    'urgency': 'planned' if branch == 'routine' else 'emergency',
    'critical': branch != 'routine',
    'severity': 'not_assessed' if branch == 'routine' else 'critical',
    'patient_ref': pid, 'case_ref': cid, 'text_digest': digest(text), 'branch': branch,
} for cid, uid, pid, text, branch in FIXTURES)


def enabled(config):
    return workspace_enabled(config) and config.get('CI_API_V1') is True and config.get('CI_PROPOSALS_V1') is True


def valid_rule(rule, now):
    """Fail closed. No partially populated or developer-promoted approved rules."""
    try:
        source = rule['source']
        return (rule['status'] == 'experimental_synthetic' and rule['ruleset_version'] == VERSION
            and rule['permitted_scope'] == ['symptoms']
            and rule['referral_category'] in ('mandatory', 'desired', None)
            and rule['urgency'] in ('emergency', 'urgent', 'planned')
            and type(rule['critical']) is bool
            and rule['severity'] in ('not_assessed', 'noncritical', 'critical')
            and source == SOURCE and all(source.get(k) for k in ('source_id','source_type','source_version','provenance_uri'))
            and datetime.fromisoformat(rule['effective_at']) <= now < datetime.fromisoformat(rule['expires_at']))
    except (KeyError, TypeError, ValueError):
        return False


def catalog_link(kind, ident):
    item = get_item(kind, ident)
    if not item:
        return None
    return dict(kind=kind, id=ident, title=item['title'],
        href='/#/clinical-library/'+kind+'/'+quote(ident, safe=''),
        source_version=item['source_version'], clinical_gate=item['clinical_gate'],
        verification=item['verification'])


def derive_fixture(selected, config):
    dto = dict(schema_version='cc-clinical-proposals-v1', patient_ref=selected.patient_id,
        case_ref=selected.case_id, source_version=selected.source_version,
        source_revision=selected.source_revision, grant_version=selected.grant_version,
        rule_policy_version=VERSION, catalog_version=CATALOG_VERSION,
        clinical_rules_status='experimental_synthetic', label=LABEL, proposals=[], evidence=[],
        clinical_action_enabled=False, referral_order_created=False, alert_delivery='not_implemented',
        limitation='Учебные предложения: не диагноз, не назначение, не направление и не доставленный сигнал.')
    if not enabled(config):
        return dto
    now = datetime.now(timezone.utc)
    for rule in REGISTRY:
        if not valid_rule(rule, now) or (rule['patient_ref'], rule['case_ref'], rule['text_digest']) != (selected.patient_id, selected.case_id, digest(selected.text)):
            continue
        trace = deepcopy({k:v for k,v in rule.items() if k not in ('patient_ref','case_ref','text_digest')})
        evidence_id = digest([selected.source_version, selected.grant_version, rule['rule_id']])
        dto['evidence'] = [dict(id=evidence_id, source_type='intake', case_ref=selected.case_id,
            source_version=selected.source_version, recorded_at=selected.created_at, scope='symptoms',
            start=0, end=len(selected.text), quote=selected.text)]
        common = dict(status='proposed_readonly', rule=trace, rule_approved=False, label=LABEL,
            evidence_refs=[evidence_id], source_version=selected.source_version,
            limitations='Только учебный сценарий; клиническая проверка отсутствует.',
            missing_information=['allergies','contraindications','current_medications','interactions','age','clinical_assessment'],
            assessments={key:'not_assessed' for key in ('allergies','contraindications','current_medications','interactions','age')},
            pending_questions=['Какова длительность симптомов и влияние на жизнь?',
                'Уточните возраст, аллергию, противопоказания и текущие препараты.'],
            clinical_approval_state='unreviewed', catalog_links=[])
        critical = rule['branch'] == 'alternate_critical'
        specs = [dict(type='safety_illustration', title='Альтернативная критическая ветвь (учебная)',
            category=None, urgency=rule['urgency'], critical=rule['critical'], severity=rule['severity'],
            target_specialty=None, priority_class='critical_illustration',
            rationale='Явный изолированный тестовый event; независим от направления и NLP. Детекция и доставка не реализованы.')] if critical else [
            dict(type='referral', title='Обсудить оценку психиатром (учебный пример)',
                target_specialty='psychiatrist', category=rule['referral_category'], urgency=rule['urgency'], critical=rule['critical'],
                severity=rule['severity'], priority_class='clinician_attention',
                rationale='Учебный сценарий первичного визита с длительной тревогой; категория и срок заданы сценарием, не медицинским правилом.'),
            dict(type='diagnostic_hypothesis', title='F41.1 — гипотеза для обсуждения, не диагноз',
                rationale='Иллюстрация гипотезы из сценария; требует дифференциальной оценки врача.',
                catalog_links=[catalog_link('diagnosis','F41.1')]),
            dict(type='therapy_reference', title='КПТ — справочный метод для обсуждения',
                rationale='Учебная ссылка на метод, без назначения терапии.', catalog_links=[catalog_link('therapy','cbt')]),
            dict(type='medicine_reference', title='Авиандр — справочная карточка, не подбор препарата',
                rationale='Справочное совпадение (демо): обсуждение карточки из сценария, пригодность пациента неизвестна. Текущая ГРЛС и показания не проверены.',
                catalog_links=[catalog_link('medicine','product:aviandr_maritupirdine_instruction')])]
        for spec in specs:
            item = {**deepcopy(common), **spec}
            item['catalog_links'] = [link for link in item['catalog_links'] if link]
            item['id'] = digest([selected.patient_id, selected.case_id, selected.source_version,
                selected.grant_version, VERSION, CATALOG_VERSION, digest(rule), item['type']])
            dto['proposals'].append(item)
    return dto


def derive(selected, config):
    if evaluation_enabled(config):
        from .evaluation_proposals import derive_evaluation
        return derive_evaluation(selected, config)
    return derive_fixture(selected, config)
