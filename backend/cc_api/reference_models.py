"""Immutable imported references, auditable exact mappings and illustrative methods."""
from sqlalchemy import ForeignKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class DrugReference(Base):
    __tablename__ = 'sr_medication_references'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[str] = mapped_column(String(80), primary_key=True)
    reference_type: Mapped[str] = mapped_column(String(32))
    schema_version: Mapped[str] = mapped_column(String(64))
    review_status: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    inn: Mapped[str] = mapped_column(String(200))
    raw_original_json: Mapped[str] = mapped_column(Text)
    import_fingerprint: Mapped[str] = mapped_column(String(64))
    source_filename: Mapped[str] = mapped_column(String(200))
    manifest_filename: Mapped[str] = mapped_column(String(200))
    imported_at: Mapped[str] = mapped_column(String(40))
    structured_json: Mapped[str] = mapped_column(Text)


class ReferenceMatchRule(Base):
    __tablename__ = 'sr_reference_match_rules'
    __table_args__ = (ForeignKeyConstraint(['drug_reference_id', 'drug_reference_version'],
        ['sr_medication_references.id', 'sr_medication_references.version']),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[str] = mapped_column(String(32))
    icd10_code: Mapped[str] = mapped_column(String(32))
    drug_reference_id: Mapped[str] = mapped_column(String(80))
    drug_reference_version: Mapped[str] = mapped_column(String(80))
    match_basis: Mapped[str] = mapped_column(Text)
    source_field_paths_json: Mapped[str] = mapped_column(Text)
    curation_status: Mapped[str] = mapped_column(String(40))
    environment_scope: Mapped[str] = mapped_column(String(32))
    created_by: Mapped[str] = mapped_column(String(80))
    reviewed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    display_limitation: Mapped[str] = mapped_column(Text)


class TherapyReference(Base):
    __tablename__ = 'sr_therapy_references'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    review_status: Mapped[str] = mapped_column(String(40))
    content_json: Mapped[str] = mapped_column(Text)
