"""Independent document extraction, in-memory batches; no storage, auth system or clinical rules.

Clinical decisions and doctor relevance never modify source extraction facts.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from .models import SourceRecord, ProcessingAuthorization, ProcessingOutcome
from .pipeline import analyze, _authorize
from .errors import ValidationRejected

AnalysisMode = Literal['single', 'batch', 'contextual']

@dataclass(frozen=True)
class BatchAnalysisRequest:
    request_id: str
    subject_ref: str
    sources: tuple[SourceRecord, ...]
    mode: AnalysisMode = 'batch'
    schema_version: str = '0.2.0'

@dataclass(frozen=True)
class BatchProcessingOutcome:
    request_id: str
    subject_ref: str
    mode: str
    source_results: tuple[ProcessingOutcome, ...]
    schema_version: str = '0.2.0'

    def as_dict(self) -> dict:
        return {
            'schema_version': self.schema_version,
            'request_id': self.request_id,
            'subject_ref': self.subject_ref,
            'analysis_mode': self.mode,
            'source_results': [
                {'result': item.result, 'error_code': item.error_code,
                 'model_id': item.model_id, 'prompt_version': item.prompt_version}
                for item in self.source_results
            ],
            'contextual_findings': [],  # Reserved: no unvalidated cross-record inference.
            'clinical_rules_applied': False,
        }

def analyze_batch(request: BatchAnalysisRequest, authorization: ProcessingAuthorization,
                  provider, *, catalog: dict, schema: dict) -> BatchProcessingOutcome:
    if (request.schema_version != '0.2.0' or request.mode not in {'single', 'batch', 'contextual'}
            or not request.request_id or not request.subject_ref or not 1 <= len(request.sources) <= 32):
        raise ValidationRejected('invalid_batch_metadata')
    if request.mode == 'single' and len(request.sources) != 1:
        raise ValidationRejected('single_requires_one_source')
    if sum(len(s.body_text) for s in request.sources) > 64000:
        raise ValidationRejected('batch_too_large')
    seen = set()
    # Authorize and validate the complete batch BEFORE any provider invocation.
    for s in request.sources:
        _authorize(s, authorization)
        if s.subject_ref != request.subject_ref or not s.document_id:
            raise ValidationRejected('source_subject_or_document_mismatch')
        if (s.source_id, s.source_revision) in seen:
            raise ValidationRejected('duplicate_batch_source')
        seen.add((s.source_id, s.source_revision))
    return BatchProcessingOutcome(request.request_id, request.subject_ref, request.mode,
        tuple(analyze(s, authorization, provider, catalog=catalog, schema=schema) for s in request.sources))
