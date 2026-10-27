"""Small, additive P1 read-only supporting screens; synthetic demo only.

No role elevation, clinical content, identity vault or admin PII is exposed.
"""
from flask import abort
from sqlalchemy import select
from .models import User


def register_p1_routes(app, SessionLocal, require_role):
    @app.get('/api/v1/p1/clinic/staff')
    def p1_clinic_staff():
        with SessionLocal() as db:
            admin = require_role(db, 'clinic_admin')
            staff = db.scalars(select(User).where(
                User.organization_id == admin.organization_id,
                User.role.in_(['doctor', 'clinic_admin']),
            ).order_by(User.role, User.id))
            return {'items': [
                {'user_ref': u.id, 'display_name': u.display_name, 'role': u.role, 'specialty': u.specialty,
                 'credential_status': 'not_verified_in_prototype'} for u in staff
            ], 'scope': 'organization_only', 'synthetic_only': True,
            'limitation': 'Staff credentials, affiliations, MFA and invitations require separate verification'}
