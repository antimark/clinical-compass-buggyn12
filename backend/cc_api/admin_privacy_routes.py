"""Optional privacy API, using existing authentication, CSRF and tenant authority."""
from functools import wraps
from flask import abort, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .models import User
from .admin_privacy_models import AdminPrivacyFlag
from . import admin_privacy_service as s

BASE = '/api/v1/admin-privacy'


def register_admin_privacy_routes(app, SessionLocal, current_user, require_role, error, utc_now):
    @app.errorhandler(s.PrivacyFailure)
    def privacy_error(exc):
        return error(exc.status, exc.code, exc.message)

    @app.after_request
    def privacy_no_store(response):
        if request.path.startswith(BASE + '/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def mutation(fn):
        @wraps(fn)
        def guarded(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except IntegrityError:
                return error(409, 'PRIVACY_CONFLICT', 'Данные изменились; обновите страницу')
        return guarded

    def actor(db):
        row = current_user(db)
        if not row:
            abort(401)
        return row

    def body(keys):
        value = request.get_json(silent=True)
        if not isinstance(value, dict) or set(value) - set(keys):
            abort(422)
        return value

    def list_options():
        result = {k: request.args.get(k) for k in ('filter_field', 'filter_value', 'sort_field')}
        try:
            result.update(offset=int(request.args.get('offset', '0')), limit=int(request.args.get('limit', '50')))
        except ValueError:
            abort(422)
        if 'fields' in request.args:
            result['requested_fields'] = request.args['fields'].split(',') if request.args['fields'] else []
        return result

    @app.get(BASE + '/capabilities')
    def privacy_capabilities():
        with SessionLocal() as db:
            user = actor(db)
            return {'available': user.role in ('patient', 'platform_admin', 'clinic_admin'),
                    'fields': [{'key': k, 'label': v} for k, v in s.FIELDS.items()],
                    'clinical_access': False}

    @app.get(BASE + '/flags')
    def privacy_flags():
        with SessionLocal() as db:
            user = actor(db)
            if user.role == 'platform_admin':
                return {'items': [{'scope': x.scope, 'enabled': x.enabled}
                                  for x in db.scalars(select(AdminPrivacyFlag).order_by(AdminPrivacyFlag.scope)).all()],
                        'default_enabled': False}
            user = s.clinic_actor(db, user)
            return s.flag_state(db, user.organization_id)

    @app.patch(BASE + '/flags')
    @mutation
    def privacy_set_flag():
        data = body(('organization_id', 'enabled'))
        with SessionLocal.begin() as db:
            s.set_flag(db, actor(db), data.get('organization_id'), data.get('enabled'))
        return {'saved': True}

    @app.get(BASE + '/templates')
    def privacy_templates():
        with SessionLocal() as db:
            user = actor(db)
            if user.role == 'platform_admin':
                org = request.args.get('organization_id', '')
            elif user.role == 'clinic_admin':
                org = s.clinic_actor(db, user).organization_id
            else:
                abort(403)
            return {'items': s.templates(db, org)}

    @app.post(BASE + '/templates')
    @mutation
    def privacy_create_template():
        data = body(('organization_id', 'template_key', 'version', 'read_fields'))
        with SessionLocal.begin() as db:
            result = s.create_template(db, actor(db), data.get('organization_id'), data.get('template_key'),
                data.get('version'), data.get('read_fields'))
        return result, 201

    @app.get(BASE + '/me/clinics')
    def privacy_own_clinics():
        with SessionLocal() as db:
            user = s.own_patient(db, actor(db))
            org = user.organization_id
            active = s.relationship(db, user, org)
            # Include a withdrawn relationship's policy so the patient can revoke it.
            policy = s.policy_payload(db, user, org)
            return {'items': ([{'organization_id': org, 'relationship_active': active,
                'templates': s.templates(db, org) if active else [], 'policy': policy,
                'feature': s.flag_state(db, org)}] if active or policy else [])}

    @app.get(BASE + '/me/values')
    def privacy_own_values():
        with SessionLocal() as db:
            return {'fields': s.own_values(db, actor(db))}

    @app.put(BASE + '/me/values')
    @mutation
    def privacy_write_values():
        data = body(('fields',))
        with SessionLocal.begin() as db:
            result = s.write_values(db, actor(db), data.get('fields'))
        return result

    @app.put(BASE + '/me/policies/<organization_id>')
    @mutation
    def privacy_accept(organization_id):
        data = body(('template_id', 'confirmed', 'revision'))
        with SessionLocal.begin() as db:
            result = s.accept_policy(db, actor(db), organization_id, data.get('template_id'),
                data.get('confirmed'), data.get('revision'))
        return result

    @app.delete(BASE + '/me/policies/<organization_id>')
    @mutation
    def privacy_revoke(organization_id):
        with SessionLocal.begin() as db:
            result = s.revoke_policy(db, actor(db), organization_id)
        return result

    @app.put(BASE + '/me/policies/<organization_id>/overrides/<field_key>')
    @mutation
    def privacy_override(organization_id, field_key):
        data = body(('effect', 'expires_at', 'revision'))
        with SessionLocal.begin() as db:
            result = s.update_override(db, actor(db), organization_id, field_key, data.get('effect'),
                data.get('expires_at'), data.get('revision'))
        return result

    @app.get(BASE + '/patients')
    @app.get(BASE + '/patients/export')
    def privacy_patients():
        options = list_options()
        with SessionLocal.begin() as db:
            return s.projected_patients(db, actor(db), app.config['SECRET_KEY'], **options)

    @app.get(BASE + '/patients/<patient_ref>')
    def privacy_patient(patient_ref):
        with SessionLocal.begin() as db:
            user = s.clinic_actor(db, actor(db))
            person = s.patient_by_ref(db, user, patient_ref, app.config['SECRET_KEY'])
            return s.projected_patient(db, user, person, app.config['SECRET_KEY'])

    @app.get(BASE + '/appointments')
    def privacy_appointments():
        with SessionLocal.begin() as db:
            return s.projected_appointments(db, actor(db), app.config['SECRET_KEY'])

    @app.get(BASE + '/notices')
    def privacy_notices():
        with SessionLocal.begin() as db:
            return s.projected_notices(db, actor(db), app.config['SECRET_KEY'])
