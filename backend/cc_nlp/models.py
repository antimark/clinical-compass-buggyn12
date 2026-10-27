from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

SourceType = Literal["journal_entry", "clinician_note", "message", "previsit_case", "transcript_segment"]
Visibility = Literal["private", "shared_with_care_team"]


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_revision: int
    source_type: SourceType
    body_text: str
    visibility: Visibility
    author_role: Literal["patient", "clinician", "other", "unknown"] = "patient"
    document_id: str | None = None
    field_id: str | None = None
    authored_at: str | None = None
    subject_ref: str | None = None


@dataclass(frozen=True)
class ProcessingAuthorization:
    """A trusted integration layer must establish entitlement before constructing this object.

    This is a second-line fail-closed check, NOT a substitute for tenant/link/consent validation.
    """
    audience: Literal["patient", "doctor"]
    source_access_granted: bool = False
    private_analysis_opt_in: bool = False


@dataclass(frozen=True)
class ProcessingOutcome:
    result: dict
    error_code: str | None = None
    model_id: str | None = None
    prompt_version: str = "extract-v1"
    clinical_rules_applied: bool = False
    error_stage: str | None = None
    elapsed_ms: int = 0
