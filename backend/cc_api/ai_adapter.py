"""Provider-independent summary adapter contract, synthetic-only implementation.

No external model calls. No free text or identifiers enter deterministic_mock.
"""
from dataclasses import dataclass
from typing import Literal

Mode = Literal['disabled','deterministic_mock','approved_provider']

class AdapterDisabled(RuntimeError): pass
class AdapterUnavailable(RuntimeError): pass

@dataclass(frozen=True)
class SummaryRequest:
    observation_count: int
    source: str = 'synthetic_checkin_count'
    recipient_approved: bool = False

@dataclass(frozen=True)
class SummaryResponse:
    content: str
    mode: str
    source: str
    needs_human_review: bool = True
    explicitly_approved: bool = False


def redact_for_summary(payload: dict) -> dict:
    """Strict allowlist; denies text, names, IDs, medications, diagnosis and PHI."""
    value=payload.get('observation_count')
    if type(value) is not int or value<0 or value>100:
        raise ValueError('Count must be a bounded synthetic non-identifying integer')
    return {'observation_count':value}


def summarize(mode: Mode, request: SummaryRequest) -> SummaryResponse:
    if mode=='disabled':raise AdapterDisabled('AI summaries disabled')
    if mode=='approved_provider':
        raise AdapterUnavailable('Approved provider is intentionally not connected')
    if mode!='deterministic_mock':raise ValueError('Unknown AI adapter mode')
    minimal=redact_for_summary({'observation_count':request.observation_count})
    return SummaryResponse(
        content=f"Сводка синтетических наблюдений: {minimal['observation_count']} чек-инов. Не диагноз. Требуется проверка пациентом.",
        mode='deterministic_mock', source=request.source, needs_human_review=True,
        explicitly_approved=False)
