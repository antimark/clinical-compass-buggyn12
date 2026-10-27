"""Additive Phase5 ap_ stores; frozen schema and append-only review history."""
from alembic import op
import sqlalchemy as sa
revision = '0010_admin_privacy'
down_revision = '0009_guided_pitch'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('ap_flags',
        sa.Column('scope', sa.String(length=80), nullable=False, primary_key=True),
        sa.Column('enabled', sa.Boolean(), nullable=False))
    op.create_table('ap_templates',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=64), nullable=False),
        sa.Column('template_key', sa.String(length=80), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('read_fields_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(length=40), nullable=False),
        sa.CheckConstraint('version > 0', name='ck_ap_template_version'),
        sa.UniqueConstraint('organization_id', 'template_key', 'version', name='uq_ap_template_version'))
    op.create_table('ap_overrides',
        sa.Column('patient_user_id', sa.String(length=64), sa.ForeignKey('users.id'), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('field_key', sa.String(length=40), nullable=False, primary_key=True),
        sa.Column('effect', sa.String(length=5), nullable=False),
        sa.Column('expires_at', sa.String(length=40), nullable=True),
        sa.CheckConstraint("effect IN ('ALLOW','DENY')", name='ck_ap_override_effect'))
    op.create_table('ap_policies',
        sa.Column('patient_user_id', sa.String(length=64), sa.ForeignKey('users.id'), nullable=False, primary_key=True),
        sa.Column('organization_id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('template_id', sa.String(length=64), sa.ForeignKey('ap_templates.id'), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('accepted_at', sa.String(length=40), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False))
    op.create_table('ap_values',
        sa.Column('patient_user_id', sa.String(length=64), sa.ForeignKey('users.id'), nullable=False, primary_key=True),
        sa.Column('field_key', sa.String(length=40), nullable=False, primary_key=True),
        sa.Column('ciphertext', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.String(length=40), nullable=False))
    if op.get_bind().dialect.name == 'sqlite':
        op.execute("CREATE TRIGGER ap_templates_no_update BEFORE UPDATE ON ap_templates BEGIN SELECT RAISE(ABORT, 'Append-only history'); END")
        op.execute("CREATE TRIGGER ap_templates_no_delete BEFORE DELETE ON ap_templates BEGIN SELECT RAISE(ABORT, 'Append-only history'); END")
    elif op.get_bind().dialect.name == 'postgresql':
        op.execute("CREATE FUNCTION guard_ap_templates() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Append-only history'; END; $$ LANGUAGE plpgsql")
        op.execute("CREATE TRIGGER ap_templates_immutable BEFORE UPDATE OR DELETE ON ap_templates FOR EACH ROW EXECUTE FUNCTION guard_ap_templates()")


def downgrade():
    op.drop_table('ap_values')
    op.drop_table('ap_policies')
    op.drop_table('ap_overrides')
    op.drop_table('ap_templates')
    op.drop_table('ap_flags')
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP FUNCTION IF EXISTS guard_ap_templates()")
