"""Aggregate-only research computation. Pure functions enable offline test coverage."""
import statistics
from collections import defaultdict

MIN_CELL=5

def aggregate_observations(records, *, min_cell=MIN_CELL):
    grouped=defaultdict(list)
    for row in records:
        grouped[row.cohort].append(row)
    out=[]
    for cohort, rows in sorted(grouped.items()):
        unique={r.study_subject:r.value for r in rows}
        total=len(unique)
        valid=[v for v in unique.values() if v is not None]
        hidden=total<min_cell or len(valid)<min_cell
        out.append({'cohort':cohort,'n':None if hidden else total,
            'observed_n':None if hidden else len(valid),
            'missing_n':None if hidden else total-len(valid),
            'mean':None if hidden else round(statistics.mean(valid),2),
            'suppressed':hidden,
            'source':'reproducible_synthetic_fixture_v1'})
    return out
