"""Durable safety delivery and partitioned shared patient chat."""
from alembic import op
import sqlalchemy as sa
revision='0018_safety_patient_chat'
down_revision='0017_referrals_copilot'
branch_labels=None
depends_on=None

def c(name,fk=None,size=64,nullable=False,unique=False):
    return sa.Column(name,sa.String(size),*([sa.ForeignKey(fk)] if fk else []),primary_key=name=='id',nullable=nullable,unique=unique)
def t(name):return sa.Column(name,sa.Text(),nullable=False)
def i(name):return sa.Column(name,sa.Integer(),nullable=False)
def f(name):return sa.Column(name,sa.Float(),nullable=False)
def upgrade():
    with op.batch_alter_table('ci_chat_threads') as b:
        b.alter_column('case_id',existing_type=sa.String(64),nullable=True)
        b.add_column(sa.Column('audience',sa.String(16),nullable=False,server_default='doctor'))
        b.add_column(sa.Column('source_type',sa.String(24),nullable=False,server_default='intake'))
        b.add_column(sa.Column('source_id',sa.String(64),nullable=False,server_default=''))
    op.execute('UPDATE ci_chat_threads SET source_id=case_id')
    op.create_table('ci_patient_diaries',c('id'),c('actor_id','users.id'),c('tenant_id'),t('content'),i('revision'),c('created_at',size=40),c('updated_at',size=40))
    op.create_table('cc_safety_detections',c('id'),c('signal_id','dx_signals.id',nullable=True,unique=True),c('source_id','cc_previsit_cases.id'),c('patient_id','patients.id'),c('recipient_id','users.id'),c('tenant_id'),c('source_version'),c('grant_version'),t('trace_json'),c('status',size=32),c('workflow_status',size=24),i('revision'),c('created_at',size=40))
    op.create_table('cc_safety_outbox',c('id'),c('detection_id','cc_safety_detections.id',unique=True),c('status',size=24),i('attempts'),f('next_at'),f('lease_until'),c('lease_token'),c('receipt'),c('delivered_at',size=40),c('created_at',size=40))
    op.create_table('cc_safety_attempts',c('id'),c('outbox_id','cc_safety_outbox.id'),i('number'),c('status',size=32),c('created_at',size=40),c('finished_at',size=40),c('receipt'),sa.UniqueConstraint('outbox_id','number'))
    op.create_table('cc_safety_inbox',c('id'),c('outbox_id',unique=True),c('recipient_id'),t('envelope_json'),c('received_at',size=40))
    op.create_table('cc_safety_actions',c('id'),c('detection_id','cc_safety_detections.id'),c('actor_id','users.id'),i('revision'),c('action',size=24),c('key_hash',nullable=True),c('request_digest'),c('created_at',size=40),sa.UniqueConstraint('detection_id','revision'),sa.UniqueConstraint('actor_id','key_hash'))
def downgrade():
    for table in ('cc_safety_actions','cc_safety_inbox','cc_safety_attempts','cc_safety_outbox','cc_safety_detections','ci_patient_diaries'):op.drop_table(table)
    # Disposable databases only: diary threads cannot fit the older mandatory case FK.
    op.execute("DELETE FROM ci_chat_jobs WHERE thread_id IN (SELECT id FROM ci_chat_threads WHERE case_id IS NULL)")
    op.execute("DELETE FROM ci_chat_messages WHERE thread_id IN (SELECT id FROM ci_chat_threads WHERE case_id IS NULL)")
    op.execute('DELETE FROM ci_chat_threads WHERE case_id IS NULL')
    with op.batch_alter_table('ci_chat_threads') as b:
        for field in ('source_id','source_type','audience'):b.drop_column(field)
        b.alter_column('case_id',existing_type=sa.String(64),nullable=False)
