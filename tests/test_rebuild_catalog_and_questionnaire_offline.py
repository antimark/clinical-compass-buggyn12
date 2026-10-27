"""Offline regressions for evaluator navigation and catalog projection (no Flask needed)."""
import json
import runpy
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
CAT=runpy.run_path(str(ROOT/'backend/cc_api/clinical_catalog_v3.py'))
FORMS=runpy.run_path(str(ROOT/'backend/cc_api/demo_questionnaires.py'))

@pytest.mark.parametrize('kind,count',[('diagnosis',77),('medicine',77),('therapy',58),('instrument',30)])
def test_every_catalog_material_opens_and_crosslinks_resolve(kind,count):
    rows=[]
    for page in range(1,4):rows.extend(CAT['search'](kind=kind,page=page,per_page=50)['items'])
    assert len(rows)==count
    for record in rows:
        item=CAT['get_item'](kind,record['id'])
        assert item is not None and item['id']==record['id']
        for related in item.get('links',[]):
            assert CAT['get_item'](related['kind'],related['id']) is not None

@pytest.mark.parametrize('source',[ROOT/'clinical_catalog_data/v5/medicines/by_inn',ROOT/'clinical_catalog_data/v5/medicines/source_product_instructions'])
def test_every_present_medicine_source_field_survives_reference_projection(source):
    def scalar_leaves(value):
        if value is None or value=='':return []
        if isinstance(value,bool):return []  # displayed in Russian as да/нет
        if isinstance(value,(int,float,str)):return [str(value)]
        if isinstance(value,list):return [s for child in value for s in scalar_leaves(child)]
        if isinstance(value,dict):return [s for child in value.values() for s in scalar_leaves(child)]
        return []
    for path in source.glob('*.json'):
        raw=json.loads(path.read_text(encoding='utf-8'))
        item=CAT['get_item']('medicine', ('product:' if path.parent.name=='source_product_instructions' else '')+path.stem)
        assert item, path
        lines='\n'.join(str(line) for section in item['reference_sections'] for line in section['items'])
        for field,value in raw.items():
            for scalar in scalar_leaves(value):
                assert scalar in lines,(path.name,field,scalar)

@pytest.mark.parametrize('identifier,expected_len,maximum',[('phq_9',9,27),('phq_2',2,6),('gad_7',7,21),('gad_2',2,6)])
def test_four_draft_scales_have_questions_and_server_sum_without_diagnosis(identifier,expected_len,maximum):
    definition=next(d for d in FORMS['evaluation_definitions']() if d['source_id']==identifier)
    assert definition['status']=='evaluation_draft_unapproved'
    assert len(definition['questions'])==expected_len
    assert definition['min_score']==0 and definition['max_score']==maximum
    assert FORMS['score_answers'](definition,{q['id']:0 for q in definition['questions']})==0
    assert FORMS['score_answers'](definition,{q['id']:3 for q in definition['questions']})==maximum
    with pytest.raises(ValueError):FORMS['score_answers'](definition,{})
    with pytest.raises(ValueError):FORMS['score_answers'](definition,{q['id']:4 for q in definition['questions']})
    public=CAT['get_item']('instrument',identifier)
    assert 'questions' not in public and 'scoring' not in public
    assert public['clinical_gate']=='view_only'

def test_new_frontend_routes_and_actions_have_assessment_and_catalog_navigation():
    routes=json.loads((ROOT/'frontend/dist/assets/data/routes.json').read_text())
    paths={r['path'] for r in routes}
    assert len(paths)>=98
    assert {'/patient/assistant/thread/:threadId','/doctor/patients/:patientId/clinical-intelligence','/doctor/patients/:patientId/clinical-intelligence/chat/:threadId'}<=paths
    assert {'/patient/tasks','/patient/questionnaires/:requestId','/patient/questionnaires/:requestId/result','/clinical-library'}<=paths
    js=(ROOT/'frontend/dist/assets/js/main.js').read_text()
    views=(ROOT/'frontend/dist/assets/js/views.js').read_text()
    assert 'start-assessment' in js and '/questionnaires/self-assign' in js
    assert "input[data-answer]:checked" in js
    assert 'data-command="start-assessment"' in views
    assert 'Страница ${page} из ${pages}' in views
    assert 'catalogHref({item:l.kind+' in views
