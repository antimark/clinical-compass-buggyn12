"""Add evidence-linked signals and independent manual priority."""
from alembic import op
import sqlalchemy as sa
revision = '0005_doctor_experience'
down_revision = '0004_patient_experience'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('dx_signals',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('doctor_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('patient_id', sa.String(64), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('source', sa.String(64), nullable=False),
        sa.Column('event_key', sa.String(160), nullable=False),
        sa.Column('rule_version', sa.String(64), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('evidence_json', sa.Text(), nullable=False),
        sa.Column('occurred_at', sa.String(40), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.UniqueConstraint('doctor_id', 'event_key', name='uq_dx_signal_event'))
    op.create_index('ix_dx_signals_doctor_id', 'dx_signals', ['doctor_id'])
    op.create_table('dx_signal_reviews',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('signal_id', sa.String(64), sa.ForeignKey('dx_signals.id'), nullable=False),
        sa.Column('doctor_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('assessment', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False))
    op.create_index('ix_dx_signal_reviews_signal_id', 'dx_signal_reviews', ['signal_id'])
    op.create_table('dx_priorities',
        sa.Column('doctor_id', sa.String(64), sa.ForeignKey('users.id'), primary_key=True, nullable=False),
        sa.Column('patient_id', sa.String(64), sa.ForeignKey('patients.id'), primary_key=True, nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(500), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False))


def downgrade():
    op.drop_table('dx_priorities')
    op.drop_table('dx_signal_reviews')
    op.drop_table('dx_signals')
