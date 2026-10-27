"""Server-only, one-use OIDC authorization requests and revocable opaque sessions."""
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class OidcLoginAttempt(Base):
    __tablename__ = 'oidc_login_attempts'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    nonce_hash: Mapped[str] = mapped_column(String(64))
    verifier: Mapped[str] = mapped_column(Text)
    browser_hash: Mapped[str] = mapped_column(String(64))
    return_to: Mapped[str] = mapped_column(String(256))
    expires_at: Mapped[str] = mapped_column(String(40))
    consumed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))


class OidcBrowserSession(Base):
    __tablename__ = 'oidc_browser_sessions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    external_subject: Mapped[str] = mapped_column(String(255))
    issuer: Mapped[str] = mapped_column(String(512))
    auth_time: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str] = mapped_column(String(40))
    revoked_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    amr_json: Mapped[str] = mapped_column(Text)
    acr: Mapped[str | None] = mapped_column(String(255), nullable=True)
