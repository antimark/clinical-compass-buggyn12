"""Pure versioned engine safety checks without Flask."""
import importlib.util
from pathlib import Path
import pytest

p=Path(__file__).resolve().parents[1]/'backend/cc_api/clinical_engines.py'
spec=importlib.util.spec_from_file_location('cc_p0_engines',p)
import sys
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)

def test_synthetic_signal_is_not_a_clinical_decision():
    eng=module.SignalEngine()
    assert eng.evaluate([5,2])==[]
    signals=eng.evaluate([5,2],mode='synthetic_rules')
    assert len(signals)==1 and signals[0].status=='requires_clinician_review'
    assert signals[0].evidence[0]['value']==5
    assert eng.evaluate([5,None],mode='synthetic_rules')==[]
    assert eng.evaluate([2,1],mode='synthetic_rules')==[]
    with pytest.raises(ValueError):eng.evaluate([5,2],mode='production')

def test_recommendation_is_disabled_without_approved_provenance():
    eng=module.RecommendationEngine()
    rule={'id':'test','source':'synthetic','version':'1','limitations':'unverified'}
    assert eng.propose(mode='disabled',reviewed_rules=[rule])==[]
    assert eng.propose(mode='curated_rules',reviewed_rules=[rule])==[]
    result=eng.propose(mode='curated_rules',reviewed_rules=[{**rule,'approved':True}])
    assert result[0]['status']=='proposed_only'
    with pytest.raises(NotImplementedError):eng.propose(mode='approved_provider')
