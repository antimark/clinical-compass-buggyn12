"""Versioned technical questionnaires and own patient observations; additive only."""
from alembic import op
import sqlalchemy as sa

revision = '0004_patient_experience'
down_revision = '0003_patient_onboarding'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('px_observations',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('patient_id', sa.String(64), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('metric_key', sa.String(64), nullable=False),
        sa.Column('unit', sa.String(32), nullable=False),
        sa.Column('scale_version', sa.String(64), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('observed_at', sa.String(40), nullable=False),
        sa.Column('recorded_at', sa.String(40), nullable=False),
        sa.Column('source', sa.String(40), nullable=False),
        sa.Column('event_key', sa.String(80), nullable=False),
        sa.UniqueConstraint('patient_id', 'event_key', name='uq_px_observation_event'))
    op.create_index('ix_px_observations_patient_id', 'px_observations', ['patient_id'])
    op.create_table('px_questionnaire_definitions',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('version', sa.String(32), nullable=False),
        sa.Column('language', sa.String(8), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('definition_json', sa.Text(), nullable=False))
    op.create_table('px_questionnaire_assignments',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('patient_id', sa.String(64), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('clinician_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('definition_id', sa.String(64), sa.ForeignKey('px_questionnaire_definitions.id'), nullable=False),
        sa.Column('definition_version', sa.String(32), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False))
    op.create_index('ix_px_questionnaire_assignments_patient_id', 'px_questionnaire_assignments', ['patient_id'])
    op.create_table('px_questionnaire_drafts',
        sa.Column('assignment_id', sa.String(64), sa.ForeignKey('px_questionnaire_assignments.id'), primary_key=True, nullable=False),
        sa.Column('answers_json', sa.Text(), nullable=False),
        sa.Column('last_page', sa.Integer(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False))
    op.create_table('px_questionnaire_submissions',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('assignment_id', sa.String(64), sa.ForeignKey('px_questionnaire_assignments.id'), nullable=False, unique=True),
        sa.Column('definition_id', sa.String(64), sa.ForeignKey('px_questionnaire_definitions.id'), nullable=False),
        sa.Column('definition_version', sa.String(32), nullable=False),
        sa.Column('definition_snapshot_json', sa.Text(), nullable=False),
        sa.Column('answers_json', sa.Text(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('submitted_at', sa.String(40), nullable=False),
        sa.Column('idempotency_key', sa.String(80), nullable=False))
    op.create_table('px_personas',
        sa.Column('user_id', sa.String(64), sa.ForeignKey('users.id'), primary_key=True, nullable=False),
        sa.Column('persona_key', sa.String(64), nullable=False, unique=True),
        sa.Column('description', sa.String(300), nullable=False),
        sa.Column('state', sa.String(32), nullable=False))


def downgrade():
    for table in ('px_personas', 'px_questionnaire_submissions', 'px_questionnaire_drafts',
                  'px_questionnaire_assignments', 'px_questionnaire_definitions', 'px_observations'):
        op.drop_table(table)
