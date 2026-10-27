from __future__ import annotations
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select, inspect, text

from clinical_compass import service as s
from clinical_compass.models import (
    FeatureFlag, FieldDefinition, PatientFieldValue, Membership, PatientClinicLink,
    DoctorPatientLink, ClinicalRecord, AdminPiiPolicy, AdminPiiOverride,
    AdminPiiTemplate, AdminPiiTemplateRule, AuditEvent,
)
from clinical_compass.security import verify_password


def view(env, which="l1", actor="admin", org="org1"):
    db, ids, cipher, *_ = env
    return s.patient_view(db, ids[actor], ids[org], db.get(PatientClinicLink, ids[which]), cipher)


def test_default_flags_fail_closed(env):
    assert view(env) == {"patient_ref": env[1]["ref1"], "fields": {}}


def test_both_flags_required_and_immediate_revoke(active):
    db, ids, *_ = active
    assert view(active)["fields"] == {"first_name": "Alice"}
    s.set_flag(db, ids["platform"], None, False)
    db.commit()
    assert view(active)["fields"] == {}
    s.set_flag(db, ids["platform"], None, True)
    db.commit()
    assert view(active)["fields"] == {"first_name": "Alice"}
    s.set_flag(db, ids["platform"], ids["org1"], False)
    db.commit()
    assert view(active)["fields"] == {}
    assert view(active, "l3", "admin2", "org2")["fields"] == {"phone": "+10001112233"}


def test_different_patients_same_clinic_have_different_templates(active):
    assert view(active, "l1")["fields"] == {"first_name": "Alice"}
    assert view(active, "l2")["fields"] == {"phone": "+20004445566"}


def test_same_patient_different_clinics_different_policies(active):
    assert view(active, "l1")["fields"] == {"first_name": "Alice"}
    assert view(active, "l3", "admin2", "org2")["fields"] == {"phone": "+10001112233"}


def test_patient_override_deny_then_allow(active):
    db, ids, *_ = active
    s.update_override(db, ids["p1user"], ids["l1"], "first_name", "DENY")
    db.commit()
    assert view(active)["fields"] == {}
    s.update_override(db, ids["p1user"], ids["l1"], "phone", "ALLOW")
    db.commit()
    assert view(active)["fields"] == {"phone": "+10001112233"}
    s.update_override(db, ids["p1user"], ids["l1"], "phone", "REMOVE")
    db.commit()
    assert view(active)["fields"] == {}


def test_no_clinical_fields_ever_eligible(active):
    db, ids, cipher, *_ = active
    with pytest.raises(s.InvalidInput):
        s.register_field(db, ids["platform"], "diagnosis", "CLINICAL", True)
    s.register_field(db, ids["platform"], "diagnosis", "CLINICAL", False)
    db.flush()
    with pytest.raises(s.InvalidInput):
        s.create_template(db, ids["platform"], ids["org1"], "bad_template", 1, ["diagnosis"])
    with pytest.raises(s.InvalidInput):
        s.update_override(db, ids["p1user"], ids["l1"], "diagnosis", "ALLOW")
    assert "diagnosis" not in view(active)["fields"]
    assert "clinical" not in str(view(active)).lower()


def test_dynamic_identity_field_opt_in(active):
    db, ids, cipher, *_ = active
    s.register_field(db, ids["platform"], "preferred_name", "IDENTITY", True)
    db.flush()
    s.write_patient_field(db, ids["p1user"], "preferred_name", "Ali", cipher)
    db.commit()
    assert "preferred_name" not in view(active)["fields"]
    s.update_override(db, ids["p1user"], ids["l1"], "preferred_name", "ALLOW")
    db.commit()
    assert view(active)["fields"]["preferred_name"] == "Ali"


def test_revocation_per_link_immediate(active):
    db, ids, *_ = active
    s.revoke_policy(db, ids["p1user"], ids["l1"])
    db.commit()
    assert view(active)["fields"] == {}
    assert view(active, "l3", "admin2", "org2")["fields"] == {"phone": "+10001112233"}


