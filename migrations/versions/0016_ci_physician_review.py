"""Durable immutable NLP claims, own-physician review and native draft provenance."""
from alembic import op
import sqlalchemy as sa
revision = '0016_ci_physician_review'
down_revision = '0015_persistent_profiles'
branch_labels = None
depends_on = None


def col(name, size=64, fk=None, primary=False):
    return sa.Column(name, sa.String(size), *([sa.ForeignKey(fk)] if fk else []), primary_key=primary, nullable=False)


def upgrade():
    op.create_table('ci_suggestion_claims', col('id', primary=True), col('actor_id', fk='users.id'),
        col('organization_id'), col('patient_id', fk='patients.id'), col('case_id', fk='cc_previsit_cases.id'),
        col('source_version'), col('grant_version'), sa.Column('provenance_json', sa.Text(), nullable=False), col('created_at',40))
    op.create_table('ci_reviews', col('suggestion_id',fk='ci_suggestion_claims.id',primary=True),
        sa.Column('revision',sa.Integer(),nullable=False), sa.Column('state_json',sa.Text(),nullable=False),col('updated_at',40))
    op.create_table('ci_review_events',col('id',primary=True),col('suggestion_id',fk='ci_suggestion_claims.id'),
        col('actor_id',fk='users.id'),sa.Column('revision',sa.Integer(),nullable=False),col('key_hash'),col('request_digest'),
        col('prior_digest'),sa.Column('state_json',sa.Text(),nullable=False),col('created_at',40),
        sa.UniqueConstraint('suggestion_id','revision'),sa.UniqueConstraint('actor_id','key_hash'))
    op.create_table('ci_draft_transfers',col('id',primary=True),col('suggestion_id',fk='ci_suggestion_claims.id'),
        col('actor_id',fk='users.id'),sa.Column('review_revision',sa.Integer(),nullable=False),
        col('document_id',fk='cd_documents.id'),sa.Column('document_revision',sa.Integer(),nullable=False),
        col('target_field',32),col('text_digest'),col('key_hash'),col('request_digest'),col('created_at',40),
        sa.UniqueConstraint('actor_id','key_hash'))


def downgrade():
    for table in ('ci_draft_transfers','ci_review_events','ci_reviews','ci_suggestion_claims'):
        op.drop_table(table)
