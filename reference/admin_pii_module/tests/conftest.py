from __future__ import annotations
from datetime import datetime, timezone, timedelta
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clinical_compass.models import (
    Base, User, Organization, Membership, Patient, PatientClinicLink,
    DoctorPatientLink, ClinicalRecord, Notification, PatientFieldValue,
    configure_sqlite,
)
from clinical_compass.security import PiiCipher, hash_password
from clinical_compass import service as s


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.sqlite'}")
    configure_sqlite(engine)
    Base.metadata.create_all(engine)
    key = Fernet.generate_key().decode()
    cipher = PiiCipher(key)
    with Session(engine) as db:
        admin = User(username="clinic_admin", password_hash=hash_password("ValidPassword!222"))
        admin2 = User(username="clinic_admin2", password_hash=hash_password("ValidPassword!222"))
        doctor = User(username="doctor", password_hash=hash_password("ValidPassword!222"))
        p1user = User(username="patient1", password_hash=hash_password("ValidPassword!222"))
        p2user = User(username="patient2", password_hash=hash_password("ValidPassword!222"))
        platform = User(username="platform", password_hash=hash_password("ValidPassword!222"), is_platform_admin=True)
        rogue = User(username="outsider", password_hash=hash_password("ValidPassword!222"))
        org1, org2 = Organization(name="Clinic A"), Organization(name="Clinic B")
        db.add_all([admin, admin2, doctor, p1user, p2user, platform, rogue, org1, org2])
        db.flush()
        db.add_all([
            Membership(user_id=admin.id, organization_id=org1.id, role="CLINIC_ADMIN"),
            Membership(user_id=admin2.id, organization_id=org2.id, role="CLINIC_ADMIN"),
            Membership(user_id=doctor.id, organization_id=org1.id, role="DOCTOR"),
        ])
        p1, p2 = Patient(user_id=p1user.id), Patient(user_id=p2user.id)
        db.add_all([p1, p2])
        db.flush()
        l1 = PatientClinicLink(patient_id=p1.id, organization_id=org1.id)
        l2 = PatientClinicLink(patient_id=p2.id, organization_id=org1.id)
        l3 = PatientClinicLink(patient_id=p1.id, organization_id=org2.id)
        db.add_all([l1, l2, l3])
        db.add_all([
            DoctorPatientLink(patient_id=p1.id, doctor_user_id=doctor.id, organization_id=org1.id),
            DoctorPatientLink(patient_id=p2.id, doctor_user_id=doctor.id, organization_id=org1.id),
        ])
        db.add(ClinicalRecord(patient_id=p1.id, encrypted_payload=cipher.encrypt("Secret diagnosis: example")))
        db.flush()
        ids = {"admin": admin.id, "admin2": admin2.id, "doctor": doctor.id,
               "platform": platform.id, "p1user": p1user.id, "p2user": p2user.id,
               "rogue": rogue.id, "p1": p1.id, "p2": p2.id,
               "org1": org1.id, "org2": org2.id,
               "l1": l1.id, "l2": l2.id, "l3": l3.id,
               "ref1": l1.local_ref, "ref2": l2.local_ref, "ref3": l3.local_ref}
        s.seed_base_fields(db)
        db.flush()
        s.write_patient_field(db, p1user.id, "first_name", "Alice", cipher)
        s.write_patient_field(db, p1user.id, "phone", "+10001112233", cipher)
        s.write_patient_field(db, p2user.id, "first_name", "Bob", cipher)
        s.write_patient_field(db, p2user.id, "phone", "+20004445566", cipher)
        t1 = s.create_template(db, platform.id, org1.id, "names_only", 1, ["first_name"])
        t2 = s.create_template(db, platform.id, org1.id, "contacts_only", 1, ["phone"])
        t3 = s.create_template(db, platform.id, org2.id, "contacts_only", 1, ["phone"])
        db.flush()
        ids.update({"t1": t1.id, "t2": t2.id, "t3": t3.id})
        s.accept_template(db, p1user.id, l1.id, t1.id, True)
        s.accept_template(db, p2user.id, l2.id, t2.id, True)
        s.accept_template(db, p1user.id, l3.id, t3.id, True)
        db.commit()
        yield db, ids, cipher, engine, key
    engine.dispose()


@pytest.fixture
def active(env):
    db, ids, cipher, engine, key = env
    s.set_flag(db, ids["platform"], None, True)
    s.set_flag(db, ids["platform"], ids["org1"], True)
    s.set_flag(db, ids["platform"], ids["org2"], True)
    db.commit()
    return env
