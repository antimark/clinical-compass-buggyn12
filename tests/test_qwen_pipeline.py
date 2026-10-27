"""Offline regressions for local wire parsing, exact spans and explicit fallback."""
import json
from urllib.error import HTTPError, URLError
from dataclasses import replace
import pytest
from cc_api.nlp_lab_routes_v3 import specs
from cc_nlp.models import SourceRecord, ProcessingAuthorization
from cc_nlp.providers.ollama import LocalOllamaProvider
from cc_nlp.pipeline import analyze
from cc_nlp.errors import ValidationRejected
from auth_support import login_response
from test_onboarding import app

SOURCE = SourceRecord('synthetic', 1, 'clinician_note', '😀 е\u0301. Плохо  сплю.\n', 'shared_with_care_team', 'clinician')
AUTH = ProcessingAuthorization('doctor', True)

def wire(quote='Плохо  сплю'):
    catalog, _ = specs()
    tag = next(t['code'] for t in catalog['tags'] if t['enabled_for_llm'])
    return {'facts': [{'tag_code':tag, 'assertion':'asserted','temporality':'current',
                      'evidence':{'quote':quote}, 'speaker':'patient','review_status':'proposed'}],
            'missing_information':[]}


def fake_http(monkeypatch, content=None, error=None, outer=None):
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,n): return (outer if outer is not None else json.dumps({'message':{'content':content}},ensure_ascii=False).encode())
    class Opener:
        def open(self,*args,**kwargs):
            if error: raise error
            return Response()
    monkeypatch.setattr('cc_nlp.providers.ollama.build_opener',lambda *args: Opener())


def run(source=SOURCE, provider=None):
    return analyze(source, AUTH, provider or LocalOllamaProvider(model='qwen3:4b-instruct'), catalog=specs()[0],schema=specs()[1])


def test_exact_quote_offsets_are_python_codepoints_without_normalization(monkeypatch):
    fake_http(monkeypatch,json.dumps(wire(),ensure_ascii=False))
    result=run()
    assert result.error_code is None
    ev=result.result['facts'][0]['evidence']
    assert ev=={'quote':'Плохо  сплю','start':6,'end':17}
    assert SOURCE.body_text[ev['start']:ev['end']]==ev['quote']


@pytest.mark.parametrize('quote,source,code',[
    ('Плохо сплю',SOURCE,'evidence_quote_absent'),
    ('é',SOURCE,'evidence_quote_absent'),
    ('сплю',replace(SOURCE,body_text='сплю и сплю'),'evidence_quote_ambiguous'),
    ('SECRET_SOURCE_SENTINEL',SOURCE,'evidence_quote_absent'),
])
def test_changed_or_ambiguous_quotes_rejected(monkeypatch,quote,source,code):
    fake_http(monkeypatch,json.dumps(wire(quote),ensure_ascii=False))
    result=run(source)
    assert result.error_code==code and result.result['facts']==[]
    assert result.error_stage=='evidence_validation'


def test_incorrect_offsets_still_rejected():
    class Wrong:
        name='local_llm';model_id='fixture'
        def extract(self,*args):
            result=wire();result['facts'][0]['evidence'].update(start=0,end=2)
            return result
    result=run(provider=Wrong())
    assert result.error_code=='evidence_offset_mismatch' and not result.result['facts']


@pytest.mark.parametrize('content,error,outer,code,stage',[
    ('not JSON SECRET_SOURCE_SENTINEL',None,None,'invalid_model_json','json_parsing'),
    ('{}',None,None,'invalid_provider_payload','schema_validation'),
    (None,None,b'no JSON','invalid_ollama_response','json_parsing'),
    (None,HTTPError('http://127.0.0.1',404,'missing',{},None),None,'model_unavailable','generation'),
    (None,URLError('SECRET_SOURCE_SENTINEL'),None,'local_transport_failure','generation'),
])
def test_failure_diagnostics_are_bounded(monkeypatch,content,error,outer,code,stage):
    fake_http(monkeypatch,content,error,outer)
    result=run()
    assert result.error_code==code and result.error_stage==stage
    assert result.elapsed_ms>=0 and not result.result['facts']
    assert 'SECRET_SOURCE_SENTINEL' not in repr(result)


