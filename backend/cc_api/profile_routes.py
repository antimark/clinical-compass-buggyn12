"""Self-owned profiles, raster lifecycle and clinic-approved public projections."""
import json
import uuid
from datetime import datetime,timedelta,timezone
from flask import abort,request,Response
from sqlalchemy import select,update,func
from .models import User,Patient
from .physician_history_models import PhysicianProfile,ProfilePhoto
from .extension_models import Audit
from .verification import workspace_enabled
from .profile_services import defaults,profile_dto,validate_profile,publication_snapshot,public_doctor
from .profile_photos import MAX_BYTES,normalize

BASE='/api/v1/profiles'


def register_profile_routes(app,SessionLocal,current_user,require_role,error,utc_now):
    def self_user(db):
        user=current_user(db)
        if not user:abort(401)
        if user.role not in ('patient','doctor'):abort(403)
        return user

    def audit(db,user,action,object_id=None):
        db.add(Audit(id=uuid.uuid4().hex,actor=user.id,action=action,object_type='profile',
            object_id=object_id or user.id,created_at=utc_now()))

    def revision(value):
        if type(value) is not int or value<0:abort(422)
        return value

    def lock_revision(db,user,expected):
        changed=db.execute(update(User).where(User.id==user.id,User.profile_revision==expected)
            .values(profile_revision=expected+1)).rowcount
        if changed!=1:abort(409,description='Профиль изменён. Загрузите актуальную версию.')
        db.refresh(user)

    def invalidate(db,user):
        row=db.get(PhysicianProfile,user.id)
        if row:row.published_json=None

    @app.before_request
    def profile_guard():
        if request.path.startswith(BASE+'/'):
            request.max_content_length=MAX_BYTES+65536
            request.max_form_parts=3
            if not workspace_enabled(app.config):return error(403,'SYNTHETIC_PROFILE_REQUIRED','Доступно только в synthetic_dev')
            if request.content_length and request.content_length>MAX_BYTES+65536:abort(413)

    @app.get(BASE+'/me')
    def profile_get():
        with SessionLocal() as db:
            user=self_user(db)
            return profile_dto(db,user),200,{'ETag':'"'+str(user.profile_revision)+'"','Cache-Control':'no-store'}

    @app.put(BASE+'/me')
    def profile_put():
        data=request.get_json(silent=True)
        if not isinstance(data,dict):abort(422)
        expected=revision(data.get('revision'))
        with SessionLocal.begin() as db:
            user=self_user(db)
            # Serialize against photo/publication too; validation errors roll back revision.
            lock_revision(db,user,expected)
            values=validate_profile(data,user)
            user.display_name=values['display_name'];user.profile_json=json.dumps(values,ensure_ascii=False)
            if user.role=='patient':
                patient=db.get(Patient,user.patient_id)
                if patient:patient.display_name=user.display_name
            if user.role=='doctor':
                physician=db.get(PhysicianProfile,user.id)
                if not physician:
                    physician=PhysicianProfile(user_id=user.id,full_name=user.display_name,synthetic=1)
                    db.add(physician)
                physician.full_name=user.display_name;physician.published_json=None
            audit(db,user,'profile.updated');db.flush()
            result=profile_dto(db,user)
        return result

    def photo_rate(user_id):
        # Count attempted uploads, including failed decoding; serialize on owner row.
        with SessionLocal.begin() as db:
            db.execute(update(User).where(User.id==user_id).values(profile_revision=User.profile_revision))
            since=(datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat().replace('+00:00','Z')
            count=db.scalar(select(func.count()).select_from(Audit).where(Audit.actor==user_id,
                Audit.action=='profile.photo.attempt',Audit.created_at>=since))
            if count>=20:abort(429)
            user=db.get(User,user_id);audit(db,user,'profile.photo.attempt')

    @app.post(BASE+'/me/photo')
    def profile_photo_post():
        if set(request.form)!={'revision'} or set(request.files)!={'file'}:abort(422)
        try:expected=int(request.form['revision'])
        except (ValueError,TypeError):abort(422)
        expected=revision(expected)
        with SessionLocal() as db:
            user=self_user(db);owner=user.id
            if user.profile_revision!=expected:abort(409)
        photo_rate(owner)
        upload=request.files['file']
        if not upload.filename or '/' in upload.filename or '\\' in upload.filename or '..' in upload.filename or len(upload.filename)>180:abort(422)
        data=upload.stream.read(MAX_BYTES+1)
        try:content=normalize(data,upload.mimetype)
        except ValueError as exc:return error(422,'INVALID_PHOTO',str(exc))
        except RuntimeError:return error(503,'PHOTO_DECODER_UNAVAILABLE','Обработка фото временно недоступна')
        with SessionLocal.begin() as db:
            user=self_user(db);lock_revision(db,user,expected)
            old=db.get(ProfilePhoto,user.profile_photo_id) if user.profile_photo_id else None
            if old:
                if old.owner_id!=user.id:abort(409)
                db.delete(old);db.flush()
            photo=ProfilePhoto(id=uuid.uuid4().hex,owner_id=user.id,content=content,created_at=utc_now())
            db.add(photo);user.profile_photo_id=photo.id;invalidate(db,user);audit(db,user,'profile.photo.saved',photo.id)
            db.flush();result=profile_dto(db,user)
        return result,201

    @app.delete(BASE+'/me/photo')
    def profile_photo_delete():
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or set(data)!={'revision'}:abort(422)
        expected=revision(data['revision'])
        with SessionLocal.begin() as db:
            user=self_user(db);lock_revision(db,user,expected)
            photo=db.get(ProfilePhoto,user.profile_photo_id) if user.profile_photo_id else None
            if photo:
                if photo.owner_id!=user.id:abort(409)
                db.delete(photo)
            user.profile_photo_id=None;invalidate(db,user);audit(db,user,'profile.photo.deleted')
            db.flush();result=profile_dto(db,user)
        return result

    @app.get(BASE+'/photos/<photo_id>')
    def profile_photo_get(photo_id):
        if len(photo_id)!=32 or any(c not in '0123456789abcdef' for c in photo_id):abort(404)
        with SessionLocal() as db:
            # Query owner metadata before selecting private image bytes.
            owner_id=db.scalar(select(ProfilePhoto.owner_id).where(ProfilePhoto.id==photo_id))
            if not owner_id:abort(404)
            owner=db.get(User,owner_id);actor=current_user(db)
            if not actor or actor.id!=owner_id:
                projection=public_doctor(db,owner)
                if not projection or projection.get('photo_url')!=BASE+'/photos/'+photo_id:abort(404)
            photo=db.get(ProfilePhoto,photo_id)
            return Response(photo.content,mimetype='image/png',headers={'Cache-Control':'no-store',
                'X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'",'Content-Disposition':'inline; filename="profile.png"'})

    @app.post(BASE+'/<user_id>/publication')
    def profile_publish(user_id):
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or set(data)!={'revision','confirmation'} or data['confirmation'] is not True:abort(422)
        expected=revision(data['revision'])
        with SessionLocal.begin() as db:
            admin=require_role(db,'clinic_admin')
            # Lock issuer authority and target, re-read both after serialization.
            for ident in sorted({admin.id,user_id}):
                db.execute(update(User).where(User.id==ident).values(profile_revision=User.profile_revision))
            db.expire_all();admin=require_role(db,'clinic_admin');user=db.get(User,user_id)
            if not user or user.role!='doctor' or user.organization_id!=admin.organization_id:abort(404)
            if user.profile_revision!=expected:abort(409)
            if not defaults(user).get('public_visibility'):abort(409)
            physician=db.get(PhysicianProfile,user.id)
            if not physician:abort(409)
            physician.published_json=json.dumps(publication_snapshot(user),ensure_ascii=False)
            audit(db,admin,'profile.publication.approved',user.id)
            return {'user_id':user.id,'revision':user.profile_revision,'publication_status':'published'}
