"""Whitelisted self profile DTOs, transactional revisions and public snapshots."""
import json
import re
import uuid
from datetime import date
from urllib.parse import urlsplit, unquote
from flask import abort
from sqlalchemy import select
from .models import User
from .physician_history_models import PhysicianProfile
from .staff_enrollment_models import StaffEnrollmentInvitation
from .verification import normalize_synthetic_email

COMMON = {'display_name','bio','contact_preference'}
DOCTOR = {'public_visibility','photo_visible','specialty_label','public_contact','education','certificates','publications'}
TYPES = {'specialist','bachelor','master','residency','postgraduate','doctoral','retraining','advanced','additional','other'}


def defaults(user):
    result = {'display_name': user.display_name, 'bio':'', 'contact_preference':'in_app'}
    if user.role == 'doctor':
        result.update(public_visibility=False, photo_visible=False, specialty_label='', public_contact='',
                      education=[], certificates=[], publications=[])
    result.update(json.loads(user.profile_json))
    result['display_name'] = user.display_name
    return result


def profile_dto(db, user):
    value = defaults(user)
    published = db.get(PhysicianProfile,user.id) if user.role == 'doctor' else None
    value.update(user_id=user.id, role=user.role, revision=user.profile_revision,
        photo_id=user.profile_photo_id, photo_url='/api/v1/profiles/photos/'+user.profile_photo_id if user.profile_photo_id else None,
        publication_status='published' if published and published.published_json else 'pending' if value.get('public_visibility') else 'private')
    return value


def string(value, maximum, minimum=0):
    if not isinstance(value,str) or not minimum <= len(value.strip()) <= maximum or any(ord(c)<32 and c not in '\n\t' for c in value):
        abort(422)
    return value.strip()


def date_value(value, partial=False):
    value = string(value,10)
    if partial and re.fullmatch(r'\d{4}',value):
        year=int(value)
        if 1900<=year<=2100:return value
    if partial and re.fullmatch(r'\d{4}-\d{2}',value):
        try:date.fromisoformat(value+'-01');return value
        except ValueError:abort(422)
    try: date.fromisoformat(value)
    except ValueError: abort(422)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value) or not 1900<=int(value[:4])<=2100:abort(422)
    return value


def doi_value(value):
    value=string(value or '',200)
    if not value:return ''
    value=unquote(re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)','',value,flags=re.I)).lower()
    if not re.fullmatch(r'10\.\d{4,9}/[-._;()/:a-z0-9]+',value):abort(422)
    return value


def entries(items, key, previous):
    if not isinstance(items,list) or len(items)>20:abort(422)
    ids={entry['id'] for entry in previous}; seen=set(); result=[]
    allowed={'education':{'id','type','institution','specialization','year_from','year_to','document','status'},
        'certificates':{'id','title','issuer','issued_at','expires_at','kind','status'},
        'publications':{'id','title','journal','published_at','doi','authors','link'}}[key]
    for item in items:
        if not isinstance(item,dict) or set(item)-allowed:abort(422)
        ident=item.get('id')
        if ident:
            if not isinstance(ident,str) or ident not in ids or ident in seen:abort(422)
        else:ident=uuid.uuid4().hex
        seen.add(ident); row={'id':ident}
        if key=='education':
            kind=item.get('type');status=item.get('status','completed')
            if kind not in TYPES or status not in ('completed','in_progress','interrupted'):abort(422)
            row.update(type=kind,status=status,institution=string(item.get('institution'),180,2),
                       specialization=string(item.get('specialization',''),120),document=string(item.get('document',''),120))
            for field in ('year_from','year_to'):
                raw=item.get(field)
                if raw in ('',None) and (field=='year_from' or status=='in_progress'):row[field]=None;continue
                if isinstance(raw,str) and re.fullmatch(r'\d{4}',raw):raw=int(raw)
                if type(raw) is not int or not 1900<=raw<=2100:abort(422)
                row[field]=raw
            if row['year_from'] and row['year_to'] and row['year_from']>row['year_to']:abort(422)
        elif key=='certificates':
            if item.get('status','self_reported')!='self_reported':abort(422)
            row.update(title=string(item.get('title'),180,2),issuer=string(item.get('issuer'),180,2),
                issued_at=date_value(item.get('issued_at')),expires_at=date_value(item['expires_at']) if item.get('expires_at') else '',
                kind=string(item.get('kind','certificate'),80),status='self_reported')
            if row['expires_at'] and row['expires_at']<row['issued_at']:abort(422)
        else:
            link=string(item.get('link',''),500)
            try:parsed=urlsplit(link)
            except ValueError:abort(422)
            if link and (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in link)):abort(422)
            row.update(title=string(item.get('title'),180,2),journal=string(item.get('journal'),180,2),
                published_at=date_value(item.get('published_at'),partial=True),doi=doi_value(item.get('doi','')),
                authors=string(item.get('authors',''),500),link=link)
        result.append(row)
    return result


