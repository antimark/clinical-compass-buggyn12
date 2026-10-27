"""Public-safe v5 clinical reference INDEX. Not a decision-support or prescribing engine.

Catalog v5 release is pinned to the bundled copy. No diagnostic conclusions,
questionnaire questions, proprietary scoring, or unreviewed doses are served.
"""
from __future__ import annotations
from pathlib import Path
import json
import re
import unicodedata
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[2] / 'clinical_catalog_data' / 'v5'
VERSION = 'clinical-catalog-v5-2026-10-25'
KINDS = {'diagnosis','medicine','therapy','instrument'}
SORTS = {'relevance', 'title_asc', 'title_desc', 'code', 'updated'}


def normalized(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(value or '')).casefold().replace('ё', 'е')).strip()


def _json(path):
    with path.open(encoding='utf-8') as file:
        return json.load(file)


def _code(value):
    return str(value or '').upper().strip()


def _item(kind, identifier, title, raw, *, code='', aliases=(), relationships=(), description='', source=''):
    return {'kind': kind, 'id': str(identifier), 'title': str(title), 'code': str(code),
            'aliases': [str(a) for a in aliases if isinstance(a, str)],
            'description': str(description or ''), 'category': str(raw.get('category','')),
            'source_version': VERSION, 'source': source or 'Clinical Catalog v5',
            'updated_at': str(raw.get('last_treatment_link_update') or raw.get('instrument_version') or ''),
            'clinical_gate': 'view_only', 'relationships': list(relationships),
            'synthetic': True, 'verification': 'reference_only_not_prescribing'}


def _relations(raw, kind):
    links=[]
    if kind=='diagnosis':
        for t in raw.get('treatment_links',{}).get('therapy_methods',[]):
            if isinstance(t,dict) and t.get('therapy_id'):links.append(('therapy',str(t['therapy_id'])))
        for m in raw.get('treatment_links',{}).get('medicines_active_substances',[]):
            if isinstance(m,dict) and m.get('substance_id'):links.append(('medicine',str(m['substance_id'])))
        for q in raw.get('suggested_questionnaires',[]):
            if isinstance(q,str):links.append(('instrument',q.lower().replace('-','_')))
    elif kind in ('medicine','therapy'):
        for d in raw.get('diagnosis_links',[]):
            if isinstance(d,dict) and d.get('code'):links.append(('diagnosis',_code(d['code'])))
    elif kind=='instrument':
        for code in raw.get('diagnostic_linkage',{}).get('icd10_targets',[]):
            if isinstance(code,str):links.append(('diagnosis',_code(code)))
    return links


def is_self_assessment_eligible(raw):
    """Default deny: ui_ready or public descriptions do not prove rights/validation."""
    availability=raw.get('availability') or {}
    publication=raw.get('publication') or {}
    rights=raw.get('rights') or {}
    localization=raw.get('localization') or {}
    return bool(availability.get('usable_for_patient') is True
                and publication.get('clinical_release_approved') is True
                and publication.get('medical_review_required') is False
                and publication.get('localization_review_required') is False
                and publication.get('legal_review_required') is False
                and rights.get('digital_clearance') is True
                and rights.get('commercial_clearance') is True
                and localization.get('validated_russian') is True)


