"""Small helpers shared across route and fixture modules."""
from __future__ import annotations
from datetime import datetime, timezone

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def alert_dict(a):
    return {'id': a.id, 'patient_id': a.patient_id, 'severity': a.severity,
            'status': a.status, 'created_at': a.created_at, 'acknowledged_at': a.acknowledged_at,
            'reason_code': a.reason_code}
