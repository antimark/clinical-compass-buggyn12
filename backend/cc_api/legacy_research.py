"""Compatibility projections use the same current-grant/disclosure boundary."""
import json
from sqlalchemy import select, update
from .p0_models import DatasetDefinition
from .research_workflow_models import ResearchStudyLock
from . import research_workflow_service as service


def legacy_aggregate(db, user, secret, study='study_demo_v1', cohort=None):
    service.require_grant(db, user, study)
    if cohort is not None and cohort not in ('A', 'B'):
        service.fail(422, 'INVALID_FILTER', 'Неизвестная группа')
    db.execute(update(ResearchStudyLock).where(ResearchStudyLock.study_id == study)
        .values(revision=ResearchStudyLock.revision + 1))
    service.require_grant(db, user, study)
    config = service.validate({'study_id': study, 'measure': 'synthetic_mood',
        'cohorts': [cohort] if cohort else ['A', 'B']})
    definition = None
    for row in db.scalars(select(DatasetDefinition).where(DatasetDefinition.researcher_id == user.id,
            DatasetDefinition.study_id == study)).all():
        raw = json.loads(row.definition_json)
        try: candidate=service.validate({'study_id': row.study_id, **raw})
        except service.ResearchFailure: continue
        if candidate == config:
            definition = row.id
            break
    if definition is None:
        definition = service.create_definition(db, user, config)['id']
    return service.compute(db, user, definition, secret)
