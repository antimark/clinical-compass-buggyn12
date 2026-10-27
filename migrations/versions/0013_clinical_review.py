"""Additive Phase5 cr_ stores; frozen schema and append-only review history."""
from alembic import op
import sqlalchemy as sa
revision = '0013_clinical_review'
down_revision = '0012_research_workflow'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cr_review_packets',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('source_kind', sa.String(length=32), nullable=False),
        sa.Column('source_id', sa.String(length=100), nullable=False),
        sa.Column('source_version', sa.String(length=120), nullable=False),
        sa.Column('content_sha256', sa.String(length=64), nullable=False),
        sa.Column('packet_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('creator_id', sa.String(length=64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('requested_at', sa.String(length=40), nullable=False))
    op.create_table('cr_summary_fields',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('draft_id', sa.String(length=60), sa.ForeignKey('cc_ai_summary_drafts.id'), nullable=False),
        sa.Column('field_key', sa.String(length=60), nullable=False),
        sa.Column('label', sa.String(length=160), nullable=False),
        sa.Column('scope', sa.String(length=24), nullable=False),
        sa.Column('source_version', sa.Integer(), nullable=False),
        sa.Column('value_json', sa.Text(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('reviewed_value_json', sa.Text(), nullable=True),
        sa.Column('reviewer_id', sa.String(length=64), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.String(length=40), nullable=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False),
        sa.UniqueConstraint('draft_id', 'field_key'))
    op.create_table('cr_decision_classifications',
        sa.Column('decision_id', sa.String(length=60), sa.ForeignKey('p0_decisions.id'), nullable=False, primary_key=True),
        sa.Column('code', sa.String(length=24), nullable=False),
        sa.Column('version', sa.String(length=120), nullable=False),
        sa.Column('label', sa.String(length=300), nullable=False),
        sa.Column('created_at', sa.String(length=40), nullable=False))
    op.create_table('cr_encounter_addenda',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('encounter_id', sa.String(length=60), sa.ForeignKey('p0_encounters.id'), nullable=False),
        sa.Column('author_id', sa.String(length=64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(length=40), nullable=False))
    op.create_table('cr_notification_destinations',
        sa.Column('notification_id', sa.String(length=60), sa.ForeignKey('p0_notifications.id'), nullable=False, primary_key=True),
        sa.Column('entity_type', sa.String(length=32), nullable=False),
        sa.Column('entity_id', sa.String(length=64), nullable=False))
    op.create_table('cr_summary_field_revisions',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('field_id', sa.String(length=64), sa.ForeignKey('cr_summary_fields.id'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.String(length=64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(length=24), nullable=False),
        sa.Column('snapshot_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(length=40), nullable=False),
        sa.UniqueConstraint('field_id', 'revision'))
    if op.get_bind().dialect.name == 'sqlite':
        op.execute("CREATE TRIGGER cr_summary_field_revisions_no_update BEFORE UPDATE ON cr_summary_field_revisions BEGIN SELECT RAISE(ABORT, 'Append-only history'); END")
        op.execute("CREATE TRIGGER cr_summary_field_revisions_no_delete BEFORE DELETE ON cr_summary_field_revisions BEGIN SELECT RAISE(ABORT, 'Append-only history'); END")
    elif op.get_bind().dialect.name == 'postgresql':
        op.execute("CREATE FUNCTION guard_cr_summary_field_revisions() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Append-only history'; END; $$ LANGUAGE plpgsql")
        op.execute("CREATE TRIGGER cr_summary_field_revisions_immutable BEFORE UPDATE OR DELETE ON cr_summary_field_revisions FOR EACH ROW EXECUTE FUNCTION guard_cr_summary_field_revisions()")
    if op.get_bind().dialect.name == 'sqlite':
        op.execute("CREATE TRIGGER cr_encounter_addenda_no_update BEFORE UPDATE ON cr_encounter_addenda BEGIN SELECT RAISE(ABORT, 'Append-only history'); END")
        op.execute("CREATE TRIGGER cr_encounter_addenda_no_delete BEFORE DELETE ON cr_encounter_addenda BEGIN SELECT RAISE(ABORT, 'Append-only history'); END")
    elif op.get_bind().dialect.name == 'postgresql':
        op.execute("CREATE FUNCTION guard_cr_encounter_addenda() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Append-only history'; END; $$ LANGUAGE plpgsql")
        op.execute("CREATE TRIGGER cr_encounter_addenda_immutable BEFORE UPDATE OR DELETE ON cr_encounter_addenda FOR EACH ROW EXECUTE FUNCTION guard_cr_encounter_addenda()")
    if op.get_bind().dialect.name == 'sqlite':
        op.execute("CREATE TRIGGER cr_review_packets_no_update BEFORE UPDATE ON cr_review_packets BEGIN SELECT RAISE(ABORT, 'Append-only history'); END")
        op.execute("CREATE TRIGGER cr_review_packets_no_delete BEFORE DELETE ON cr_review_packets BEGIN SELECT RAISE(ABORT, 'Append-only history'); END")
    elif op.get_bind().dialect.name == 'postgresql':
        op.execute("CREATE FUNCTION guard_cr_review_packets() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Append-only history'; END; $$ LANGUAGE plpgsql")
        op.execute("CREATE TRIGGER cr_review_packets_immutable BEFORE UPDATE OR DELETE ON cr_review_packets FOR EACH ROW EXECUTE FUNCTION guard_cr_review_packets()")


def downgrade():
    op.drop_table('cr_summary_field_revisions')
    op.drop_table('cr_notification_destinations')
    op.drop_table('cr_encounter_addenda')
    op.drop_table('cr_decision_classifications')
    op.drop_table('cr_summary_fields')
    op.drop_table('cr_review_packets')
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP FUNCTION IF EXISTS guard_cr_summary_field_revisions()")
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP FUNCTION IF EXISTS guard_cr_encounter_addenda()")
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP FUNCTION IF EXISTS guard_cr_review_packets()")