# Clinician-facing reference details. Never expose questionnaire copyrighted item text,
# scoring algorithms, or executable clinical instructions through the public catalog.
PUBLIC_SECTION_TITLES = {
    'description_clinician':'Описание для специалиста',
    'specialties':'Профильные специальности',
    'criteria':'Критерии и характеристики — справочные сведения',
    'differential_diagnosis_icd10':'Дифференциальная диагностика — проверить врачом',
    'diagnostic_workflow':'Диагностический подход — справочно',
    'red_flags':'Предупреждающие признаки',
    'icd11_context_text':'Контекст МКБ-11',
    'implementation':'Организация и проведение',
    'clinical_evidence':'Данные об эффективности и источники',
    'safety':'Безопасность и ограничения',
    'therapeutic_class':'Терапевтическая группа',
    'regulatory':'Регуляторные сведения (без гарантии актуальности)',
    'administration_instructions':'Способ применения из исходного текста',
    'adverse_event_frequency_definitions':'Частоты нежелательных явлений',
    'adverse_effects':'Нежелательные явления',
    'excipient_warnings':'Предупреждения о вспомогательных веществах',
    'special_populations':'Особые группы пациентов',
    'storage':'Хранение',
    'clinical_decision_support':'Комментарии из включённой инструкции',
    'sources':'Источники',
    'verification':'Сведения об источнике',
    'id':'Код материала',
    'schema_version':'Версия структуры данных',
    'record_type':'Тип материала',
    'international_nonproprietary_name':'Международное непатентованное наименование',
    'name_ru':'Название на русском языке',
    'description_patient':'Описание для пациента',
    'diagnosis_links':'Связанные диагнозы',
    'source_product_ids':'Связанные инструкции конкретных препаратов',
    'review':'Статус экспертной проверки',
    'review_status':'Статус проверки',
    'reviewed_by':'Кем проверено',
    'reviewed_at':'Дата проверки',
    'requires_review':'Требует проверки',
    'source_url':'Ссылка на источник',
    'source_urls':'Ссылки на источники',
    'reference_url':'Ссылка на справочный материал',
    'title':'Название',
    'name':'Название',
    'kind':'Тип',
    'url':'Адрес источника',
    'approval_status':'Статус утверждения',
    'medical_review_status':'Медицинская проверка',
    'registration_status':'Регистрационные сведения (проверить актуальность)',
    'registration_number':'Номер регистрации (по включённому источнику)',
    'product':'Конкретный препарат',
    'manufacturer':'Производитель',
    'country':'Страна',
    'strength':'Действующая дозировка в форме выпуска',
    'dosage_form':'Лекарственная форма',
    'dose_per_administration_mg':'Доза за один приём, мг (по источнику)',
    'administrations_per_day':'Число приёмов в сутки (по источнику)',
    'duration':'Длительность, указанная в источнике',
    'age_min_years':'Минимальный возраст, лет',
    'indications_and_dosing':'Показания и режимы из инструкции',
    'contraindications':'Противопоказания',
    'precautions':'Меры предосторожности',
    'drug_interactions':'Лекарственные взаимодействия',
    'language':'Язык источника',
    'source':'Источник',
}

def _plain_lines(value, prefix='', depth=0):
    """Bounded, escaped-in-UI structured prose; no HTML, scoring or inference."""
    if depth > 8 or value is None or value == '':
        return []
    if isinstance(value, bool):
        return [prefix + ('да' if value else 'нет')]
    if isinstance(value, (str, int, float)):
        return [prefix + str(value)]
    if isinstance(value, list):
        lines = []
        for x in value:
            lines.extend(_plain_lines(x, prefix, depth+1))
        return lines
    if isinstance(value, dict):
        lines = []
        for key, child in value.items():
            if key in ('questions','response_sets','scales','scoring','interpretations','scoring_blueprint_non_executable'):
                continue
            label = PUBLIC_SECTION_TITLES.get(key, key.replace('_', ' '))
            lines.extend(_plain_lines(child, prefix + label + ': ', depth+1))
        return lines
    return []

def _safe_sections(raw, fields):
    return [{'title': PUBLIC_SECTION_TITLES.get(field,field.replace('_',' ').capitalize()),
             'items': _plain_lines(raw[field])}
            for field in fields if field in raw and _plain_lines(raw[field])]

