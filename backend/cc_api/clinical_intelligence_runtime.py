"""Transient bounded source/actor-scoped cache; existing cc_nlp is the only extractor."""
import copy
from collections import OrderedDict,deque
from datetime import datetime,timezone
import logging
import threading
from time import monotonic
import uuid
from cc_nlp.models import SourceRecord,ProcessingAuthorization
from cc_nlp.providers.mock import DeterministicMockProvider
from cc_nlp.providers.ollama import LocalOllamaProvider
from cc_nlp.pipeline import analyze
from .nlp_lab_routes_v3 import specs
from .clinical_intelligence_sources import POLICY


def provider_factory(config):
    if config['CI_NLP_PROVIDER']=='mock':return DeterministicMockProvider()
    if config['CI_NLP_PROVIDER']!='ollama':raise ValueError('invalid_provider')
    return LocalOllamaProvider(model=config['CI_NLP_MODEL'],timeout_seconds=max(1,min(int(config.get('CI_NLP_TIMEOUT',45)),45)))


class Runtime:
    ttl=300
    capacity=64
    def __init__(self):
        self.lock=threading.RLock()
        self.generation=threading.BoundedSemaphore(1)
        self.cache=OrderedDict()
        self.pending=set()
        self.attempts=OrderedDict()
        self.sequence=0
        self.provider_factory=provider_factory

    def prune(self):
        now=monotonic()
        for key in list(self.cache):
            if now-self.cache[key]['at']>self.ttl:self.cache.pop(key)
        for key in list(self.attempts):
            while self.attempts[key] and now-self.attempts[key][0]>=60:self.attempts[key].popleft()
            if not self.attempts[key]:self.attempts.pop(key)

    def start(self,key):
        with self.lock:
            self.prune()
            if key[0] not in self.attempts and len(self.attempts)>=256:return 'busy'
            times=self.attempts.setdefault(key[0],deque())
            if len(times)>=5:return 'rate_limited'
            if not self.generation.acquire(blocking=False):return 'busy'
            times.append(monotonic())
            self.pending.add(key)
            return None

    def finish(self,key):
        with self.lock:
            self.pending.discard(key)
            self.generation.release()

    def read(self,key,source):
        with self.lock:
            self.prune()
            item=self.cache.get(key)
            if not item:return None
            if item['source_version']!=source.source_version or item['grant_version']!=source.grant_version:
                self.cache.pop(key);return 'stale'
            self.cache.move_to_end(key)
            return copy.deepcopy(item['dto'])

    def put(self,key,source,dto):
        with self.lock:
            self.sequence+=1;dto['snapshot_version']=self.sequence
            self.cache[key]={'at':monotonic(),'source_version':source.source_version,'grant_version':source.grant_version,'dto':copy.deepcopy(dto)}
            self.cache.move_to_end(key)
            while len(self.cache)>self.capacity:self.cache.popitem(last=False)


def empty_dto(source,status='unavailable',reason='not_started'):
    return {'schema_version':'ci-v1','snapshot_version':0,'analysis_status':status,'reason_code':reason,
        'source_policy_version':POLICY,'patient_ref':source.patient_id,'encounter_ref':source.case_id,
        'source_revision':source.source_revision,'source_version':source.source_version,
        'granted_scopes':['symptoms'],'mode':None,'model_version':None,'primary_model_version':None,
        'generated_at':None,'tags':[],'evidence':[],'draft_suggestions':[],'routing':[],
        'permissions':{'can_review':False,'can_create_referral':False,'clinical_action_enabled':False},
        'clinical_action_enabled':False,'clinical_rules_applied':False,'persisted':False,'error_code':None}


def compute(source,config,runtime):
    catalog,schema=specs()
    record=SourceRecord(source_id=source.case_id,source_revision=source.source_revision,source_type='previsit_case',
        body_text=source.text,visibility='shared_with_care_team',author_role='patient',authored_at=source.created_at)
    allowed=ProcessingAuthorization(audience='doctor',source_access_granted=True)
    primary_provider=runtime.provider_factory(config)
    primary=analyze(record,allowed,primary_provider,catalog=catalog,schema=schema)
    result=primary;fallback=False
    if primary.error_code and primary_provider.name=='local_llm' and primary.error_code!='local_inference_busy':
        result=analyze(record,allowed,DeterministicMockProvider(),catalog=catalog,schema=schema);fallback=True
    dto=empty_dto(source,'ready' if not primary.error_code and primary_provider.name=='local_llm' else 'needs_review',None)
    dto.update(mode='deterministic_mock_fallback' if fallback else primary_provider.name,
        model_version=result.model_id,primary_model_version=primary.model_id,
        generated_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),error_code=primary.error_code,
        fallback_used=fallback,fallback_error_code=result.error_code if fallback else None,
        prompt_version=primary.prompt_version,nlp_version='0.2.0',catalog_version=catalog['catalog_version'],
        diagnostics={'stage':primary.error_stage or 'completed','duration_ms':primary.elapsed_ms,'error_code':primary.error_code})
    if primary.error_code=='local_inference_busy':
        dto['analysis_status']='unavailable';dto['reason_code']='local_inference_busy'
    tags={tag['code']:tag for tag in catalog['tags']}
    grouped={}
    # Intake symptoms/topic scope never upgrades into safety, medication or clinical rules.
    for fact in result.result['facts']:
        tag=tags[fact['tag_code']]
        if tag['category'] not in ('symptom','topic'):continue
        ev_id='ev_'+uuid.uuid4().hex
        dto['evidence'].append({'id':ev_id,'source_type':'intake','source_id':source.case_id,
            'quote':fact['evidence']['quote'],'start':fact['evidence']['start'],'end':fact['evidence']['end'],
            'scope':'symptoms','recorded_at':source.created_at})
        key=(fact['tag_code'],fact['assertion'],fact['temporality'])
        if key not in grouped:
            grouped[key]={'id':'tag_'+uuid.uuid4().hex,'code':fact['tag_code'],'label':tag['label_ru'],
                'category':tag['category'],'assertion':fact['assertion'],'temporality':fact['temporality'],
                'review_status':'proposed','evidence_refs':[],
                'frequency':{'numerator':1,'denominator':1,'unit':'authorized_notes',
                    'window_start':source.created_at,'window_end':source.created_at}}
        grouped[key]['evidence_refs'].append(ev_id)
    dto['tags']=list(grouped.values())
    for evidence in dto['evidence'][:8]:
        dto['draft_suggestions'].append({'id':'proposal_'+uuid.uuid4().hex,'text':evidence['quote'],
            'status':'proposed','evidence_refs':[evidence['id']]})
    # Trusted bounded metadata only. No source identifiers, quotes, names, prompts or model prose.
    logging.getLogger(__name__).info('ci_analysis mode=%s stage=%s duration_ms=%s error=%s',
        dto['mode'],dto['diagnostics']['stage'],dto['diagnostics']['duration_ms'],dto['error_code'])
    return dto
