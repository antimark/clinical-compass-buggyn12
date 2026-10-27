"""Add synthetic-dev onboarding. No changes to existing clinical tables."""
from alembic import op
import sqlalchemy as sa
revision='0003_patient_onboarding'
down_revision='0002_p0_synthetic'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('ob_identities',
        sa.Column('user_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False, primary_key=True),
        sa.Column('email', sa.String(254), nullable=False, unique=True),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('email_provider', sa.String(80), nullable=False),
        sa.Column('email_status', sa.String(40), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
    )
    op.create_table('ob_journeys',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('owner_id', sa.String(64), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('doctor_id', sa.String(64), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('subject', sa.String(160), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('step', sa.String(32), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False),
    )
    op.create_table('ob_patient_onboarding',
        sa.Column('user_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False, primary_key=True),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('introduction_seen', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False),
    )
    op.create_table('ob_invitations',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('issuer_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('recipient_hash', sa.String(64), nullable=False),
        sa.Column('organization_id', sa.String(64), nullable=False),
        sa.Column('categories', sa.String(400), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('expires_at', sa.String(40), nullable=False),
        sa.Column('accepted_at', sa.String(40), nullable=True),
        sa.Column('revoked_at', sa.String(40), nullable=True),
        sa.Column('patient_user_id', sa.String(64), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_table('ob_consents',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('patient_user_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('doctor_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('invitation_id', sa.String(64), sa.ForeignKey('ob_invitations.id'), nullable=False, unique=True),
        sa.Column('categories', sa.String(400), nullable=False),
        sa.Column('version', sa.String(32), nullable=False),
        sa.Column('accepted_at', sa.String(40), nullable=False),
        sa.Column('revoked_at', sa.String(40), nullable=True),
    )
    op.create_table('ob_prepared_drafts',
        sa.Column('id', sa.String(64), nullable=False, primary_key=True),
        sa.Column('invitation_id', sa.String(64), sa.ForeignKey('ob_invitations.id'), nullable=False),
        sa.Column('clinician_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('state', sa.String(24), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('signed_at', sa.String(40), nullable=True),
        sa.Column('published_at', sa.String(40), nullable=True),
    )
    op.create_table('ob_staff_verifications',
        sa.Column('user_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False, primary_key=True),
        sa.Column('provider', sa.String(80), nullable=False),
        sa.Column('status', sa.String(40), nullable=False),
        sa.Column('verified_at', sa.String(40), nullable=False),
    )
    op.create_table('ob_auth_sessions',
        sa.Column('token_hash',sa.String(64),primary_key=True,nullable=False),
        sa.Column('user_id',sa.String(64),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('expires_at',sa.String(40),nullable=False),
        sa.Column('revoked_at',sa.String(40),nullable=True))
    op.create_index('ix_ob_journeys_owner_id','ob_journeys',['owner_id'])

def downgrade():
    op.drop_table('ob_auth_sessions')
    op.drop_table('ob_staff_verifications')
    op.drop_table('ob_prepared_drafts')
    op.drop_table('ob_consents')
    op.drop_table('ob_invitations')
    op.drop_table('ob_patient_onboarding')
    op.drop_table('ob_journeys')
    op.drop_table('ob_identities')
