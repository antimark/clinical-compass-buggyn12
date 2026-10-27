"""Persist guided-demo anchors and explicit escalation simulations, never delivery."""
from alembic import op
import sqlalchemy as sa
revision = '0009_guided_pitch'
down_revision = '0008_physician_history'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('pt_runs',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('doctor_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('patient_user_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('started_at', sa.String(40), nullable=False))
    op.create_table('pt_escalation_configs',
        sa.Column('doctor_id', sa.String(64), sa.ForeignKey('users.id'), primary_key=True, nullable=False),
        sa.Column('signal_id', sa.String(64), sa.ForeignKey('dx_signals.id'), primary_key=True, nullable=False),
        sa.Column('delay_seconds', sa.Integer(), nullable=True),
        sa.Column('target_label', sa.String(120), nullable=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False))
    op.create_table('pt_escalation_simulations',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('doctor_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('signal_id', sa.String(64), sa.ForeignKey('dx_signals.id'), nullable=False),
        sa.Column('config_revision', sa.Integer(), nullable=False),
        sa.Column('config_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False))


def downgrade():
    op.drop_table('pt_escalation_simulations')
    op.drop_table('pt_escalation_configs')
    op.drop_table('pt_runs')