def validate_profile(data,user):
    if not isinstance(data,dict) or set(data)-({'revision'}|COMMON|(DOCTOR if user.role=='doctor' else set())):abort(422)
    old=defaults(user);result=dict(old)
    for field in COMMON:
        if field not in data:continue
        if field=='contact_preference':
            if data[field] not in ('in_app','email','none'):abort(422)
            result[field]=data[field]
        else:result[field]=string(data[field],100 if field=='display_name' else 1000,2 if field=='display_name' else 0)
    if user.role=='doctor':
        for field in DOCTOR:
            if field not in data:continue
            if field in ('public_visibility','photo_visible'):
                if type(data[field]) is not bool:abort(422)
                result[field]=data[field]
            elif field in ('education','certificates','publications'):result[field]=entries(data[field],field,old[field])
            elif field=='public_contact':
                try:result[field]=normalize_synthetic_email(data[field]) if data[field] else ''
                except ValueError:abort(422)
            else:result[field]=string(data[field],120)
    if len(json.dumps(result))>40000:abort(422)
    return result


def public_doctor(db,user,detail=False):
    if not user or user.role!='doctor':return None
    profile=db.get(PhysicianProfile,user.id)
    enrolled=db.scalar(select(StaffEnrollmentInvitation.id).where(StaffEnrollmentInvitation.recipient_id==user.id))
    # Preserve existing fixture/catalogue contracts; invited or edited doctors must explicitly publish.
    if user.profile_revision==0 and not enrolled:
        result={'id':user.id,'slug':user.id,'name':user.display_name,'specialty':user.specialty,
                'clinic_id':user.organization_id,'conditions':['anxiety','depressive_symptoms'],'verified':'synthetic_demo'}
    elif profile and profile.published_json and defaults(user).get('public_visibility'):
        result=json.loads(profile.published_json)
        if result.pop('revision',None)!=user.profile_revision:return None
    else:return None
    if user.id in ('doc_psy', 'doc_ther', 'doc_other') and user.profile_revision == 0:
        training = {
            'doc_psy': ('Психиатрия', 7, '2019'),
            'doc_ther': ('Психотерапия', 9, '2017'),
            'doc_other': ('Психиатрия', 5, '2021'),
        }
        specialty, years, graduation = training[user.id]
        result.update(
            specialty_label=specialty,
            experience_years=years,
            bio=f'Опыт практики в демонстрационном сценарии: {years} лет. Приём и сопровождение пациентов. Данные профиля являются учебным примером.',
            education=[{'type':'specialist','institution':'Институт синтетических данных',
                        'specialization':specialty,'year_from':str(int(graduation)-6),
                        'year_to':graduation,'status':'completed'}],
            certificates=[{'title':'Учебный сертификат по '+specialty.lower(),
                           'issuer':'Центр демонстрационных компетенций',
                           'issued_at':'2025-01-15','status':'self_reported'}],
            publications=[],
        )
    if user.organization_id=='evaluation_sandbox':
        result['verified']='self_reported'
        result['qualification_notice']='Evaluation MVP: профессиональная квалификация и email не проверены.'
        if user.profile_revision==0:result['conditions']=[]
    if detail:result['reviews']=[]
    return result


def publication_snapshot(user):
    data=defaults(user)
    return {'id':user.id,'slug':user.id,'name':user.display_name,'specialty':user.specialty,
        'specialty_label':data['specialty_label'],'clinic_id':user.organization_id,'conditions':[],
        'verified':'self_reported','qualification_notice':'Сведения представлены врачом. Профессиональная квалификация не проверена.',
        'bio':data['bio'],'public_contact':data['public_contact'],
        'education':[{k:v for k,v in row.items() if k!='document'} for row in data['education']],
        'certificates':data['certificates'],'publications':data['publications'],
        'photo_url':'/api/v1/profiles/photos/'+user.profile_photo_id if user.profile_photo_id and data['photo_visible'] else None,
        'revision':user.profile_revision}