@lru_cache(maxsize=1)
def _index():
    data={}
    for path in sorted((ROOT/'diagnoses/by_code').glob('*.json')):
        raw=_json(path);code=_code(raw.get('code'))
        if not code:continue
        data[('diagnosis',code)]=_item('diagnosis',code,raw.get('title_ru',code),raw,code=code,
            aliases=raw.get('synonyms_ru') or [],description=raw.get('description_patient'),
            relationships=_relations(raw,'diagnosis'),source='WHO ICD-10 / catalog v5 (reference)')
        data[('diagnosis',code)]['reference_sections']=_safe_sections(raw, ('specialties','description_clinician','criteria','differential_diagnosis_icd10','diagnostic_workflow','red_flags','icd11_context_text'))
    for path in sorted((ROOT/'therapies/by_id').glob('*.json')):
        raw=_json(path);id=raw.get('id') or path.stem
        data[('therapy',id)]=_item('therapy',id,raw.get('title_ru',id),raw,
            relationships=_relations(raw,'therapy'),description=raw.get('description_patient'),source='Catalog v5 / guideline links pending RF review')
        data[('therapy',id)]['reference_sections']=_safe_sections(raw, ('description_clinician','implementation','clinical_evidence','safety'))
    for path in sorted((ROOT/'medicines/by_inn').glob('*.json')):
        raw=_json(path);id=raw.get('id') or path.stem
        data[('medicine',id)]=_item('medicine',id,raw.get('name_ru',id),raw,
            aliases=[raw.get('international_nonproprietary_name','')],
            relationships=_relations(raw,'medicine'),description=raw.get('description_patient'),
            source='Catalog v5 / INN summary; registration NOT verified')
        # Every present field in all active-substance summaries is preserved.
        # Source links and reviewer provenance are reference data, not approvals.
        data[('medicine',id)]['reference_sections']=_safe_sections(raw, tuple(raw.keys()))
    for path in sorted((ROOT/'medicines/source_product_instructions').glob('*.json')):
        raw=_json(path);prod=raw.get('product') or {};id='product:'+path.stem
        inn=str(prod.get('international_nonproprietary_name_latin') or '')
        aliases=[prod.get('international_nonproprietary_name',''),inn,prod.get('registration_number','')]
        med_id=next((k[1] for k,v in data.items() if k[0]=='medicine' and normalized(inn)==normalized(k[1])),None)
        links=[('medicine',med_id)] if med_id else []
        item=_item('medicine',id,prod.get('name',path.stem),raw,aliases=aliases,
            relationships=links,description='Карточка конкретного препарата. Перед применением требуется проверка действующей инструкции ГРЛС и противопоказаний.',
            source='Catalog v5 / product instruction snapshot, NOT current GRLS proof')
        item['trade_name']=prod.get('name');item['active_substance']=prod.get('international_nonproprietary_name')
        item['regulatory_identifier_unverified']=prod.get('registration_number')
        # Read-only projection of the bundled snapshot, NOT current registration proof.
        # Preserve source wording. Never calculate patient-specific regimens.
        def as_sentence(x):
            if isinstance(x,str): return x.strip()
            if isinstance(x,(int,float)) and not isinstance(x,bool):return str(x)
            return ''
        sections=[]
        ingredients=prod.get('active_substances') or []
        if isinstance(ingredients,list):
            entries=[]
            for substance in ingredients:
                if not isinstance(substance,dict):continue
                name=as_sentence(substance.get('name'))
                strength=as_sentence(substance.get('amount_per_tablet_mg'))
                entries.append(name+(' · '+strength+' мг/таблетка' if strength else ''))
            if entries:sections.append({'title':'Состав: действующие вещества','items':entries})
        indications=[]
        for instruction in raw.get('indications_and_dosing') or []:
            if not isinstance(instruction,dict):continue
            words=[as_sentence(instruction.get('diagnosis_or_condition'))]
            if instruction.get('icd10_codes'):words.append('Коды из источника: '+', '.join(map(str,instruction['icd10_codes'])))
            if instruction.get('age_min_years'):words.append('Возраст от '+str(instruction['age_min_years'])+' лет')
            # Doses are quoted as a snapshot, not used as a dose calculator.
            if instruction.get('dose_per_administration_mg'):
                words.append('По тексту источника: '+str(instruction['dose_per_administration_mg'])+' мг за приём, '+str(instruction.get('administrations_per_day','?'))+' раз/сут; врачебная проверка обязательна')
            if instruction.get('duration'):words.append('Длительность: '+as_sentence(instruction['duration']))
            indications.append('; '.join(w for w in words if w))
        if indications:sections.append({'title':'Показания и режимы из источника — не назначение','items':indications})
        for field,title in [('contraindications','Противопоказания'),('drug_interactions','Взаимодействия'),('precautions','Предупреждения')]:
            values=raw.get(field) or []
            items=[]
            for value in values if isinstance(values,list) else []:
                if isinstance(value,str):items.append(value)
                elif isinstance(value,dict):
                    parts=[]
                    for k,v in value.items():
                        if isinstance(v,str):parts.append(v)
                        elif isinstance(v,list):parts.extend(q for q in v if isinstance(q,str))
                    if parts:items.append('; '.join(parts))
            if items:sections.append({'title':title,'items':items})
        sections.extend(_safe_sections(raw, ('administration_instructions','adverse_event_frequency_definitions','adverse_effects','excipient_warnings','special_populations','storage','clinical_decision_support','sources','verification')))
        # Do not stop at selected excerpts: preserve every bundled source field,
        # including product metadata, excipients, dosing caveats and citations.
        sections.extend({'title': 'Исходные данные полностью · ' + PUBLIC_SECTION_TITLES.get(field, field.replace('_',' ')),
                         'items': _plain_lines(value)} for field,value in raw.items()
                        if _plain_lines(value))
        item['reference_sections']=sections
        item['reference_warning']='Снимок инструкции из включённого источника: проверьте актуальность по официальной инструкции и противопоказания перед применением.'

        data[('medicine',id)]=item
    for path in sorted((ROOT/'catalog/instruments').glob('*.json')):
        raw=_json(path);id=path.stem;info=raw.get('information') or {}
        title=(info.get('title') or {}).get('ru') if isinstance(info.get('title'),dict) else None
        item=_item('instrument',id,title or id.replace('_','-').upper(),raw,
            aliases=[raw.get('instrument_id','')],description=info.get('purpose_patient',''),
            relationships=_relations(raw,'instrument'),source='Catalog v5 / questionnaire metadata only')
        item['instrument_version']=str(raw.get('instrument_version',''))
        item['clinical_gate']='eligible_for_self_assessment' if is_self_assessment_eligible(raw) else 'view_only'
        item['license_note']='Публичное прохождение недоступно: не подтверждены все условия русской валидации, лицензии и клинического допуска.' if item['clinical_gate']=='view_only' else 'Подтверждён допуск к самостоятельному заполнению.'
        item['reference_sections']=_safe_sections(raw.get('information') or {}, ('purpose_patient',))
        data[('instrument',id)]=item
    # Make reciprocals ONLY to records that exist; source relationships are labels, not medical orders.
    for key,item in list(data.items()):
        for linked in item.pop('relationships'):
            if linked not in data:continue
            to=data[linked]
            item.setdefault('links',[]).append({'kind':linked[0],'id':linked[1],'title':to['title'],'status':'reference_link_requires_clinician_review'})
            to.setdefault('links',[]).append({'kind':key[0],'id':key[1],'title':item['title'],'status':'reference_link_requires_clinician_review'})
    for item in data.values():
        dedup={ (link['kind'],link['id']):link for link in item.get('links',[]) }
        item['links']=sorted(dedup.values(),key=lambda l:(l['kind'],l['title']))
    return data


