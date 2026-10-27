"""Offline catalog coverage/sanitization regressions; no Flask required."""
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
CAT = runpy.run_path(str(ROOT / 'backend/cc_api/clinical_catalog_v3.py'))

def test_all_bundled_catalog_entries_are_reachable():
    search = CAT['search']
    assert search()['total'] == 242
    assert {k:search(kind=k)['total'] for k in ('diagnosis','therapy','medicine','instrument')} == {
        'diagnosis':77, 'therapy':58, 'medicine':77, 'instrument':30}
    assert search(q='F41.1')['total'] >= 1
    assert search(kind='medicine', q='сертралин')['total'] >= 1

def test_diagnosis_therapy_and_full_eight_drug_reference_details():
    get_item = CAT['get_item']
    assert get_item('diagnosis','F41.1')['reference_sections']
    assert get_item('therapy','cbt')['reference_sections']
    source = ROOT / 'clinical_catalog_data/v5/medicines/source_product_instructions'
    for path in source.glob('*.json'):
        item = get_item('medicine','product:' + path.stem)
        assert item is not None and item['reference_sections']
        titles = [sec['title'] for sec in item['reference_sections']]
        assert 'Показания и режимы из источника — не назначение' in titles
        assert 'Нежелательные явления' in titles

def test_unapproved_licensed_scales_never_expose_item_text_through_v5():
    get_item = CAT['get_item']
    for path in (ROOT/'clinical_catalog_data/v5/catalog/instruments').glob('*.json'):
        item=get_item('instrument',path.stem)
        assert item and item['clinical_gate'] in ('view_only','eligible_for_self_assessment')
        assert 'questions' not in item and 'scoring' not in item
        for section in item['reference_sections']:
            assert 'scoring_' not in str(section)
