"""v0.2 synthetic-only NLP adapter. Not clinical workflow, never writes to chart.

This route deliberately accepts only self-contained *declared synthetic* test prose,
not patient IDs or real encounter references. Importing patient source content must be
implemented separately with per-source consent/grant checks and persisted audit.
"""
from __future__ import annotations
from flask import request
from functools import lru_cache
from pathlib import Path
import os
import logging
from cc_nlp.models import SourceRecord,ProcessingAuthorization
from cc_nlp.providers.mock import DeterministicMockProvider
from cc_nlp.providers.ollama import LocalOllamaProvider
from cc_nlp.catalog import load_catalog
from cc_nlp.validator import load_schema
from cc_nlp.pipeline import analyze

@lru_cache(maxsize=1)
def specs():
    root=Path(__file__).resolve().parents[1]/'cc_nlp/assets'
    return load_catalog(root/'tags.v0.1.json'), load_schema(root/'extraction_result.schema.json')

def register_nlp_lab_v3(app, SessionLocal, require_role):
    @app.post('/api/v1/nlp-v3/synthetic-extract')
    def nlp_v3_synthetic_extract():
        from .verification import workspace_enabled
        if not workspace_enabled(app.config):
            return {'error':{'code':'SYNTHETIC_ONLY'}},404
        with SessionLocal() as db:require_role(db,'doctor')
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or set(data)!={'text','synthetic'} or data['synthetic'] is not True or not isinstance(data['text'],str) or not 1<=len(data['text'])<=12000 or not data['text'].strip():
            return {'error':{'code':'INVALID_SYNTHETIC_INPUT','message':'Только явно синтетический текст, 1–12000 символов'}},422
        catalog,schema=specs()
        source=SourceRecord(source_id='synthetic_lab_v3',source_revision=1,source_type='clinician_note',
                            body_text=data['text'],visibility='shared_with_care_team',author_role='clinician')
        allowed=ProcessingAuthorization(audience='doctor',source_access_granted=True)
        mode=os.environ.get('CC_NLP_V3_PROVIDER','mock')
        provider=DeterministicMockProvider()
        if mode=='ollama':
            provider=LocalOllamaProvider(model=os.environ.get('CC_NLP_V3_MODEL','qwen3:4b-instruct'))
        result=analyze(source,allowed,provider,catalog=catalog,schema=schema)
        primary=result
        diagnostics={'error_code':primary.error_code,'stage':primary.error_stage or 'completed',
                     'duration_ms':primary.elapsed_ms,'model_id':primary.model_id,
                     'prompt_version':primary.prompt_version}
        # Only bounded metadata from trusted pipeline; never log source/model prose.
        logging.getLogger(__name__).info('synthetic_nlp_pipeline %s', diagnostics)
        fallback=False
        if result.error_code and mode=='ollama':
            result=analyze(source,allowed,DeterministicMockProvider(),catalog=catalog,schema=schema)
            fallback=True
        return {'synthetic':True,'mode':'deterministic_mock_fallback' if fallback else provider.name,
                'nlp_version':'0.2.0','data':result.result,'error_code':primary.error_code,
                'diagnostics':diagnostics,'fallback_used':fallback,
                'fallback_error_code':result.error_code if fallback else None,
                'clinical_rules_applied':False,'persisted':False,
                'status':'candidate_requires_clinician_review',
                'limitations':'Лабораторный NLP для синтетического текста. Не создаёт диагнозов, назначений или подписанных записей.'}
