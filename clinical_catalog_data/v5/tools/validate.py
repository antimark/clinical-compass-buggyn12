from pathlib import Path
import json, re, sys
from jsonschema import Draft202012Validator
base=Path(__file__).resolve().parents[1]
load=lambda p: json.loads(p.read_text(encoding='utf-8'))
m=load(base/'manifest.json')
vs=Draft202012Validator(load(base/'schemas'/'clinical_catalog_v4.schema.json'))
ds=Draft202012Validator(load(base/'schemas'/'diagnosis_v1.schema.json'))
assert m['instrument_count']==len(m['instruments'])
assert len(set(x['instrument_id'] for x in m['instruments']))==len(m['instruments'])
for row in m['instruments']:
 i=load(base/row['path']);vs.validate(i)
 assert i['instrument_id']==row['instrument_id']
 assert i['rights']['license_source_url'] is not None
 assert i['publication']['clinical_release_approved'] is False
 assert i['availability']['usable_for_patient'] is False
 assert i['availability']['usable_for_clinician'] is False
 if i['questions'] and i['instrument_id'] in ('PHQ-9','PHQ-2','GAD-7','GAD-2'):
  expected=int(i['instrument_id'].split('-')[1]);assert len(i['questions'])==expected
  assert sum(max(o['score'] for o in q['options']) for q in i['questions'])==expected*3
index=load(base/'diagnoses'/'diagnoses_index.json')
assert index['diagnosis_count']==len(index['items'])
codes={x['code'] for x in index['items']}; assert len(codes)==len(index['items'])
for row in index['items']:
 d=load(base/row['path']);ds.validate(d)
 assert d['code']==row['code'] and d['review']['not_for_automated_diagnosis']
 assert d['criteria']['main_features'] and d['criteria']['exclude_and_check']
 assert not any(c.startswith('6A') or c.startswith('6B') for c in d.get('differential_diagnosis_icd10',[]))
for name in ('PHQ-9','PHQ-2','GAD-7','GAD-2'):
 assert name in {x['instrument_id'] for x in m['instruments']}
for baseid,small in (('PHQ-9','PHQ-2'),('GAD-7','GAD-2')):
 p=lambda x: base/'catalog'/'instruments'/(re.sub('[^a-z0-9]+','_',x.lower()).strip('_')+'.json')
 large=load(p(baseid));sm=load(p(small))
 assert [q['text'] for q in large['questions'][:2]]==[q['text'] for q in sm['questions']]
 assert [q['id'] for q in large['questions'][:2]]==[q['id'] for q in sm['questions']]
assert load(base/'translations'/'pending'/'pc_ptsd_5_ru_proposed.json')['clinical_use_allowed'] is False
print('PASS: instruments',len(m['instruments']),'diagnoses',len(codes),'all publication gates closed; no invented full licensed forms')