def test_no_cross_clinic_or_fake_role(active):
    db, ids, cipher, *_ = active
    with pytest.raises(s.AccessDenied):
        view(active, "l1", "admin2", "org1")
    with pytest.raises(s.AccessDenied):
        view(active, "l1", "rogue", "org1")
    with pytest.raises(s.NotFound):
        s.get_link(db, ids["org2"], ids["ref2"])
    with pytest.raises(s.AccessDenied):
        s.set_flag(db, ids["admin"], None, False)
    with pytest.raises(s.AccessDenied):
        s.update_override(db, ids["admin"], ids["l1"], "phone", "ALLOW")


def test_search_sort_filter_and_export_never_use_forbidden_field(active):
    db, ids, cipher, *_ = active
    page = s.patient_list(db, ids["admin"], ids["org1"], cipher,
                          filter_field="first_name", filter_value="Bob")
    assert page["total"] == 0  # Bob's name is not available to admin
    page = s.patient_list(db, ids["admin"], ids["org1"], cipher,
                          filter_field="first_name", filter_value="Alice")
    assert page["total"] == 1
    assert page["items"][0]["patient_ref"] == ids["ref1"]
    page = s.patient_list(db, ids["admin"], ids["org1"], cipher, sort_field="first_name")
    assert page["total"] == 2
    assert page["items"][0]["patient_ref"] == ids["ref1"]
    exported = s.patient_list(db, ids["admin"], ids["org1"], cipher,
                              requested_fields=["first_name", "phone"])
    assert exported["total"] == 2
    lookup = {p["patient_ref"]: p["fields"] for p in exported["items"]}
    assert lookup[ids["ref1"]] == {"first_name": "Alice"}
    assert lookup[ids["ref2"]] == {"phone": "+20004445566"}
    with pytest.raises(s.InvalidInput):
        s.patient_list(db, ids["admin"], ids["org1"], cipher, sort_field="diagnosis")


def test_notifications_and_appointments_project_same_fields(active):
    db, ids, cipher, *_ = active
    future = datetime.now(timezone.utc) + timedelta(days=4)
    app = s.request_appointment(db, ids["admin"], ids["org1"], ids["ref1"], ids["doctor"], future)
    db.commit()
    appointments = s.appointment_list(db, ids["admin"], ids["org1"], cipher)
    notifications = s.notification_list(db, ids["admin"], ids["org1"], cipher)
    assert appointments["items"][0]["patient"]["fields"] == {"first_name": "Alice"}
    assert notifications["items"][0]["patient"]["fields"] == {"first_name": "Alice"}
    assert "diagnosis" not in str(appointments).lower() + str(notifications).lower()
    s.set_flag(db, ids["platform"], ids["org1"], False)
    db.commit()
    assert appointments["items"][0]["id"] == app.id
    assert s.appointment_list(db, ids["admin"], ids["org1"], cipher)["items"][0]["patient"]["fields"] == {}
    assert s.notification_list(db, ids["admin"], ids["org1"], cipher)["items"][0]["patient"]["fields"] == {}


def test_no_patient_doctor_relation_prevents_appointment(active):
    db, ids, *_ = active
    doctor_link = db.scalar(select(DoctorPatientLink).where(DoctorPatientLink.patient_id == ids["p1"]))
    doctor_link.active = False
    db.commit()
    with pytest.raises(s.AccessDenied):
        s.request_appointment(db, ids["admin"], ids["org1"], ids["ref1"], ids["doctor"],
                              datetime.now(timezone.utc) + timedelta(days=1))


def test_no_pii_without_policy_even_flag_on(active):
    db, ids, *_ = active
    db.scalar(select(AdminPiiPolicy).where(AdminPiiPolicy.patient_clinic_link_id == ids["l1"])).active = False
    db.commit()
    assert view(active)["fields"] == {}
    # Patient reference (not cross-clinic identifier) remains available.
    assert view(active)["patient_ref"] == ids["ref1"]


def test_template_new_version_not_retroactive(active):
    db, ids, cipher, *_ = active
    new = s.create_template(db, ids["platform"], ids["org1"], "names_only", 2,
                            ["first_name", "phone"])
    db.commit()
    assert view(active)["fields"] == {"first_name": "Alice"}
    s.accept_template(db, ids["p1user"], ids["l1"], new.id, True)
    db.commit()
    assert view(active)["fields"] == {"first_name": "Alice", "phone": "+10001112233"}


