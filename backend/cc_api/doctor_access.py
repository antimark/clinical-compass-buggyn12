"""Current clinician scope/tenant/consent checks, before clinical selection."""
from flask import abort
from sqlalchemy import select, update
from .models import User, DoctorPatientLink
from .onboarding_models import PatientConsent


def authorized_patient(db, doctor, patient_id, scope='symptoms', lock=False):
    if doctor.role != 'doctor':
        abort(403)
    person = db.scalar(select(User).where(User.patient_id == patient_id,
        User.role == 'patient', User.organization_id == doctor.organization_id))
    if not person:
        abort(404)
    # Mutations serialize with withdrawal in the same consent-then-link order.
    # SQL no-op updates also acquire a write lock on SQLite (FOR UPDATE is ignored).
    if lock:
        db.execute(update(PatientConsent).where(PatientConsent.patient_user_id == person.id,
            PatientConsent.doctor_id == doctor.id).values(version=PatientConsent.version))
        db.execute(update(DoctorPatientLink).where(DoctorPatientLink.patient_id == patient_id,
            DoctorPatientLink.doctor_id == doctor.id).values(categories=DoctorPatientLink.categories))
    links = db.scalars(select(DoctorPatientLink).where(
        DoctorPatientLink.patient_id == patient_id, DoctorPatientLink.doctor_id == doctor.id)
        .execution_options(populate_existing=True)).all()
    if not links:
        abort(404)
    granted = set().union(*(set(filter(None,link.categories.split(','))) for link in links))
    ledgers = db.scalars(select(PatientConsent).where(
        PatientConsent.patient_user_id == person.id, PatientConsent.doctor_id == doctor.id)
        .execution_options(populate_existing=True)).all()
    if ledgers:
        active = set().union(*(set(filter(None,c.categories.split(','))) for c in ledgers if c.revoked_at is None))
        granted &= active
    if not granted or (scope is not None and scope not in granted):
        abort(404)
    return person


def authorized_scopes(db, doctor, patient_id, lock=False):
    person = authorized_patient(db, doctor, patient_id, None, lock=lock)
    links = db.scalars(select(DoctorPatientLink).where(DoctorPatientLink.patient_id == patient_id,
        DoctorPatientLink.doctor_id == doctor.id)).all()
    granted = set().union(*(set(filter(None,row.categories.split(','))) for row in links))
    ledgers = db.scalars(select(PatientConsent).where(PatientConsent.patient_user_id == person.id,
        PatientConsent.doctor_id == doctor.id)).all()
    if ledgers:
        granted &= set().union(*(set(filter(None,row.categories.split(','))) for row in ledgers if row.revoked_at is None))
    return granted
