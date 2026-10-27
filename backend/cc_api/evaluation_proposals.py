"""Versioned experimental evaluation rules over any authorized intake, never orders.
Not clinically validated. Negation and limited lexical criteria are documented test
heuristics, not risk classification, diagnostic criteria or a prescribing policy.
"""
import re
from copy import deepcopy
from .clinical_intelligence_sources import digest
from .clinical_proposals import catalog_link, derive_fixture

VERSION='evaluation-propositions-2026-10-26.1'
RULE=dict(rule_id='evaluation-anxiety-lexical',version='1',ruleset_version=VERSION,
    status='experimental_needs_validation',effective_at='2026-10-26T00:00:00+00:00',expires_at='2027-10-26T00:00:00+00:00',
    source=dict(source_id='evaluation-lexical-policy',source_type='experimental_engineering_heuristic',source_version='1',
        provenance_uri='repo:backend/cc_api/evaluation_proposals.py',verification_status='unverified',verification_date=None,
        qualified_clinical_reviewer=None,reviewer_timestamp=None,author='Evaluation MVP engineering policy'),
    permitted_scope=['symptoms'],permitted_population='authorized de-identified or synthetic evaluation narratives',
    age_constraints='not assessed; no eligibility conclusion',contraindication_constraints='not assessed',
    inclusion='non-negated тревога/тревожность/беспокойство lexical evidence; explicit functional impairment may alter category independently of time',
    exclusion='negated/uncertain quoted trigger; no matching affirmative source span',
    missing_data_behavior='not_assessed, clinician questions; never interpret absent data as safe',
    validation_dataset_version='phase03b-unseen-evaluation-v1',approval_evidence=None,supersedes=None)


def derive_evaluation(source,config):
    from datetime import datetime,timezone
    dto=derive_fixture(source,config)
    dto.update(proposals=[],evidence=[],rule_policy_version=VERSION,clinical_rules_status='experimental_needs_validation',
        technical_status='implemented',clinical_review_status='experimental_needs_validation',
        label='Экспериментальное правило — требует клинической валидации',proposal_status='no_relevant_proposal')
    if not (datetime.fromisoformat(RULE['effective_at'])<=datetime.now(timezone.utc)<datetime.fromisoformat(RULE['expires_at'])):return dto
    matched=None
    for match in re.finditer(r'\b(?:тревог\w*|тревож\w*|беспокойств\w*)\b',source.text,re.I):
        sentence=re.split(r'[.!?\n;]',source.text[:match.start()])[-1].lower()
        if re.search(r'\b(?:не|нет|без|отрица\w*|возможно|если|пример|цитата)\b',sentence[-90:]):continue
        matched=match;break
    if not matched:return dto
    evidence_id=digest([source.source_version,source.grant_version,matched.span(),VERSION])
    dto['evidence']=[dict(id=evidence_id,source_type='intake',case_ref=source.case_id,source_version=source.source_version,
        recorded_at=source.created_at,scope='symptoms',start=matched.start(),end=matched.end(),quote=matched.group())]
    dto['proposal_status']='proposed'
    impaired=bool(re.search(r'\bне могу работать\b|\bмешает работать\b',source.text,re.I))
    urgency='urgent' if re.search(r'\bсегодня\b',source.text,re.I) else 'planned'
    base=dict(status='proposed_readonly',rule=deepcopy(RULE),rule_approved=False,label=dto['label'],evidence_refs=[evidence_id],
        source_version=source.source_version,limitations='Экспериментальная текстовая эвристика, не диагноз и не назначение; возможны ошибки отрицания и контекста.',
        missing_information=['duration','allergies','contraindications','current_medications','interactions','age','clinical_assessment'],
        assessments={key:'not_assessed' for key in ('allergies','contraindications','current_medications','interactions','age')},
        pending_questions=['Уточните длительность, контекст и влияние симптомов на жизнь.', 'Уточните возраст, аллергию, противопоказания и текущие препараты.'],
        clinical_approval_state='unreviewed',clinical_review_status='experimental_needs_validation',technical_status='implemented',catalog_links=[])
    specs=[dict(type='referral',title='Рассмотреть консультацию психиатра',target_specialty='psychiatrist',
        category='mandatory' if impaired else 'desired',urgency=urgency,critical=False,severity='not_assessed',priority_class='clinician_attention',
        rationale='Найдена явная текстовая отметка тревоги. Категория зависит от экспериментального признака влияния на работу; срок — отдельно от упоминания «сегодня». Врач принимает самостоятельное решение.'),
        dict(type='diagnostic_hypothesis',title='F41.1 — экспериментальная гипотеза, не диагноз',
            rationale='Текстовый признак для обсуждения с врачом; диагностические критерии и длительность не установлены.',catalog_links=[catalog_link('diagnosis','F41.1')]),
        dict(type='therapy_reference',title='КПТ — справочный материал к рассмотрению',
            rationale='Ссылка на метод из каталога, без назначения терапии.',catalog_links=[catalog_link('therapy','cbt')])]
    if re.search('авиандр',source.text,re.I):specs.append(dict(type='medicine_reference',title='Авиандр — справочное совпадение (демо)',
        rationale='Название упомянуто в обращении. Не доказаны показания, действующая регистрация, противопоказания и пригодность пациента.',
        catalog_links=[catalog_link('medicine','product:aviandr_maritupirdine_instruction')]))
    for spec in specs:
        item={**deepcopy(base),**spec};item['catalog_links']=[x for x in item['catalog_links'] if x]
        item['id']=digest([source.patient_id,source.case_id,source.source_version,source.grant_version,VERSION,digest(RULE),spec['type']])
        dto['proposals'].append(item)
    return dto
