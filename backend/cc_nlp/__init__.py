"""Standalone, synthetic-first text extractor; not a clinical decision system."""
__version__="0.2.0"
from .batch import BatchAnalysisRequest, BatchProcessingOutcome, analyze_batch
from .clinician import ClinicianTagReview, ClinicianTagPreference, ClinicianContext, project_for_clinician
from .frequency import aggregate_document_mentions
