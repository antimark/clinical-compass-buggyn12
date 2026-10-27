"""Additive Phase5 rw_ stores; frozen schema and append-only review history."""
from alembic import op
import sqlalchemy as sa
revision = '0012_research_workflow'
down_revision = '0011_oidc_browser'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('rw_study_locks',
        sa.Column('study_id', sa.String(length=50), nullable=False, primary_key=True),
        sa.Column('revision', sa.Integer(), nullable=False))
    op.create_table('rw_study_grants',
        sa.Column('researcher_id', sa.String(length=64), sa.ForeignKey('users.id'), nullable=False, primary_key=True),
        sa.Column('study_id', sa.String(length=50), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('active', sa.Boolean(), nullable=False))
    op.create_table('rw_disclosures',
        sa.Column('id', sa.String(length=60), nullable=False, primary_key=True),
        sa.Column('study_id', sa.String(length=50), nullable=False),
        sa.Column('cohort', sa.String(length=30), nullable=False),
        sa.Column('definition_id', sa.String(length=60), sa.ForeignKey('p0_dataset_definitions.id'), nullable=False),
        sa.Column('definition_version', sa.Integer(), nullable=False),
        sa.Column('query_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('membership_json', sa.Text(), nullable=False),
        sa.Column('values_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('result_json', sa.Text(), nullable=False),
        sa.Column('min_cell', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.String(length=40), nullable=False))
    op.create_index('ix_rw_disclosures_study_id', 'rw_disclosures', ['study_id'], unique=False)
    op.create_table('rw_revisions',
        sa.Column('id', sa.String(length=60), nullable=False, primary_key=True),
        sa.Column('definition_id', sa.String(length=60), sa.ForeignKey('p0_dataset_definitions.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('snapshot_json', sa.Text(), nullable=False),
        sa.Column('actor_id', sa.String(length=64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.String(length=40), nullable=False),
        sa.UniqueConstraint('definition_id', 'version', name='uq_rw_definition_version'))
    if op.get_bind().dialect.name == 'sqlite':
        op.execute("CREATE TRIGGER rw_revisions_no_update BEFORE UPDATE ON rw_revisions BEGIN SELECT RAISE(ABORT, 'Append-only history'); END")
        op.execute("CREATE TRIGGER rw_revisions_no_delete BEFORE DELETE ON rw_revisions BEGIN SELECT RAISE(ABORT, 'Append-only history'); END")
    elif op.get_bind().dialect.name == 'postgresql':
        op.execute("CREATE FUNCTION guard_rw_revisions() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Append-only history'; END; $$ LANGUAGE plpgsql")
        op.execute("CREATE TRIGGER rw_revisions_immutable BEFORE UPDATE OR DELETE ON rw_revisions FOR EACH ROW EXECUTE FUNCTION guard_rw_revisions()")
    if op.get_bind().dialect.name == 'sqlite':
        op.execute("CREATE TRIGGER rw_disclosures_no_update BEFORE UPDATE ON rw_disclosures BEGIN SELECT RAISE(ABORT, 'Append-only history'); END")
        op.execute("CREATE TRIGGER rw_disclosures_no_delete BEFORE DELETE ON rw_disclosures BEGIN SELECT RAISE(ABORT, 'Append-only history'); END")
    elif op.get_bind().dialect.name == 'postgresql':
        op.execute("CREATE FUNCTION guard_rw_disclosures() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Append-only history'; END; $$ LANGUAGE plpgsql")
        op.execute("CREATE TRIGGER rw_disclosures_immutable BEFORE UPDATE OR DELETE ON rw_disclosures FOR EACH ROW EXECUTE FUNCTION guard_rw_disclosures()")
    op.execute(sa.text("INSERT INTO rw_study_locks (study_id, revision) VALUES ('study_demo_v1', 0)"))


def downgrade():
    op.drop_table('rw_revisions')
    op.drop_table('rw_disclosures')
    op.drop_table('rw_study_grants')
    op.drop_table('rw_study_locks')
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP FUNCTION IF EXISTS guard_rw_revisions()")
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP FUNCTION IF EXISTS guard_rw_disclosures()")
