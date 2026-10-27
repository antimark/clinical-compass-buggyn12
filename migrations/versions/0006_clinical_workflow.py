"""Add versioned clinical workflows and persisted scheduling; preserve prior tables."""
from alembic import op
import sqlalchemy as sa
revision = '0006_clinical_workflow'
down_revision = '0005_doctor_experience'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('cd_documents',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('patient_id', sa.String(64), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('clinician_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(24), nullable=False),
        sa.Column('mode', sa.String(24), nullable=False),
        sa.Column('content_json', sa.Text(), nullable=False),
        sa.Column('required_scopes', sa.String(200), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('parent_id', sa.String(64), sa.ForeignKey('cd_documents.id'), nullable=True),
        sa.Column('amendment_reason', sa.Text(), nullable=True),
        sa.Column('signed_hash', sa.String(64), nullable=True),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False),
        sa.Column('signed_at', sa.String(40), nullable=True),
        sa.Column('published_at', sa.String(40), nullable=True))
    op.create_table('cd_document_revisions',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('document_id', sa.String(64), sa.ForeignKey('cd_documents.id'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(32), nullable=False),
        sa.Column('actor_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('snapshot_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.UniqueConstraint('document_id', 'revision'))
    op.create_table('cd_medication_orders',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('document_id', sa.String(64), sa.ForeignKey('cd_documents.id'), nullable=False),
        sa.Column('patient_id', sa.String(64), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('clinician_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('reference_id', sa.String(80), nullable=True),
        sa.Column('reference_version', sa.String(80), nullable=True),
        sa.Column('regimen_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False))
    op.create_table('cd_medication_adherence',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('order_id', sa.String(64), sa.ForeignKey('cd_medication_orders.id'), nullable=False),
        sa.Column('patient_user_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('outcome', sa.String(32), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('recorded_at', sa.String(40), nullable=False))
    op.create_table('cd_availability_slots',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('doctor_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('starts_at', sa.String(40), nullable=False),
        sa.Column('ends_at', sa.String(40), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.UniqueConstraint('doctor_id', 'starts_at'))
    op.create_table('cd_reschedule_requests',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('appointment_id', sa.String(64), sa.ForeignKey('cc_appointments.id'), nullable=False),
        sa.Column('requester_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('resolved_at', sa.String(40), nullable=True),
        sa.Column('replacement_appointment_id', sa.String(64), sa.ForeignKey('cc_appointments.id'), nullable=True))
    op.create_table('cd_appointment_proposals',
        sa.Column('id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('case_id', sa.String(64), sa.ForeignKey('cc_previsit_cases.id'), nullable=False),
        sa.Column('doctor_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('patient_user_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('slot_ids_json', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.String(40), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('accepted_appointment_id', sa.String(64), sa.ForeignKey('cc_appointments.id'), nullable=True),
        sa.Column('reschedule_request_id', sa.String(64), sa.ForeignKey('cd_reschedule_requests.id'), nullable=True))
    op.create_table('cd_proposal_candidates',
        sa.Column('appointment_id', sa.String(64), sa.ForeignKey('cc_appointments.id'), primary_key=True, nullable=False),
        sa.Column('proposal_id', sa.String(64), sa.ForeignKey('cd_appointment_proposals.id'), nullable=False),
        sa.Column('slot_id', sa.String(64), sa.ForeignKey('cd_availability_slots.id'), nullable=False))
    op.create_table('cd_slot_bookings',
        sa.Column('slot_id', sa.String(64), sa.ForeignKey('cd_availability_slots.id'), primary_key=True, nullable=False),
        sa.Column('appointment_id', sa.String(64), sa.ForeignKey('cc_appointments.id'), nullable=False),
        sa.Column('doctor_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('patient_user_id', sa.String(64), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('starts_at', sa.String(40), nullable=False),
        sa.Column('ends_at', sa.String(40), nullable=False),
        sa.UniqueConstraint('appointment_id'))

def downgrade():
    op.drop_table('cd_slot_bookings')
    op.drop_table('cd_proposal_candidates')
    op.drop_table('cd_appointment_proposals')
    op.drop_table('cd_reschedule_requests')
    op.drop_table('cd_availability_slots')
    op.drop_table('cd_medication_adherence')
    op.drop_table('cd_medication_orders')
    op.drop_table('cd_document_revisions')
    op.drop_table('cd_documents')