def test_wire_rejects_model_supplied_offsets(monkeypatch):
    payload=wire();payload['facts'][0]['evidence'].update(start=0,end=2)
    fake_http(monkeypatch,json.dumps(payload))
    assert run().error_code=='invalid_provider_payload'


def test_route_modes_csrf_acl_and_primary_failure(app,monkeypatch,caplog):
    import logging
    caplog.set_level(logging.INFO, logger='cc_api.nlp_lab_routes_v3')
    client=app.test_client();token=login_response(client,'doc_psy').json['csrf_token']
    path='/api/v1/nlp-v3/synthetic-extract';payload={'text':SOURCE.body_text,'synthetic':True}
    assert client.post(path,json=payload).status_code==403
    def post(): return client.post(path,json=payload,headers={'X-CSRF-Token':token}).json
    monkeypatch.setenv('CC_NLP_V3_PROVIDER','mock')
    assert post()['mode']=='deterministic_mock'
    monkeypatch.setenv('CC_NLP_V3_PROVIDER','ollama');monkeypatch.setenv('CC_NLP_V3_MODEL','qwen3:4b-instruct')
    fake_http(monkeypatch,json.dumps(wire(),ensure_ascii=False))
    good=post();assert good['mode']=='local_llm' and good['fallback_used'] is False and good['data']['facts']
    fake_http(monkeypatch,error=HTTPError('http://127.0.0.1',404,'missing',{},None))
    fallback=post()
    assert fallback['mode']=='deterministic_mock_fallback' and fallback['fallback_used']
    assert fallback['error_code']=='model_unavailable'
    assert fallback['diagnostics']['model_id']=='qwen3:4b-instruct'
    assert fallback['diagnostics']['stage']=='generation'
    for content,code in [('SECRET_SOURCE_SENTINEL','invalid_model_json'),
                         (json.dumps(wire('SECRET_SOURCE_SENTINEL')),'evidence_quote_absent')]:
        fake_http(monkeypatch,content=content)
        rejected=post()
        assert rejected['mode']=='deterministic_mock_fallback' and rejected['fallback_used']
        assert rejected['error_code']==code
        assert rejected['data']['provider']=='deterministic_mock'
    assert 'body_text' not in json.dumps(fallback['diagnostics'])
    assert 'synthetic_nlp_pipeline' in caplog.text
    assert SOURCE.body_text not in caplog.text
    token=login_response(client,'pat_01').json['csrf_token']
    assert client.post(path,json=payload,headers={'X-CSRF-Token':token}).status_code==403


def test_unknown_provider_error_never_exposes_source():
    from cc_nlp.errors import ProviderUnavailable
    class Unsafe:
        name='local_llm'; model_id='fixture'
        def extract(self,*args): raise ProviderUnavailable('SECRET_SOURCE_SENTINEL')
    result=run(provider=Unsafe())
    assert result.error_code=='analysis_failure'
    assert 'SECRET_SOURCE_SENTINEL' not in repr(result)


def test_transport_timeout_has_safe_specific_diagnostic(monkeypatch):
    fake_http(monkeypatch,error=TimeoutError('PRIVATE_TIMEOUT_SENTINEL'))
    result=run()
    assert result.error_code=='local_timeout' and result.error_stage=='generation'
    assert not result.result['facts'] and 'PRIVATE_TIMEOUT_SENTINEL' not in repr(result)


def test_generation_schema_offers_only_exact_source_excerpts(monkeypatch):
    observed={}
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return json.dumps({'message':{'content':json.dumps(wire())}}).encode()
    class Opener:
        def open(self,request,**kwargs):
            observed.update(json.loads(request.data));return Response()
    monkeypatch.setattr('cc_nlp.providers.ollama.build_opener',lambda *args:Opener())
    result=run();assert result.error_code is None
    choices=observed['format']['properties']['facts']['items']['properties']['evidence']['properties']['quote']['enum']
    assert choices and all(SOURCE.body_text.count(quote)==1 for quote in choices)
    assert observed['options']['temperature']==0
