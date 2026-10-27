"""Researcher-only synthetic fixture routes. No patient tables are queried."""
from flask import request, Response, current_app
from .research_demo_v3 import describe, summarize, export_aggregates, dataset

def register_research_demo_v3(app,SessionLocal,require_role):
    def guard():
        # Fail closed on deployments not explicitly synthetic.
        from .verification import workspace_enabled
        if not workspace_enabled(app.config):
            return {'error':{'code':'SYNTHETIC_ONLY'}},404
        with SessionLocal() as db:require_role(db,'researcher')
        return None

    @app.get('/api/v1/research/demo-datasets')
    def v3_dataset_index():
        err=guard()
        if err:return err
        return {'items':[describe()]}

    @app.get('/api/v1/research/demo-datasets/<dataset_id>/summary')
    def v3_dataset_summary(dataset_id):
        err=guard()
        if err:return err
        if dataset_id!='synthetic_research_v3':return {'error':{'code':'NOT_FOUND'}},404
        try:return summarize(cohort=request.args.get('cohort',''),
                     date_from=request.args.get('from',''),date_to=request.args.get('to',''))
        except ValueError:return {'error':{'code':'INVALID_FILTER'}},422

    @app.get('/api/v1/research/demo-datasets/<dataset_id>/synthetic-observations')
    def v3_synthetic_table(dataset_id):
        # Independent, explicitly fake rows only; NEVER query patients, journals or encounters.
        err=guard()
        if err:return err
        if dataset_id!='synthetic_research_v3':return {'error':{'code':'NOT_FOUND'}},404
        d=dataset()
        return {'dataset_id':d['dataset_id'],'version':d['version'],'synthetic':True,
                'source':'independent_synthetic_fixture_not_patient_records',
                'unit_of_analysis':'one_observation',
                'items':[{'subject_id':r['subject_id'],'date':r['date'],
                          'cohort':next(s['cohort'] for s in d['subjects'] if s['id']==r['subject_id']),
                          'mood_1_5':r['mood_1_5']} for r in d['observations']]}

    @app.get('/api/v1/research/demo-datasets/<dataset_id>/export')
    def v3_dataset_export(dataset_id):
        err=guard()
        if err:return err
        if dataset_id!='synthetic_research_v3':return {'error':{'code':'NOT_FOUND'}},404
        if request.args:return {'error':{'code':'FILTERED_EXPORT_NOT_SUPPORTED'}},422
        return Response(export_aggregates(),mimetype='text/csv',headers={
             'Content-Disposition':'attachment; filename="clinical_compass_synthetic_v3_aggregates.csv"',
             'Cache-Control':'no-store'})
