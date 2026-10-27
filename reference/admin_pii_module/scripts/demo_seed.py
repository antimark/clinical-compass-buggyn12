"""Synthetic-only demo seeder. Never run in production."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from clinical_compass.models import (
    User, Organization, Membership, Patient, PatientClinicLink, DoctorPatientLink,
    configure_sqlite,
)
from clinical_compass.security import PiiCipher, hash_password
from clinical_compass import service as s


def main():
    load_dotenv()
    if os.environ.get("APP_ENV") != "development":
        raise RuntimeError("Synthetic demo seed is development-only")
    key = os.environ.get("PII_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("PII_ENCRYPTION_KEY is required")
    url = os.environ.get("DATABASE_URL", "sqlite:///data/core.sqlite")
    engine = create_engine(url)
    configure_sqlite(engine)
    with Session(engine) as db:
        if db.scalar(select(User.id).where(User.username == "platform_demo")):
            print("Demo already seeded")
            return
        pwd = hash_password("DemoPassword!123456")
        platform = User(username="platform_demo", password_hash=pwd, is_platform_admin=True)
        admin = User(username="admin_demo", password_hash=pwd)
        doctor = User(username="doctor_demo", password_hash=pwd)
        alice = User(username="patient_alice_demo", password_hash=pwd)
        bob = User(username="patient_bob_demo", password_hash=pwd)
        org = Organization(name="Synthetic demonstration clinic")
        db.add_all([platform, admin, doctor, alice, bob, org])
        db.flush()
        db.add_all([
            Membership(user_id=admin.id, organization_id=org.id, role="CLINIC_ADMIN"),
            Membership(user_id=doctor.id, organization_id=org.id, role="DOCTOR"),
        ])
        p1, p2 = Patient(user_id=alice.id), Patient(user_id=bob.id)
        db.add_all([p1, p2])
        db.flush()
        l1 = PatientClinicLink(patient_id=p1.id, organization_id=org.id)
        l2 = PatientClinicLink(patient_id=p2.id, organization_id=org.id)
        db.add_all([l1, l2])
        db.add_all([
            DoctorPatientLink(patient_id=p1.id, doctor_user_id=doctor.id, organization_id=org.id),
            DoctorPatientLink(patient_id=p2.id, doctor_user_id=doctor.id, organization_id=org.id),
        ])
        s.seed_base_fields(db)
        db.flush()
        cipher = PiiCipher(key)
        s.write_patient_field(db, alice.id, "first_name", "Alice", cipher)
        s.write_patient_field(db, alice.id, "phone", "+10000000000", cipher)
        s.write_patient_field(db, bob.id, "first_name", "Bob", cipher)
        s.write_patient_field(db, bob.id, "phone", "+20000000000", cipher)
        t1 = s.create_template(db, platform.id, org.id, "names_only", 1, ["first_name"])
        t2 = s.create_template(db, platform.id, org.id, "phone_only", 1, ["phone"])
        db.flush()
        s.accept_template(db, alice.id, l1.id, t1.id, True)
        s.accept_template(db, bob.id, l2.id, t2.id, True)
        # Both flags remain OFF deliberately: secure-by-default demo.
        db.commit()
        print("Seeded synthetic clinic ID", org.id)
        print("Accounts: platform_demo, admin_demo, doctor_demo, patient_alice_demo, patient_bob_demo")
        print("Development-only password: DemoPassword!123456")
        print("Feature flags are OFF. Enable global + organization flags explicitly via API.")


if __name__ == "__main__":
    main()
