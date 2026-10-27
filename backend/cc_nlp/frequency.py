"""Descriptive journal statistics, never diagnostic scores."""
from __future__ import annotations
from collections import defaultdict
from .errors import ValidationRejected
from .batch import BatchAnalysisRequest, BatchProcessingOutcome

def aggregate_document_mentions(request: BatchAnalysisRequest, outcomes: BatchProcessingOutcome,
                                *, scoped_projection: dict | None = None) -> dict:
    """Count at most one positive mention per (document_id, tag_code).

    Use only already-authorized sources; production enforces date/window and consent.
    Does not interpret absence of mention as absence of symptom.
    """
    if len(request.sources) != len(outcomes.source_results):
        raise ValidationRejected('frequency_batch_length_mismatch')
    eligible={s.document_id for s in request.sources if s.source_type=='journal_entry'}
    if not eligible:
        return {'eligible_documents':0,'tags':{},'interpretation':'mentions_in_analyzed_documents_not_symptom_prevalence'}
    if scoped_projection is not None:
        if scoped_projection.get('subject_ref')!=request.subject_ref:
            raise ValidationRejected('projection_subject_mismatch')
        # caller supplies only authorized clinician-specific projection
        authorized_source_docs={(s.source_id,s.document_id) for s in request.sources}
        if any((item['source_id'],item['document_id']) not in authorized_source_docs
               for item in scoped_projection.get('annotations', [])):
            raise ValidationRejected('projection_sources_mismatch')
        items=scoped_projection['annotations']
    else:
        items=[]
        for s,outcome in zip(request.sources,outcomes.source_results):
            for f in outcome.result['facts']:
                items.append({'document_id':s.document_id, 'source_id':s.source_id,
                    'tag_code':f['tag_code'],'assertion':f['assertion'],
                    'temporality':f['temporality'],'speaker':f['speaker'],
                    'factual_review':'unreviewed','display_priority':'normal'})
    grouped=defaultdict(set)
    relevant_grouped=defaultdict(set)
    for item in items:
        if (item['document_id'] not in eligible or item['assertion']!='asserted' or
            item['temporality']!='current' or item['speaker']!='patient' or
            item.get('factual_review')=='incorrect'):
            continue
        code=item['tag_code'];doc=item['document_id']
        grouped[code].add(doc)
        if item.get('display_priority')!='deprioritized':
            relevant_grouped[code].add(doc)
    return {'eligible_documents':len(eligible),'tags':{
       code:{'mentioned_documents':len(docs),
             'mention_fraction':round(len(docs)/len(eligible),6),
             'prominent_documents':len(relevant_grouped[code])}
       for code,docs in sorted(grouped.items())},
       'interpretation':'mentions_in_analyzed_documents_not_symptom_prevalence'}
