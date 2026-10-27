"""Clinic invitation -> actual OIDC/MFA candidate -> explicit synthetic enrollment.

No self-appointed staff role, local password identity, automatic patient link or
production professional verification is created by these routes.
"""
import hashlib
import secrets
import uuid
from datetime import timedelta
from flask import abort, request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .models import User
from .extension_models import Audit
from .onboarding_models import StaffVerification
from .oidc_browser import browser_user, now, stamp
from .staff_enrollment_models import StaffEnrollmentInvitation
from .staff_enrollment_services import invited_enrollment_enabled, SyntheticInvitedProfessionalVerifier
from .verification import normalize_synthetic_email

BASE='/api/v1/staff-enrollment'
SPECIALTIES={'psychiatry','psychotherapy'}


def register_staff_enrollment_routes(app, SessionLocal, current_user, require_role, error, utc_now):
    def enabled():
        if not invited_enrollment_enabled(app.config):
            abort(403)

    def body(keys):
        value=request.get_json(silent=True)
        if not isinstance(value,dict) or set(value)-set(keys):
            abort(422)
        return value

    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def audit(db, actor, action, row):
        db.add(Audit(id=uuid.uuid4().hex,actor=actor.id,action=action,
            object_type='staff_invitation',object_id=row.id,created_at=stamp(now())))

    def lock_users(db, *ids):
        for uid in sorted(set(ids)):
            db.execute(update(User).where(User.id==uid).values(role=User.role))
        db.expire_all()

    def clinic_issuer(db):
        actor=require_role(db,'clinic_admin')
        lock_users(db,actor.id)
        actor=db.get(User,actor.id,populate_existing=True)
        if not actor or actor.role!='clinic_admin':
            abort(403)
        return actor

    def candidate(db):
        actor=browser_user(db)
        if not actor:
            abort(401)
        selected=current_user(db)
        if request.headers.get('Authorization') or not selected or selected.id!=actor.id:
            abort(403)
        return actor

    def payload(row, recipient=None):
        state='accepted' if row.accepted_at else 'revoked' if row.revoked_at else 'expired' if row.expires_at<=stamp(now()) else 'pending'
        result={'id':row.id,'organization_id':row.organization_id,'specialty':row.specialty,
            'state':state,'created_at':row.created_at,'expires_at':row.expires_at,
            'accepted_at':row.accepted_at,'revoked_at':row.revoked_at,
            'synthetic_environment':True,'real_professional_verification':False}
        if recipient:
            result['recipient']={'id':recipient.id,'display_name':recipient.display_name}
            if recipient.role=='doctor':
                from .profile_services import defaults
                # Publication metadata only, never private profile fields in the clinic list.
                result['recipient']['profile_revision']=recipient.profile_revision
                result['recipient']['publication_requested']=defaults(recipient).get('public_visibility',False)

        return result

    @app.get(BASE+'/capabilities')
    def staff_capabilities():
        return {'synthetic_invited_enrollment_enabled':invited_enrollment_enabled(app.config),
            'verified_staff_enrollment_enabled':False,'mfa_required':True,
            'specialties':sorted(SPECIALTIES),'self_appointed_roles':False,
            'real_email_verification':'deferred_by_product_decision',
            'real_professional_verification':'deferred_by_product_decision'}

    @app.post(BASE+'/invitations')
    def staff_invite():
        enabled();data=body(('recipient_email','display_name','external_subject','specialty','ttl_hours'))
        try:
            email=normalize_synthetic_email(data.get('recipient_email'))
        except ValueError:
            abort(422)
        subject=data.get('external_subject');name=data.get('display_name');specialty=data.get('specialty')
        ttl=data.get('ttl_hours',24)
        if (not isinstance(subject,str) or not 1<=len(subject)<=200 or subject!=subject.strip()
                or any(ord(value)<32 for value in subject) or not isinstance(name,str)
                or not 2<=len(name.strip())<=100 or specialty not in SPECIALTIES
                or type(ttl) is not int or not 1<=ttl<=168):
            abort(422)
        token=secrets.token_urlsafe(40);created=now()
        try:
            with SessionLocal.begin() as db:
                issuer=clinic_issuer(db)
                if db.scalar(select(User.id).where(User.external_subject==subject)):
                    return error(409,'STAFF_SUBJECT_EXISTS','Учётная запись уже существует; её роль не изменена')
                user=User(id='staff_'+uuid.uuid4().hex,display_name=name.strip(),role='staff_candidate',
                    specialty=None,organization_id=issuer.organization_id,external_subject=subject)
                db.add(user);db.flush()
                row=StaffEnrollmentInvitation(id='sei_'+uuid.uuid4().hex,token_hash=digest(token),
                    issuer_id=issuer.id,recipient_id=user.id,recipient_email_hash=digest(email),
                    organization_id=issuer.organization_id,specialty=specialty,created_at=stamp(created),
                    expires_at=stamp(created+timedelta(hours=ttl)))
                db.add(row);db.flush();audit(db,issuer,'staff.invitation.created',row)
                result=payload(row,user)
            return {**result,'token':token,'url':'/#/register/specialist?token='+token,
                'authority':'clinic_admin_invitation','credentials_provider':'synthetic_invited_auto'},201
        except IntegrityError:
            return error(409,'STAFF_SUBJECT_EXISTS','Учётная запись уже существует; её роль не изменена')

    @app.get(BASE+'/invitations')
    def staff_invitation_list():
        enabled()
        with SessionLocal() as db:
            issuer=require_role(db,'clinic_admin')
            rows=db.scalars(select(StaffEnrollmentInvitation).where(
                StaffEnrollmentInvitation.issuer_id==issuer.id,
                StaffEnrollmentInvitation.organization_id==issuer.organization_id).order_by(StaffEnrollmentInvitation.created_at.desc())).all()
            return {'items':[payload(row,db.get(User,row.recipient_id)) for row in rows]}

    @app.get(BASE+'/invitation')
    def staff_invitation_preview_get_disabled():
        return error(400,'TOKEN_IN_BODY_REQUIRED','Передайте приглашение в защищённом POST-запросе')

    @app.post(BASE+'/preview')
    def staff_invitation_preview():
        enabled();token=body(('token',)).get('token')
        if not isinstance(token,str) or not 20<=len(token)<=200:
            abort(404)
        with SessionLocal() as db:
            actor=candidate(db)
            row=db.scalar(select(StaffEnrollmentInvitation).where(StaffEnrollmentInvitation.token_hash==digest(token)))
            if not row or row.recipient_id!=actor.id or row.organization_id!=actor.organization_id:
                abort(404)
            return {'invitation':payload(row,actor),'requires_explicit_acceptance':True,
                'professional_provider':{'status':'synthetic_pending','real_verification':False}}

    @app.post(BASE+'/accept')
    def staff_accept():
        enabled();data=body(('token','accept'))
        token=data.get('token')
        if not isinstance(token,str) or not 20<=len(token)<=200 or data.get('accept') is not True:
            abort(422)
        with SessionLocal.begin() as db:
            actor=candidate(db)
            row=db.scalar(select(StaffEnrollmentInvitation).where(StaffEnrollmentInvitation.token_hash==digest(token)))
            if not row or row.recipient_id!=actor.id or row.organization_id!=actor.organization_id:
                abort(404)
            lock_users(db,actor.id,row.issuer_id)
            actor=candidate(db)
            row=db.get(StaffEnrollmentInvitation,row.id,populate_existing=True)
            issuer=db.get(User,row.issuer_id)
            if not issuer or issuer.role!='clinic_admin' or issuer.organization_id!=row.organization_id or actor.organization_id!=row.organization_id:
                abort(403)
            if row.accepted_at or row.revoked_at:
                return error(409,'STAFF_INVITATION_CONSUMED','Приглашение уже использовано или отозвано')
            timestamp=stamp(now())
            if row.expires_at<=timestamp:
                return error(410,'STAFF_INVITATION_EXPIRED','Срок приглашения истёк')
            if actor.role!='staff_candidate':
                abort(409)
            status=SyntheticInvitedProfessionalVerifier().verify(db,actor,app.config)
            changed=db.execute(update(StaffEnrollmentInvitation).where(
                StaffEnrollmentInvitation.id==row.id,StaffEnrollmentInvitation.accepted_at.is_(None),
                StaffEnrollmentInvitation.revoked_at.is_(None),StaffEnrollmentInvitation.expires_at>timestamp
            ).values(accepted_at=timestamp)).rowcount
            if changed!=1:
                abort(409)
            changed=db.execute(update(User).where(User.id==actor.id,User.role=='staff_candidate',
                User.organization_id==row.organization_id).values(role='doctor',specialty=row.specialty)).rowcount
            if changed!=1:
                abort(409)
            db.add(StaffVerification(user_id=actor.id,provider=status['provider'],status=status['status'],verified_at=timestamp))
            audit(db,actor,'staff.invitation.accepted',row)
            row=db.get(StaffEnrollmentInvitation,row.id,populate_existing=True)
            return {'invitation':payload(row,actor),'context':{'role':'doctor','specialty':row.specialty,
                'organization_id':row.organization_id},'professional_verification':status,
                'role_authority':'clinic_admin_invitation','patient_links_created':0}

    @app.post(BASE+'/invitations/<invitation_id>/revoke')
    def staff_revoke(invitation_id):
        enabled();body(())
        with SessionLocal.begin() as db:
            issuer=clinic_issuer(db)
            row=db.get(StaffEnrollmentInvitation,invitation_id)
            if not row or row.issuer_id!=issuer.id or row.organization_id!=issuer.organization_id:
                abort(404)
            changed=db.execute(update(StaffEnrollmentInvitation).where(
                StaffEnrollmentInvitation.id==row.id,StaffEnrollmentInvitation.accepted_at.is_(None),
                StaffEnrollmentInvitation.revoked_at.is_(None)).values(revoked_at=stamp(now()))).rowcount
            if changed!=1:
                return error(409,'STAFF_INVITATION_CONSUMED','Приглашение уже использовано или отозвано')
            audit(db,issuer,'staff.invitation.revoked',row)
            return {'invitation':payload(db.get(StaffEnrollmentInvitation,row.id,populate_existing=True))}
