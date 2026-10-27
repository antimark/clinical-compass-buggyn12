"""Additive Phase5 oidc_ stores; frozen schema and append-only review history."""
from alembic import op
import sqlalchemy as sa
revision = '0011_oidc_browser'
down_revision = '0010_admin_privacy'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('oidc_login_attempts',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('state_hash', sa.String(length=64), nullable=False),
        sa.Column('nonce_hash', sa.String(length=64), nullable=False),
        sa.Column('verifier', sa.Text(), nullable=False),
        sa.Column('browser_hash', sa.String(length=64), nullable=False),
        sa.Column('return_to', sa.String(length=256), nullable=False),
        sa.Column('expires_at', sa.String(length=40), nullable=False),
        sa.Column('consumed_at', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.String(length=40), nullable=False),
        sa.UniqueConstraint('state_hash'))
    op.create_table('oidc_browser_sessions',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('external_subject', sa.String(length=255), nullable=False),
        sa.Column('issuer', sa.String(length=512), nullable=False),
        sa.Column('auth_time', sa.String(length=40), nullable=False),
        sa.Column('expires_at', sa.String(length=40), nullable=False),
        sa.Column('revoked_at', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.String(length=40), nullable=False),
        sa.Column('amr_json', sa.Text(), nullable=False),
        sa.Column('acr', sa.String(length=255), nullable=True),
        sa.UniqueConstraint('token_hash'))


def downgrade():
    op.drop_table('oidc_browser_sessions')
    op.drop_table('oidc_login_attempts')
