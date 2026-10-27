from __future__ import annotations
from time import monotonic
from .errors import AccessDenied, AnalysisError, ValidationRejected, ProviderUnavailable
from .catalog import tag_map
from .validator import validate_output, conservative_context_guard
from .models import SourceRecord, ProcessingAuthorization, ProcessingOutcome

ALLOWED_TYPES = {"journal_entry", "clinician_note", "message", "previsit_case", "transcript_segment"}
ALLOWED_VISIBILITY = {"private", "shared_with_care_team"}
ALLOWED_MISSING = {"sleep_pattern", "functional_impact", "symptom_duration", "symptom_frequency", "medication_details"}
MAX_TEXT_LEN = 12_000
SAFE_ERRORS = {"local_timeout", "local_inference_busy", "response_too_large", "model_unavailable", "local_http_failure", "local_transport_failure",
               "invalid_ollama_response", "invalid_model_json", "invalid_provider_payload",
               "evidence_quote_absent", "evidence_quote_ambiguous", "invalid_extraction_schema",
               "source_metadata_mismatch", "unknown_or_disabled_tag", "evidence_offset_mismatch",
               "duplicate_fact", "local_inference_failure"}



def _authorize(source: SourceRecord, authorization: ProcessingAuthorization) -> None:
    if not authorization.source_access_granted:
        raise AccessDenied("source_access_not_granted")
    if source.visibility not in ALLOWED_VISIBILITY:
        raise AccessDenied("unknown_source_visibility")
    if authorization.audience == "doctor" and source.visibility == "private":
        raise AccessDenied("private_source_not_accessible_to_doctor")
    if authorization.audience == "patient" and source.visibility == "private" and not authorization.private_analysis_opt_in:
        raise AccessDenied("private_processing_opt_in_required")


def _base_envelope(source: SourceRecord, provider_name: str, catalog: dict, facts: list, status: str, missing: list) -> dict:
    return {"schema_version": "1.0.0", "tag_catalog_version": catalog["catalog_version"],
            "source_id": source.source_id, "source_revision": source.source_revision,
            "source_type": source.source_type, "provider": provider_name,
            "analysis_status": status, "facts": facts, "missing_information": missing,
            "requires_human_review": True}


def analyze(source: SourceRecord, authorization: ProcessingAuthorization, provider, *, catalog: dict, schema: dict,
            prompt_version: str = "extract-v1") -> ProcessingOutcome:
    """Run a pure, stateless analysis. The caller is responsible for persistence and tenant authorization.

    Caller MUST already verify patient/doctor identity, clinical link, role, scopes and current sharing.
    Default-deny private data and filter patient-facing output to neutral visible topics only.
    """
    started = monotonic()
    stage = "authorization"
    _authorize(source, authorization)
    if prompt_version != "extract-v1":
        raise ValidationRejected("unsupported_prompt_version")
    if (not source.source_id or type(source.source_revision) is not int or source.source_revision < 1
            or source.source_type not in ALLOWED_TYPES or not isinstance(source.body_text, str)
            or len(source.body_text) > MAX_TEXT_LEN):
        raise ValidationRejected("invalid_source_metadata_or_length")
    if provider.name not in {"deterministic_mock", "local_llm"}:
        raise ValidationRejected("invalid_provider")
    if not source.body_text.strip():
        empty = _base_envelope(source, provider.name, catalog, [], "completed", [])
        validate_output(empty, source, catalog, schema)
        return ProcessingOutcome(empty, model_id=provider.model_id, prompt_version=prompt_version)
    try:
        stage = "generation"
        raw = provider.extract(source, catalog, prompt_version)
        if not isinstance(raw, dict) or set(raw) != {"facts", "missing_information"}:
            raise ValidationRejected("invalid_provider_payload")
        if not isinstance(raw["facts"], list) or not isinstance(raw["missing_information"], list):
            raise ValidationRejected("invalid_provider_payload")
        # Fail safe on invalid LLM assertions. Don't repair fabricated evidence.
        stage = "schema_validation"
        envelope = _base_envelope(source, provider.name, catalog, raw["facts"], "completed", raw["missing_information"])
        validate_output(envelope, source, catalog, schema)
        envelope = conservative_context_guard(envelope, source)
        validate_output(envelope, source, catalog, schema)
        # Non-medical information-gap placeholders only; clinician must review.
        envelope["missing_information"] = [m for m in envelope["missing_information"] if m in ALLOWED_MISSING]
        if authorization.audience == "patient":
            allowed = {t["code"] for t in catalog["tags"] if t["category"] == "topic" and t["patient_visible"]}
            envelope["facts"] = [f for f in envelope["facts"] if f["tag_code"] in allowed
                                 and f["assertion"] == "asserted" and f["speaker"] == "patient"]
            envelope["missing_information"] = []
        validate_output(envelope, source, catalog, schema)
        return ProcessingOutcome(envelope, model_id=provider.model_id, prompt_version=prompt_version,
                                 elapsed_ms=round((monotonic()-started)*1000))
    except (ProviderUnavailable, ValidationRejected, AnalysisError) as exc:
        # No raw text, prompts or model output in diagnostics.
        code = str(exc) if str(exc) in SAFE_ERRORS else "analysis_failure"
        safe = _base_envelope(source, provider.name, catalog, [], "requires_review", [])
        validate_output(safe, source, catalog, schema)
        return ProcessingOutcome(safe, error_code=code,
                                 model_id=provider.model_id, prompt_version=prompt_version,
                                 error_stage=("evidence_validation" if code.startswith("evidence_") else
                                              "json_parsing" if code in {"invalid_model_json", "invalid_ollama_response"} else
                                              "schema_validation" if code in {"invalid_provider_payload", "invalid_extraction_schema"} else stage),
                                 elapsed_ms=round((monotonic()-started)*1000))
    except Exception:
        safe = _base_envelope(source, provider.name, catalog, [], "requires_review", [])
        validate_output(safe, source, catalog, schema)
        return ProcessingOutcome(safe, error_code="internal_analysis_failure", model_id=provider.model_id,
                                 prompt_version=prompt_version, error_stage=stage, elapsed_ms=round((monotonic()-started)*1000))