def get_item(kind, identifier):
    if kind not in KINDS:return None
    return _index().get((kind,_code(identifier) if kind=='diagnosis' else identifier))


def search(*, q='', kind='', diagnosis_code='', active_substance='', category='', source='', sort='relevance',page=1,per_page=20):
    if kind and kind not in KINDS:raise ValueError('invalid_kind')
    if sort not in SORTS:raise ValueError('invalid_sort')
    if any(len(str(x))>120 for x in (q,diagnosis_code,active_substance,category,source)):raise ValueError('search_too_long')
    if not 1<=page<=100000 or not 1<=per_page<=100:raise ValueError('invalid_pagination')
    qn=normalized(q);dn=normalized(diagnosis_code);an=normalized(active_substance);cn=normalized(category);sn=normalized(source)
    is_icd_query=bool(re.fullmatch(r'[a-z][0-9]{2}(?:\.[0-9]{1,3})?',qn))
    rows=[]
    for item in _index().values():
        if kind and kind!=item['kind']:continue
        if is_icd_query and not kind and item['kind']!='diagnosis':continue
        if dn and not (normalized(item['code']).startswith(dn) if item['kind']=='diagnosis' else any(normalized(l['id']).startswith(dn) for l in item['links'] if l['kind']=='diagnosis')):continue
        if an and item['kind']=='medicine' and an not in normalized(' '.join(item['aliases']+[item.get('active_substance','')])):continue
        if an and item['kind']!='medicine':continue
        if cn and cn not in normalized(item['category']):continue
        if sn and sn not in normalized(item['source']):continue
        hay=normalized(' '.join([item['title'],item['id'],item['code'],item['description'],*item['aliases']]))
        if qn and (not item['code'].casefold().startswith(qn) if is_icd_query and item['kind']=='diagnosis' else qn not in hay):continue
        rows.append({k:v for k,v in item.items() if k not in ('reference_sections','reference_warning')})
    if sort=='title_asc':rows.sort(key=lambda x:normalized(x['title']))
    elif sort=='title_desc':rows.sort(key=lambda x:normalized(x['title']),reverse=True)
    elif sort=='code':rows.sort(key=lambda x:(x['code'] or 'ZZZ',normalized(x['title'])))
    elif sort=='updated':rows.sort(key=lambda x:x['updated_at'],reverse=True)
    else:
        def relevance(x):
            title=normalized(x['title']);code=normalized(x['code']);id=normalized(x['id'])
            return (0 if qn and (code==qn or id==qn) else 1 if qn and (code.startswith(qn) or title.startswith(qn)) else 2, title)
        rows.sort(key=relevance)
    total=len(rows);start=(page-1)*per_page
    return {'items':rows[start:start+per_page], 'total':total,'page':page,'per_page':per_page,
            'source_version':VERSION,'filters':{'q':q,'type':kind,'diagnosis_code':diagnosis_code,'active_substance':active_substance,'category':category,'source':source,'sort':sort}}
