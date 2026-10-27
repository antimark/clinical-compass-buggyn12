"""Deterministic public-safe catalog RAG and immutable, server-built citation links."""
import re
import json
from urllib.parse import quote
from .clinical_catalog_v3 import get_item, search, VERSION, ROOT
from .clinical_intelligence_sources import digest


def fragment(kind,ident):
    item=get_item(kind,ident)
    if not item or kind not in ('diagnosis','therapy','medicine'):return None
    text=item.get('description') or item['title']
    if item.get('active_substance'):
        text=item['title']+'. МНН из справочной карточки: '+item['active_substance']+'. '+text
    return dict(section_id='overview',fragment_id='overview-'+digest(text)[:20],text_digest=digest(text),
        catalog_version=item['source_version'],text=text)



def patient_reference_policy(kind,ident,item):
    """Allow only documented editorial descriptions or product metadata, never protocol/instrument bodies."""
    if kind=='diagnosis':path=ROOT/'diagnoses/by_code'/(ident.lower().replace('.','_')+'.json')
    elif kind=='therapy':path=ROOT/'therapies/by_id'/(ident+'.json')
    elif kind=='medicine' and ident.startswith('product:'):path=ROOT/'medicines/source_product_instructions'/(ident[8:]+'.json')
    else:return None
    try:raw=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError,TypeError):return None
    rights=raw.get('rights') or {};publication=raw.get('publication') or {}
    if not isinstance(rights,dict) or not isinstance(publication,dict):return None
    if publication.get('public') is False or publication.get('withdrawn') is True:return None
    if rights.get('patient_reference_allowed') is False or rights.get('redistribution')=='prohibited':return None
    if kind=='diagnosis':
        if rights.get('content')!='original_editorial_summary_not_verbatim_WHO_text' or item.get('description')!=raw.get('description_patient'):return None
        projection='original_editorial_patient_description'
    elif kind=='therapy':
        if rights.get('summary_text')!='original_editorial_summary' or item.get('description')!=raw.get('description_patient'):return None
        projection='original_editorial_patient_description_no_protocol'
    else:
        # Existing public product overview contains only factual title/MNN metadata and a server-authored caution.
        if item.get('description')!='Карточка конкретного препарата. Перед применением требуется проверка действующей инструкции ГРЛС и противопоказаний.':return None
        projection='product_metadata_and_server_caution_only'
    return dict(audience='patient',publication='public_metadata_projection',license='editorial_summary_or_metadata_only',
        license_status='clinical_use_rights_not_asserted',patient_reference_policy='patient-public-projection-v1',
        projection=projection,rights_digest=digest([rights,publication,projection]))

def citation(kind,ident,audience='doctor'):
    item=get_item(kind,ident);part=fragment(kind,ident)
    if not item or not part:return None
    cid='c_'+digest([kind,ident,part])[:24]
    result=dict(citation_id=cid,kind=kind,catalog_id=ident,title=item['title'],
        **{k:v for k,v in part.items() if k!='text'},source_status=item['verification'],
        href='/#/clinical-library/'+kind+'/'+quote(ident,safe='')+'?ci_citation='+cid,
        source=item['source'],snippet=part['text'],active_substance=item.get('active_substance'))
    if audience=='patient':
        policy=patient_reference_policy(kind,ident,item)
        if not policy:return None
        result.update(policy)
        patient_cid='c_'+digest([kind,ident,part,policy])[:24]
        result.update(citation_id=patient_cid,href='/#/clinical-library/'+kind+'/'+quote(ident,safe='')+'?ci_citation='+patient_cid)
    return result


def retrieve(question,source_text,previous=(),audience='doctor'):
    """Max three references. No instrument text, scoring or model-generated href."""
    candidates=[]
    for ref in previous:
        current=citation(ref.get('kind'),ref.get('catalog_id'),audience=ref.get('audience','doctor'))
        if current and current['citation_id']==ref.get('citation_id'):candidates.append(current)
    text=question+' '+source_text
    if re.search(r'f41|трево|генерализован',text,re.I):
        candidates.extend(filter(None,[citation('diagnosis','F41.1'),citation('therapy','cbt')]))
    if re.search(r'кпт|\bcbt\b',text,re.I):candidates.append(citation('therapy','cbt'))
    if re.search('авиандр',text,re.I):candidates.append(citation('medicine','product:aviandr_maritupirdine_instruction'))
    if not candidates:
        # Arbitrary new narratives/questions need no prepared keyword/ID whitelist.
        codes=re.findall(r'\b[a-z][0-9]{2}(?:\.[0-9]{1,3})?\b',text,re.I)
        words=[w for w in re.findall(r'[а-яёa-z]{6,}',text,re.I) if w.lower() not in {'напомни','открой','вопрос','какие','уточнить','помощь','предыдущего','ответа'}]
        queries=list(dict.fromkeys(codes+[question[:120]]+[w[:9] for w in words[:6]]))
        for query in queries:
            for item in search(q=query,per_page=3)['items']:
                ref=citation(item['kind'],item['id'])
                if ref:candidates.append(ref)
            if len(candidates)>=3:break
    unique=[]
    for item in candidates:
        if item and (item['kind'],item['catalog_id']) not in {(x['kind'],x['catalog_id']) for x in unique}:unique.append(item)
    return [ref for x in unique[:3] if (ref:=citation(x['kind'],x['catalog_id'],audience)) is not None]


def revalidate(refs):
    return all(citation(x['kind'],x['catalog_id'],audience=x.get('audience','doctor'))==x for x in refs)


def answer_supported(answer,refs):
    """Known source facts and write/dose guard, not general clinical validation."""
    medicines=[r for r in refs if r['kind']=='medicine']
    if re.search(r'(?i)\b(?:назначаю|назначьте|начните принимать|выписал|оформил направление|создал направление)\b',answer):return False
    if medicines:
        if re.search(r'(?i)\b\d+(?:[.,]\d+)?\s*(?:мг|мкг|таблет|капсул)|принимайте|дозировк',answer):return False
        if re.search(r'(?i)содерж|состав|действующ(?:ее|его) веществ|\bмнн\b',answer):
            known=[r['active_substance'] for r in medicines if r.get('active_substance')]
            if not known or not any(sub.casefold()[:8] in answer.casefold() for sub in known):return False
    return True


def patient_verified_response(refs):
    """Publish server-selected extracts, never model clinical prose. Citation alone is insufficient."""
    lines=['Экспериментальная справка. По переписке нельзя установить диагноз, подобрать препарат, дозу или оценить взаимодействия. Обсудите эти вопросы с врачом.']
    for i,ref in enumerate(refs,1):
        snippet=ref['snippet'][:420]
        lines.append(str(i)+'. '+ref['title']+': «'+snippet+'»')
    lines.append('Это общие справочные сведения; они не подтверждают наличие заболевания и не являются назначением.')
    return '\n\n'.join(lines)
