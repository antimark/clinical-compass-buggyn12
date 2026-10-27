"""Additive PUBLIC read-only catalog endpoints; fail closed on unsupported actions."""
from flask import request
from .clinical_catalog_v3 import search, get_item

def register_clinical_catalog_routes_v3(app):
    @app.get('/api/v1/clinical-catalog/search')
    def catalog_v3_search():
        args=request.args
        try:
            return search(q=args.get('q',''),kind=args.get('type',''),
                diagnosis_code=args.get('diagnosis_code',''),active_substance=args.get('active_substance',''),
                category=args.get('category',''),source=args.get('source',''),
                sort=args.get('sort','relevance'),page=int(args.get('page',1)),per_page=int(args.get('per_page',20)))
        except (ValueError, TypeError):
            return {'error':{'code':'INVALID_SEARCH','message':'Недопустимые параметры поиска'}},422

    @app.get('/api/v1/clinical-catalog/<kind>/<path:identifier>')
    def catalog_v3_detail(kind,identifier):
        item=get_item(kind,identifier)
        if item is None:return {'error':{'code':'NOT_FOUND','message':'Материал не найден'}},404
        from .copilot_catalog import fragment
        item = dict(item)
        part=fragment(kind,identifier)
        if part:item['reference_fragment']=part
        return item

    @app.get('/api/v1/clinical-catalog/instruments/<identifier>/eligibility')
    def catalog_v3_eligibility(identifier):
        item=get_item('instrument',identifier)
        if item is None:return {'error':{'code':'NOT_FOUND','message':'Опросник не найден'}},404
        return {'instrument_id':identifier,'instrument_version':item['instrument_version'],
                'status':item['clinical_gate'],'reason':item.get('license_note',''),
                'patient_self_assessment':item['clinical_gate']=='eligible_for_self_assessment',
                'source_version':item['source_version']}

    @app.get('/api/v1/clinical-catalog/<kind>/<path:identifier>/fragments/<citation_id>')
    def catalog_verified_fragment(kind,identifier,citation_id):
        from .copilot_catalog import citation,fragment
        candidates=[citation(kind,identifier),citation(kind,identifier,audience='patient')]
        current=next((item for item in candidates if item and item['citation_id']==citation_id),None)
        if not current:
            return {'valid':False,'reason':'source_changed_or_unavailable'}
        return {'valid':True,**fragment(kind,identifier)}