def test_pii_encrypted_at_rest_and_audit_excludes_values(active):
    db, ids, _, engine, _ = active
    entries = db.scalars(select(PatientFieldValue)).all()
    for entry in entries:
        assert "Alice" not in entry.encrypted_value
        assert "+10001112233" not in entry.encrypted_value
    assert all("Alice" not in str(a.__dict__) for a in db.scalars(select(AuditEvent)))


def test_module_removal_does_not_require_core_table_changes(active):
    # Proves FK direction: optional tables reference core, not the reverse.
    db, ids, _, engine, _ = active
    core = {"users", "organizations", "patients", "patient_clinic_links",
            "patient_doctor_links", "clinical_records", "patient_field_values"}
    optional = ["admin_pii_overrides", "admin_pii_policies",
                "admin_pii_template_rules", "admin_pii_templates"]
    table_names = set(inspect(engine).get_table_names())
    assert core.issubset(table_names)
    for table_name in optional:
        assert all(fk["referred_table"] not in optional for
                   name in core for fk in inspect(engine).get_foreign_keys(name))
    assert db.scalar(select(ClinicalRecord.id)) is not None
    assert db.scalar(select(DoctorPatientLink.id)) is not None


def test_membership_disabled_cuts_off_entire_admin_list(active):
    db, ids, cipher, *_ = active
    member = db.scalar(select(Membership).where(Membership.user_id == ids["admin"]))
    member.active = False
    db.commit()
    with pytest.raises(s.AccessDenied):
        s.patient_list(db, ids["admin"], ids["org1"], cipher)


def test_override_expiration(active):
    db, ids, cipher, *_ = active
    t = datetime.now(timezone.utc) + timedelta(seconds=3)
    s.update_override(db, ids["p1user"], ids["l1"], "phone", "ALLOW", t)
    db.commit()
    assert "phone" in view(active)["fields"]
    override = db.scalar(select(AdminPiiOverride).where(AdminPiiOverride.field_key == "phone"))
    override.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert "phone" not in view(active)["fields"]


def test_optional_tables_can_be_dropped_without_touching_core(active):
    from clinical_compass.models import (
        AdminPiiOverride, AdminPiiPolicy, AdminPiiTemplateRule, AdminPiiTemplate,
    )
    db, ids, _, engine, _ = active
    db.commit()
    with engine.begin() as conn:
        for model in (AdminPiiOverride, AdminPiiPolicy, AdminPiiTemplateRule, AdminPiiTemplate):
            model.__table__.drop(conn)
    remaining = set(inspect(engine).get_table_names())
    assert "clinical_records" in remaining
    assert "patient_doctor_links" in remaining
    assert "patient_field_values" in remaining
    assert "patient_clinic_links" in remaining
    assert "admin_pii_policies" not in remaining
    assert db.scalar(select(ClinicalRecord.id)) is not None
    assert db.scalar(select(DoctorPatientLink.id)) is not None


def test_each_named_identity_contact_field_independently_authorized(active):
    db, ids, cipher, *_ = active
    for field, value in (("last_name", "Smith"), ("middle_name", "Mary"),
                         ("email", "alice@example.invalid")):
        s.write_patient_field(db, ids["p1user"], field, value, cipher)
    db.commit()
    assert view(active)["fields"] == {"first_name": "Alice"}
    s.update_override(db, ids["p1user"], ids["l1"], "last_name", "ALLOW")
    s.update_override(db, ids["p1user"], ids["l1"], "email", "ALLOW")
    db.commit()
    assert view(active)["fields"] == {
        "first_name": "Alice", "last_name": "Smith", "email": "alice@example.invalid"
    }
    s.update_override(db, ids["p1user"], ids["l1"], "middle_name", "ALLOW")
    db.commit()
    assert view(active)["fields"]["middle_name"] == "Mary"
    s.update_override(db, ids["p1user"], ids["l1"], "email", "DENY")
    db.commit()
    assert "email" not in view(active)["fields"]
