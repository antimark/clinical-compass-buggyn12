"""Narrow intake source authorization; no diary/message/document tables are read."""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime,timezone
from flask import abort
from sqlalchemy import select
from .doctor_access import authorized_patient
from .models import DoctorPatientLink
from .onboarding_models import PatientConsent,PatientInvitation
from .extension_models import PrevisitCase

POLICY='ci-intake-symptoms-v1'
MAX_SOURCE=4000


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def active_case(row):
    try:
        stamp=datetime.fromisoformat(row.allowed_until.replace('Z','+00:00'))
        return row.status in ('submitted','reviewed') and row.consent_version=='case-1' and stamp.tzinfo is not None and stamp>datetime.now(timezone.utc)
    except (ValueError,TypeError,AttributeError):return False


def clinical_grant(db,doctor,patient_id):
    # Existing authority first. CI additionally requires an explicit accepted consent ledger.
    person=authorized_patient(db,doctor,patient_id,'symptoms')
    pairs=db.execute(select(PatientConsent,PatientInvitation).join(PatientInvitation,
        PatientInvitation.id==PatientConsent.invitation_id).where(
        PatientConsent.patient_user_id==person.id,PatientConsent.doctor_id==doctor.id,
        PatientConsent.revoked_at.is_(None),PatientConsent.version=='clinical-link-v1',
        PatientInvitation.issuer_id==doctor.id,PatientInvitation.patient_user_id==person.id,
        PatientInvitation.organization_id==doctor.organization_id,PatientInvitation.status=='accepted',
        PatientInvitation.accepted_at.is_not(None),PatientInvitation.revoked_at.is_(None))).all()
    now=datetime.now(timezone.utc)
    valid=[]
    for consent,invitation in pairs:
        if 'symptoms' not in consent.categories.split(',') or 'symptoms' not in invitation.categories.split(','):continue
        try:
            stamp=datetime.fromisoformat(consent.accepted_at.replace('Z','+00:00'))
            if stamp.tzinfo is None or stamp>now:continue
        except (ValueError,TypeError):continue
        valid.append([consent.id,consent.version,consent.accepted_at,invitation.id,invitation.accepted_at])
    if not valid:abort(404)
    links=db.execute(select(DoctorPatientLink.id,DoctorPatientLink.categories).where(
        DoctorPatientLink.patient_id==patient_id,DoctorPatientLink.doctor_id==doctor.id)).all()
    relevant=[row.id for row in links if 'symptoms' in row.categories.split(',')]
    if not relevant:abort(404)
    return person,digest([doctor.id,doctor.organization_id,person.id,person.organization_id,sorted(relevant),sorted(valid),POLICY])


def metadata_query(person,doctor):
    return select(PrevisitCase.id,PrevisitCase.patient_user_id,PrevisitCase.doctor_id,
        PrevisitCase.status,PrevisitCase.allowed_until,PrevisitCase.consent_version,PrevisitCase.created_at).where(
        PrevisitCase.patient_user_id==person.id,PrevisitCase.doctor_id==doctor.id)


@dataclass(frozen=True)
class AuthorizedIntake:
    patient_id:str
    case_id:str
    text:str
    created_at:str
    source_version:str
    source_revision:int
    grant_version:str


def selected_source(db,doctor,patient_id,case_id):
    person,grant=clinical_grant(db,doctor,patient_id)
    meta=db.execute(metadata_query(person,doctor).where(PrevisitCase.id==case_id)).first()
    if not meta or not active_case(meta):abort(404)
    # The clinical text column is selected only after all metadata ACL/consent checks.
    raw=db.scalar(select(PrevisitCase.intake_json).where(PrevisitCase.id==case_id,
        PrevisitCase.patient_user_id==person.id,PrevisitCase.doctor_id==doctor.id))
    try:data=json.loads(raw)
    except (ValueError,TypeError):abort(422,description='Источник недоступен для анализа')
    if not isinstance(data,dict):abort(422,description='Источник недоступен для анализа')
    field='text' if 'text' in data else 'message'
    text=data.get(field)
    if not isinstance(text,str) or not text.strip() or not 1<=len(text)<=MAX_SOURCE:
        abort(422,description='Источник недоступен для анализа')
    # Never hash unrelated structured fields (medications, questionnaires, private copies).
    version=digest([POLICY,field,text,meta.created_at,meta.consent_version])
    return AuthorizedIntake(patient_id,case_id,text,meta.created_at,version,int(version[:12],16)+1,
        digest([grant,meta.status,meta.allowed_until,meta.consent_version]))
