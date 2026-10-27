"""Apply document release/consent checks to every compatibility plan projection."""
from flask import abort
from werkzeug.exceptions import HTTPException


def plan_visible(db, user, plan, *, lock=False):
    if not plan.id.startswith('cdoc_'):
        return True  # Preserve original separately authored legacy plan contracts.
    from .clinical_workflow_services import document_access
    try:
        document = document_access(db, user, plan.id, lock=lock)
        return document.status == 'published' and document.patient_id == plan.patient_id
    except HTTPException as exc:
        if exc.code not in (403, 404):
            raise
        return False


def require_released_plan(db, user, plan, *, lock=False):
    if not plan_visible(db, user, plan, lock=lock):
        abort(404)
