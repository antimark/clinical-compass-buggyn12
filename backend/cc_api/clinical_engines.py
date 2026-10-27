"""Versioned, synthetic-only clinical extension interfaces.

Not validated for medical decisions. This module does not prescribe, triage or
create chart entries. Models accept only structured numeric/patient-reported
synthetic data; free text is never sent to an external provider.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Signal:
    rule_id: str
    rule_version: str
    evidence: tuple
    status: str = 'requires_clinician_review'
    limitations: str = 'Synthetic demonstration; no validated clinical significance'

class SignalEngine:
    version='0.1-synthetic'
    def evaluate(self, measurements, *, mode='disabled'):
        """One explicit demo rule based on two *known* numerical observations.

        Deliberately no psych-risk inference, medication causality, keywords,
        severity, clinician escalation, or autonomous documentation.
        """
        if mode=='disabled':return []
        if mode!='synthetic_rules':raise ValueError('Unsupported signal engine mode')
        if len(measurements)<2:return []
        before,after=measurements[-2:]
        if not all(type(x)==int and 1<=x<=5 for x in (before,after)):
            return []
        if before-after>=2:
            return [Signal('synthetic_score_change','0.1',(
                {'source':'synthetic_measurement','value':before},
                {'source':'synthetic_measurement','value':after}))]
        return []

class RecommendationEngine:
    modes=('disabled','curated_rules','approved_provider')
    def propose(self, *, mode='disabled', reviewed_rules=(), facts=None):
        if mode=='disabled':return []
        if mode=='approved_provider':raise NotImplementedError('No external provider connected')
        if mode!='curated_rules':raise ValueError('Invalid recommendation mode')
        # Reviewed rules need human-approved provenance before any display.
        return [{'rule_id':r['id'],'version':r['version'],'source':r['source'],
                'limitations':r['limitations'],'status':'proposed_only'}
                for r in reviewed_rules
                if all(r.get(k) for k in ('id','version','source','limitations'))
                and r.get('approved') is True]
