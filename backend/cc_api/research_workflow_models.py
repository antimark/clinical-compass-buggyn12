"""Optional aggregate research versioning and global disclosure ledger."""
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class ResearchDefinitionRevision(Base):
    __tablename__ = 'rw_revisions'
    __table_args__ = (UniqueConstraint('definition_id', 'version', name='uq_rw_definition_version'),)
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    definition_id: Mapped[str] = mapped_column(ForeignKey('p0_dataset_definitions.id'))
    version: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[str] = mapped_column(String(40))


class ResearchStudyGrant(Base):
    __tablename__ = 'rw_study_grants'
    researcher_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    study_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)


class ResearchDisclosure(Base):
    __tablename__ = 'rw_disclosures'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    study_id: Mapped[str] = mapped_column(String(50), index=True)
    cohort: Mapped[str] = mapped_column(String(30))
    definition_id: Mapped[str] = mapped_column(ForeignKey('p0_dataset_definitions.id'))
    definition_version: Mapped[int] = mapped_column(Integer)
    query_fingerprint: Mapped[str] = mapped_column(String(64))
    membership_json: Mapped[str] = mapped_column(Text)
    values_fingerprint: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[str] = mapped_column(Text)
    min_cell: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))


class ResearchStudyLock(Base):
    __tablename__ = 'rw_study_locks'
    study_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)


@event.listens_for(ResearchDefinitionRevision, 'before_update')
@event.listens_for(ResearchDefinitionRevision, 'before_delete')
@event.listens_for(ResearchDisclosure, 'before_update')
@event.listens_for(ResearchDisclosure, 'before_delete')
def immutable_research_snapshot(*_args):
    raise ValueError('Published research history is append-only')
