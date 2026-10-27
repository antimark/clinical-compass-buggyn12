"""Add recipient-bound invited staff enrollment without clinical grants."""
from alembic import op
import sqlalchemy as sa
revision = '0014_staff_enrollment'
down_revision = '0013_clinical_review'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('se_staff_invitations',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('issuer_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('recipient_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('recipient_email_hash', sa.String(64), nullable=False),
        sa.Column('organization_id', sa.String(64), nullable=False),
        sa.Column('specialty', sa.String(50), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('expires_at', sa.String(40), nullable=False),
        sa.Column('accepted_at', sa.String(40), nullable=True),
        sa.Column('revoked_at', sa.String(40), nullable=True))

def downgrade():
    op.drop_table('se_staff_invitations')
