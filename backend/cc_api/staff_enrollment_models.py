"""Issuer-authorized staff invitations; identity remains the existing User row."""
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class StaffEnrollmentInvitation(Base):
    __tablename__='se_staff_invitations'
    id: Mapped[str]=mapped_column(String(64),primary_key=True)
    token_hash: Mapped[str]=mapped_column(String(64),unique=True)
    issuer_id: Mapped[str]=mapped_column(ForeignKey('users.id'))
    recipient_id: Mapped[str]=mapped_column(ForeignKey('users.id'))
    recipient_email_hash: Mapped[str]=mapped_column(String(64))
    organization_id: Mapped[str]=mapped_column(String(64))
    specialty: Mapped[str]=mapped_column(String(50))
    created_at: Mapped[str]=mapped_column(String(40))
    expires_at: Mapped[str]=mapped_column(String(40))
    accepted_at: Mapped[str | None]=mapped_column(String(40),nullable=True)
    revoked_at: Mapped[str | None]=mapped_column(String(40),nullable=True)
