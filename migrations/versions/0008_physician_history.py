"""Keep historical adverse-event assessments and synthetic physician names."""
from alembic import op
import sqlalchemy as sa
revision = '0008_physician_history'
down_revision = '0007_structured_references'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('dx_adverse_event_revisions',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('event_id', sa.String(60), sa.ForeignKey('p0_adverse_events.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('review_text', sa.Text(), nullable=False),
        sa.Column('reviewer_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.UniqueConstraint('event_id', 'version', name='uq_dx_adverse_review_version'))
    op.create_index('ix_dx_adverse_event_revisions_event_id', 'dx_adverse_event_revisions', ['event_id'])
    op.create_table('dx_physician_profiles',
        sa.Column('user_id', sa.String(64), sa.ForeignKey('users.id'), primary_key=True, nullable=False),
        sa.Column('full_name', sa.String(150), nullable=False),
        sa.Column('synthetic', sa.Integer(), nullable=False))


def downgrade():
    op.drop_table('dx_physician_profiles')
    op.drop_index('ix_dx_adverse_event_revisions_event_id', table_name='dx_adverse_event_revisions')
    op.drop_table('dx_adverse_event_revisions')
