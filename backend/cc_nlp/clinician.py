"""Scoped clinician-specific review/projection, without modifying extractor output.

This is an in-memory lab helper. Production backend must verify clinician identity,
org/patient relationship, consent, document sharing, and revoke cached projections.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from .errors import AccessDenied, ValidationRejected
from .batch import BatchAnalysisRequest, BatchProcessingOutcome
from .models import ProcessingAuthorization

FactualDecision = Literal['unreviewed','confirmed','incorrect','uncertain']
RelevanceDecision = Literal['undecided','relevant','not_relevant']
Reason = Literal['not_relevant_for_specialty','not_relevant_for_visit','incorrect_extraction',
                 'insufficient_evidence','other','none']

@dataclass(frozen=True)
class ClinicianTagReview:
    review_id: str
    clinician_ref: str
    subject_ref: str
    source_id: str
    source_revision: int
    tag_code: str
    evidence_start: int
    evidence_end: int
    factual_decision: FactualDecision = 'unreviewed'
    relevance_decision: RelevanceDecision = 'undecided'
    reason_code: Reason = 'none'

@dataclass(frozen=True)
class ClinicianTagPreference:
    clinician_ref: str
    subject_ref: str
    tag_code: str
    display_preference: Literal['pin','normal','deprioritize'] = 'normal'

@dataclass(frozen=True)
class ClinicianContext:
    clinician_ref: str
    subject_ref: str
    scope_verified: bool = False
    reviews: tuple[ClinicianTagReview,...] = ()
    preferences: tuple[ClinicianTagPreference,...] = ()


def project_for_clinician(batch: BatchAnalysisRequest, outcomes: BatchProcessingOutcome,
                          auth: ProcessingAuthorization, context: ClinicianContext,
                          catalog: dict) -> dict:
    if auth.audience != 'doctor' or not auth.source_access_granted or not context.scope_verified:
        raise AccessDenied('doctor_scope_not_verified')
    if (context.subject_ref != batch.subject_ref or context.subject_ref != outcomes.subject_ref
            or not context.clinician_ref or batch.request_id != outcomes.request_id):
        raise AccessDenied('clinician_subject_scope_mismatch')
    if len(batch.sources) != len(outcomes.source_results):
        raise ValidationRejected('source_results_length_mismatch')
    allowed_tag_map = {t['code']:t for t in catalog['tags']}
    reviews = {}
    preferences = {}
    for r in context.reviews:
        if r.clinician_ref != context.clinician_ref or r.subject_ref != context.subject_ref:
            raise AccessDenied('cross_clinician_review_forbidden')
        if (r.factual_decision not in {'unreviewed','confirmed','incorrect','uncertain'} or
            r.relevance_decision not in {'undecided','relevant','not_relevant'} or
            r.reason_code not in {'none','not_relevant_for_specialty','not_relevant_for_visit',
                                  'incorrect_extraction','insufficient_evidence','other'}):
            raise ValidationRejected('invalid_review_decision')
        if r.tag_code not in allowed_tag_map:
            raise ValidationRejected('unknown_review_tag')
        key=(r.source_id,r.source_revision,r.tag_code,r.evidence_start,r.evidence_end)
        if key in reviews:
            raise ValidationRejected('duplicate_review')
        reviews[key]=r
    for pref in context.preferences:
        if pref.clinician_ref != context.clinician_ref or pref.subject_ref != context.subject_ref:
            raise AccessDenied('cross_clinician_preference_forbidden')
        if pref.tag_code not in allowed_tag_map or pref.display_preference not in {'pin','normal','deprioritize'}:
            raise ValidationRejected('invalid_preference')
        if pref.tag_code in preferences:
            raise ValidationRejected('duplicate_tag_preference')
        preferences[pref.tag_code]=pref.display_preference
    # A supplied review must target a visible, current-revision evidence span.
    # Fail closed on stale/private/unrelated entries; this API is not an old-history importer.
    allowed_review_keys = {
        (src.source_id, src.source_revision, fact['tag_code'],
         fact['evidence']['start'], fact['evidence']['end'])
        for src, output in zip(batch.sources, outcomes.source_results)
        for fact in output.result['facts']
    }
    if not set(reviews).issubset(allowed_review_keys):
        raise AccessDenied('review_not_in_authorized_source_results')
    annotated = []
    for source, outcome in zip(batch.sources, outcomes.source_results):
        if (outcome.result['source_id'] != source.source_id or
                outcome.result['source_revision'] != source.source_revision):
            raise ValidationRejected('batch_result_source_mismatch')
        if source.visibility != 'shared_with_care_team' or source.subject_ref != context.subject_ref:
            raise AccessDenied('private_or_cross_patient_projection')
        for fact in outcome.result['facts']:
            e=fact['evidence']
            key=(source.source_id,source.source_revision,fact['tag_code'],e['start'],e['end'])
            review=reviews.get(key)
            category=allowed_tag_map[fact['tag_code']]['category']
            importance=preferences.get(fact['tag_code'],'normal')
            relevance=review.relevance_decision if review else 'undecided'
            # Safety never hidden/deprioritized by clinician preferences or 'not relevant'.
            priority = ('safety_unfiltered' if category == 'safety' else
                        'deprioritized' if relevance=='not_relevant' or importance=='deprioritize' else
                        'pinned' if importance=='pin' or relevance=='relevant' else 'normal')
            annotated.append({'source_id':source.source_id, 'source_revision':source.source_revision,
                'document_id':source.document_id, 'tag_code':fact['tag_code'],
                'category':category, 'assertion':fact['assertion'], 'temporality':fact['temporality'],
                'speaker':fact['speaker'], 'evidence':e,
                'factual_review':review.factual_decision if review else 'unreviewed',
                'relevance_review':relevance,
                'reason_code':review.reason_code if review else 'none',
                'display_priority':priority})
    return {'schema_version':'0.2.0','clinician_ref':context.clinician_ref,
            'subject_ref':context.subject_ref, 'annotations':annotated,
            'clinical_rules_applied':False}
