"""Manual physician referrals and private contextual chat; no clinical document clone."""
from alembic import op
import sqlalchemy as sa
revision='0017_referrals_copilot'
down_revision='0016_ci_physician_review'
branch_labels=None
depends_on=None

def c(name,fk=None,size=64):return sa.Column(name,sa.String(size),*([sa.ForeignKey(fk)] if fk else []),primary_key=name=='id',nullable=False)
def text(name):return sa.Column(name,sa.Text(),nullable=False)
def integer(name):return sa.Column(name,sa.Integer(),nullable=False)
def common():return [c('id'),c('actor_id','users.id'),c('tenant_id'),c('patient_id','patients.id'),c('case_id','cc_previsit_cases.id'),c('source_version'),c('grant_version'),integer('revision'),c('status',size=24),c('created_at',size=40),c('updated_at',size=40)]

def upgrade():
    op.create_table('ci_referrals',*common(),text('content_json'),c('confirmation_hash'))
    op.create_table('ci_referral_events',c('id'),c('referral_id','ci_referrals.id'),integer('revision'),c('actor_id','users.id'),c('action',size=24),text('reason'),c('created_at',size=40),sa.UniqueConstraint('referral_id','revision'))
    op.create_table('ci_operation_receipts',c('id'),c('actor_id','users.id'),c('key_hash'),c('request_digest'),text('response_json'),c('created_at',size=40),sa.UniqueConstraint('actor_id','key_hash'))
    op.create_table('ci_chat_threads',*common(),c('retention_state',size=24))
    op.create_table('ci_chat_messages',c('id'),c('thread_id','ci_chat_threads.id'),integer('ordinal'),c('role',size=16),text('content'),text('provenance_json'),c('created_at',size=40),sa.UniqueConstraint('thread_id','ordinal'))
    op.create_table('ci_chat_jobs',c('id'),c('thread_id','ci_chat_threads.id'),c('input_id','ci_chat_messages.id'),c('status',size=24),c('safe_error_code',size=40),c('queued_at',size=40),c('started_at',size=40),c('finished_at',size=40),text('timings_json'))

def downgrade():
    for table in ('ci_chat_jobs','ci_chat_messages','ci_chat_threads','ci_operation_receipts','ci_referral_events','ci_referrals'):op.drop_table(table)
