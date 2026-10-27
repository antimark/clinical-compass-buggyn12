"""Controlled questionnaire metadata; no licensed item text or clinical interpretation."""
INSTRUMENTS={
    'PHQ-9': {'version':'metadata-1','item_count':9,'max_score':27,
        'description':'PHQ-9 (metadata only; no item wording provided)'},
    'GAD-7': {'version':'metadata-1','item_count':7,'max_score':21,
        'description':'GAD-7 (metadata only; no item wording provided)'},
}

def numeric_total(instrument_id, scores):
    meta=INSTRUMENTS.get(instrument_id)
    if not meta or not isinstance(scores,list) or len(scores)!=meta['item_count']:
        raise ValueError('Incorrect instrument or item count')
    if not all(type(v) is int and 0<=v<=3 for v in scores):
        raise ValueError('All response items must be integers in [0,3]')
    return sum(scores)
