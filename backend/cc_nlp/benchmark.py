"""Reproducible *technical* benchmark for the invented v0.1 corpus.

Output scores are draft corpus scores only; do not interpret as clinical validity.
"""
from __future__ import annotations
import argparse, json, time, statistics
from pathlib import Path
from .models import SourceRecord, ProcessingAuthorization
from .batch import BatchAnalysisRequest, analyze_batch
from .cli import resources
from .providers.mock import DeterministicMockProvider
from .providers.ollama import LocalOllamaProvider
from .evaluation import evaluate_case_results


def load_case(path: Path):
    raw=json.loads(path.read_text(encoding='utf-8'))
    request=raw['request']
    if raw.get('clinical_expert_validated') is not False or any(s.get('synthetic') is not True for s in request['sources']):
        raise ValueError('benchmark_requires_explicit_synthetic_draft')
    sources=tuple(SourceRecord(
      source_id=s['source_id'], source_revision=s['source_revision'],source_type=s['source_type'],
      body_text=s['body_text'],visibility=s['visibility'],author_role=s['author_role'],
      document_id=s['document_id'],field_id=s.get('field_id'),authored_at=s.get('authored_at'),
      subject_ref=s['subject_ref']) for s in request['sources'])
    return BatchAnalysisRequest(request['request_id'],request['subject_ref'],sources,request['analysis_mode'])


def run_corpus(path: Path, provider, *, include_splits=None) -> dict:
    cat,schema=resources(Path(__file__).resolve().parents[2])
    items=[];duration=[];total=0;failed=0;complete_facts=0;match_core=0
    for file in sorted((path/'inputs').glob('case_*.json')):
        inp=json.loads(file.read_text(encoding='utf-8'))
        if include_splits and inp['split'] not in include_splits:
            continue
        req=load_case(file)
        gold=json.loads((path/'gold_draft'/(file.stem+'.gold.json')).read_text(encoding='utf-8'))
        annotation={item['source_id']:item for item in gold['annotations_by_source']}
        begin=time.perf_counter()
        result=analyze_batch(req,ProcessingAuthorization('doctor',True),provider,catalog=cat,schema=schema)
        duration.append(time.perf_counter()-begin)
        for outcome in result.source_results:
            expected=annotation[outcome.result['source_id']]
            items.append({'gold_positive_tags':expected['positive_current_patient_tags'],
                'forbidden_positive_tags':expected.get('forbidden_positive_current_tags',[]),
                'result':outcome.result})
            if outcome.error_code:failed+=1
            # Strictly compare full facts (tag+assertion+temporality+speaker+exact evidence).
            actual={(f['tag_code'],f['assertion'],f['temporality'],f['speaker'],f['evidence']['start'],f['evidence']['end'])
                    for f in outcome.result['facts']}
            target={(f['tag_code'],f['assertion'],f['temporality'],f['speaker'],f['evidence']['start'],f['evidence']['end'])
                    for f in expected['expected_facts']}
            match_core+=len(actual&target)
            complete_facts+=len(target)
            total+=1
    metric=evaluate_case_results(items)
    metric.update({'dataset':'synthetic_draft_v0.1','corpus_sources':total,
       'provider':provider.name,'model_id':provider.model_id,
       'source_errors':failed,'exact_gold_fact_matches':match_core,
       'draft_gold_fact_count':complete_facts,
       'strict_fact_recall':match_core/complete_facts if complete_facts else None,
       'total_elapsed_seconds':round(sum(duration),4),
       'median_case_seconds':round(statistics.median(duration),4) if duration else None,
       'p95_case_seconds':round(sorted(duration)[max(0,int((len(duration)-1)*0.95))],4) if duration else None,
       'clinical_expert_validated':False,
       'warning':'PRELIMINARY SYNTHETIC TECHNICAL CORPUS: not diagnostic, not clinical validation. Holdout protected only by process.'})
    return metric


def main(argv=None):
    a=argparse.ArgumentParser(description='Synthetic-only batch benchmark')
    a.add_argument('--corpus', default='fixtures/initial_corpus_v0_1')
    a.add_argument('--provider',choices=['mock','ollama'],default='mock')
    a.add_argument('--model',default=None)
    a.add_argument('--split',choices=['development','challenge','evaluation_holdout'],action='append')
    a.add_argument('--save-report',help='Path to write metrics (no source texts)')
    args=a.parse_args(argv)
    if args.provider=='ollama' and not args.model:
        a.error('--model is required for ollama')
    provider=DeterministicMockProvider() if args.provider=='mock' else LocalOllamaProvider(model=args.model)
    metrics=run_corpus(Path(args.corpus),provider,include_splits=set(args.split) if args.split else None)
    data=json.dumps(metrics,ensure_ascii=False,indent=2)+'\n'
    print(data)
    if args.save_report:Path(args.save_report).write_text(data,encoding='utf-8')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
