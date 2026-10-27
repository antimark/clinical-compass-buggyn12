"""Additive synthetic P0 stores with the original v0.8 model unchanged.

Revision ID: 0002_p0_synthetic
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa
revision='0002_p0_synthetic'
down_revision='0001_initial'
branch_labels=None
depends_on=None

def c(name,typ,*args,nullable=False,**kw): return sa.Column(name,typ,*args,nullable=nullable,**kw)
def s(length):return sa.String(length)
def table(name,*cols):op.create_table(name,*cols)
def upgrade():
    table('p0_care_plans',c('id',s(60),primary_key=True),c('patient_id',s(64),sa.ForeignKey('patients.id')),c('clinician_id',s(64),sa.ForeignKey('users.id')),c('status',s(24)),c('version',sa.Integer()),c('created_at',s(40)))
    table('p0_plan_items',c('id',s(60),primary_key=True),c('plan_id',s(60),sa.ForeignKey('p0_care_plans.id')),c('item_type',s(32)),c('title',s(200)),c('scheduled_at',s(40),nullable=True),c('frequency',s(120)),c('completion_criteria',s(300)),c('created_at',s(40)))
    table('p0_plan_events',c('id',s(60),primary_key=True),c('item_id',s(60),sa.ForeignKey('p0_plan_items.id')),c('patient_user_id',s(64),sa.ForeignKey('users.id')),c('outcome',s(32)),c('reported_at',s(40)))
    table('p0_adverse_events',c('id',s(60),primary_key=True),c('patient_id',s(64),sa.ForeignKey('patients.id')),c('reporter_id',s(64),sa.ForeignKey('users.id')),c('description',sa.Text()),c('status',s(24)),c('review_text',sa.Text(),nullable=True),c('reviewer_id',s(64),sa.ForeignKey('users.id'),nullable=True),c('created_at',s(40)),c('reviewed_at',s(40),nullable=True))
    table('p0_encounters',c('id',s(60),primary_key=True),c('patient_id',s(64),sa.ForeignKey('patients.id')),c('clinician_id',s(64),sa.ForeignKey('users.id')),c('mode',s(20)),c('content_json',sa.Text()),c('status',s(20)),c('created_at',s(40)),c('signed_at',s(40),nullable=True))
    table('p0_decisions',c('id',s(60),primary_key=True),c('patient_id',s(64),sa.ForeignKey('patients.id')),c('clinician_id',s(64),sa.ForeignKey('users.id')),c('text',sa.Text()),c('confirmed_at',s(40)))
    table('p0_alert_reviews',c('id',s(60),primary_key=True),c('alert_id',s(64),sa.ForeignKey('alerts.id')),c('clinician_id',s(64),sa.ForeignKey('users.id')),c('assessment',sa.Text()),c('status',s(20)),c('created_at',s(40)))
    table('p0_dataset_definitions',c('id',s(60),primary_key=True),c('researcher_id',s(64),sa.ForeignKey('users.id')),c('study_id',s(50)),c('definition_json',sa.Text()),c('version',sa.Integer()),c('created_at',s(40)))
    table('p0_notifications',c('id',s(60),primary_key=True),c('recipient_id',s(64),sa.ForeignKey('users.id')),c('text',s(300)),c('category',s(30)),c('created_at',s(40)),c('read_at',s(40),nullable=True))
    table('p0_summary_revisions',c('id',s(60),primary_key=True),c('draft_id',s(60),sa.ForeignKey('cc_ai_summary_drafts.id')),c('author_id',s(64),sa.ForeignKey('users.id')),c('version',sa.Integer()),c('content',sa.Text()),c('created_at',s(40)))
    table('p0_reference_articles',c('id',s(60),primary_key=True),c('title',s(200)),c('publisher',s(100)),c('original_url',s(600)),c('version',s(50)),c('reviewed_at',s(40)),c('licensing',s(120)),c('limitations',sa.Text()),c('approval_status',s(20)))
    for name,col in [('p0_care_plans','patient_id'),('p0_plan_items','plan_id'),('p0_plan_events','item_id'),('p0_adverse_events','patient_id'),('p0_encounters','patient_id'),('p0_decisions','patient_id'),('p0_alert_reviews','alert_id'),('p0_dataset_definitions','researcher_id'),('p0_notifications','recipient_id'),('p0_summary_revisions','draft_id')]:
        op.create_index('ix_'+name+'_'+col,name,[col])

def downgrade():
    for name in reversed(['p0_care_plans','p0_plan_items','p0_plan_events','p0_adverse_events','p0_encounters','p0_decisions','p0_alert_reviews','p0_dataset_definitions','p0_notifications','p0_summary_revisions','p0_reference_articles']):op.drop_table(name)
