"""Append versioned raw-preserving references and pin optional medication references."""
from alembic import op
import sqlalchemy as sa
revision = '0007_structured_references'
down_revision = '0006_clinical_workflow'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('sr_medication_references',
        sa.Column('id', sa.String(80), primary_key=True, nullable=False),
        sa.Column('version', sa.String(80), primary_key=True, nullable=False),
        sa.Column('reference_type', sa.String(32), nullable=False),
        sa.Column('schema_version', sa.String(64), nullable=False),
        sa.Column('review_status', sa.String(40), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('inn', sa.String(200), nullable=False),
        sa.Column('raw_original_json', sa.Text(), nullable=False),
        sa.Column('import_fingerprint', sa.String(64), nullable=False),
        sa.Column('source_filename', sa.String(200), nullable=False),
        sa.Column('manifest_filename', sa.String(200), nullable=False),
        sa.Column('imported_at', sa.String(40), nullable=False),
        sa.Column('structured_json', sa.Text(), nullable=False))
    op.create_table('sr_reference_match_rules',
        sa.Column('id', sa.String(80), primary_key=True, nullable=False),
        sa.Column('version', sa.String(32), nullable=False),
        sa.Column('icd10_code', sa.String(32), nullable=False),
        sa.Column('drug_reference_id', sa.String(80), nullable=False),
        sa.Column('drug_reference_version', sa.String(80), nullable=False),
        sa.Column('match_basis', sa.Text(), nullable=False),
        sa.Column('source_field_paths_json', sa.Text(), nullable=False),
        sa.Column('curation_status', sa.String(40), nullable=False),
        sa.Column('environment_scope', sa.String(32), nullable=False),
        sa.Column('created_by', sa.String(80), nullable=False),
        sa.Column('reviewed_by', sa.String(80), nullable=True),
        sa.Column('display_limitation', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['drug_reference_id','drug_reference_version'],
            ['sr_medication_references.id','sr_medication_references.version']))
    op.create_table('sr_therapy_references',
        sa.Column('id', sa.String(80), primary_key=True, nullable=False),
        sa.Column('version', sa.String(80), primary_key=True, nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('review_status', sa.String(40), nullable=False),
        sa.Column('content_json', sa.Text(), nullable=False))
    with op.batch_alter_table('cd_medication_orders') as batch:
        batch.create_foreign_key('fk_cd_order_reference', 'sr_medication_references',
            ['reference_id','reference_version'], ['id','version'])


def downgrade():
    with op.batch_alter_table('cd_medication_orders') as batch:
        batch.drop_constraint('fk_cd_order_reference', type_='foreignkey')
    op.drop_table('sr_therapy_references')
    op.drop_table('sr_reference_match_rules')
    op.drop_table('sr_medication_references')
