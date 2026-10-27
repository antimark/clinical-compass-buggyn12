"""Stand-alone synthetic research fixture: no ORM patient access, no real study claims."""
from functools import lru_cache
from pathlib import Path
from collections import defaultdict
from statistics import mean
import json
import csv
import io

FIXTURE=Path(__file__).resolve().parents[2]/'research_data/research_demo_v3.json'
MIN_CELL=5

@lru_cache(maxsize=1)
def dataset():
    data=json.loads(FIXTURE.read_text(encoding='utf-8'))
    if data.get('synthetic') is not True or data.get('dataset_id')!='synthetic_research_v3':
        raise ValueError('only explicitly labeled independent synthetic dataset permitted')
    return data

def describe():
    d=dataset();measure=d['measure']
    return {'dataset_id':d['dataset_id'],'version':d['version'],'title':d['title'],
            'description':d['description'],'synthetic':True,'dataset_type':'independent_synthetic_fixture',
            'row_count':len(d['observations']),'subjects_count':len(d['subjects']),
            'fields':[{'name':'subject_id','type':'synthetic_subject_identifier','exported':False},
                      {'name':'date','type':'ISO_date','exported':False},
                      {'name':'cohort','type':'synthetic_categorical_group','exported':False},
                      {'name':'mood_1_5','type':'nullable_integer','min':1,'max':5,'unit':'points','null_policy':measure['null_policy']}],
            'unit_of_analysis':measure['unit_of_analysis'],
            'source':'Clinical Compass v3 fixture; NOT linked to medical records',
            'min_cell':MIN_CELL,'no_patient_records':True}

def summarize(*, cohort='', date_from='', date_to=''):
    d=dataset()
    if cohort not in ('','A','B'):raise ValueError('invalid_cohort')
    # Date slices would allow neighboring-window differencing of sub-threshold cells.
    if date_from or date_to:raise ValueError('date_filter_blocked_to_prevent_differencing')
    if any(v and (len(v)!=10 or v[4]!='-' or v[7]!='-' or not v.replace('-','').isdigit()) for v in (date_from,date_to)):
        raise ValueError('invalid_date')
    groups={r['id']:r.get('cohort') for r in d['subjects']}
    rows=[r for r in d['observations'] if (not cohort or groups.get(r['subject_id'])==cohort)
          and (not date_from or r['date']>=date_from) and (not date_to or r['date']<=date_to)]
    valid=[r['mood_1_5'] for r in rows if isinstance(r.get('mood_1_5'),(int,float)) and not isinstance(r.get('mood_1_5'),bool) and 1<=r['mood_1_5']<=5]
    observed_n=len(valid);n=len(rows);missing_n=n-observed_n
    suppressed=n<MIN_CELL or observed_n<MIN_CELL
    # Suppressed cells disclose NO raw count, no mean and no recoverable complement.
    return {'dataset_id':d['dataset_id'],'version':d['version'],'synthetic':True,
            'source':'Independent synthetic fixture v3','measure':d['measure']['code'],
            'label':d['measure']['label'],'unit':'points (1–5)','scale':{'min':1,'max':5},
            'unit_of_analysis':d['measure']['unit_of_analysis'],
            'formula':'sum(non-null mood_1_5) / count(non-null mood_1_5)',
            'period':{'from':date_from or min(r['date'] for r in d['observations']),
                      'to':date_to or max(r['date'] for r in d['observations'])},
            'filter':{'cohort':cohort,'from':date_from,'to':date_to},
            'n':None if suppressed else n,'observed_n':None if suppressed else observed_n,
            'missing_n':None if suppressed else missing_n,
            'mean':None if suppressed else round(mean(valid),2),
            'suppressed':suppressed,'suppression_reason':'small_cell' if suppressed else None,
            'limitations':'Только синтетические данные. Не измеряет эффективность лечения.'}

def export_aggregates():
    """Single unfiltered aggregate only: avoid differential attacks through flexible CSV exports."""
    summary=summarize();f=io.StringIO();fields=['dataset_id','version','measure','unit','unit_of_analysis','n','observed_n','missing_n','mean','synthetic']
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerow({k:summary[k] for k in fields})
    return f.getvalue()
