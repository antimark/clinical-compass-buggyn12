"""Real local disposable PostgreSQL integration and controlled concurrency gates.

Never targets a production host. Creates/drops only cc_phase5_test_<random>.
Requires CC_TEST_PG_ADMIN_URL; passwords are never printed. SQLite and OIDC are
separate evidence, not substitutes for this script.
"""
import os,secrets,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier,Event
from urllib.parse import unquote
import psycopg
from psycopg import sql
from sqlalchemy import select,func,event,inspect,text
from sqlalchemy.engine import make_url

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tests')]


def concurrent(functions):
    barrier=Barrier(len(functions))
    def run(fn):
        barrier.wait(timeout=15)
        return fn()
    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        return list(pool.map(run,functions))


def main():
    from cc_api import create_app
    from cc_api.models import User
    from cc_api.extension_models import Appointment
    from cc_api.clinical_workflow_models import SlotBooking,ClinicalDocument
    from test_onboarding import actor,mutate,register,issue,accept,PASSWORD
    from test_patient_experience import login
    from test_booking import setup_case,slot,proposal,BK
    from test_clinical_workflow import create,transition,CW
    from test_phase5_acceptance import second_researcher,definition,good,RW
    supplied=os.environ.get('CC_TEST_PG_ADMIN_URL')
    if not supplied:raise SystemExit('NOT_RUN: set local synthetic CC_TEST_PG_ADMIN_URL')
    url=make_url(supplied)
    if url.get_backend_name()!='postgresql' or url.host not in ('127.0.0.1','localhost','::1'):
        raise SystemExit('Only explicitly local synthetic PostgreSQL administration DSN is allowed')
    name='cc_phase5_test_'+secrets.token_hex(8)
    args={'host':url.host,'port':url.port or 5432,'dbname':url.database or 'postgres','user':unquote(url.username or ''),'password':unquote(url.password or '')}
    app=None
    with psycopg.connect(**args,autocommit=True) as admin:
        with admin.cursor() as cursor:cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            test_url=url.set(database=name,drivername='postgresql+psycopg').render_as_string(hide_password=False)
            os.environ['CC_DATABASE_URL']=test_url
            app=create_app({'TESTING':True,'DEMO_MODE':True,'APP_ENV':'synthetic_dev','SEED_PATIENT_PERSONAS':True,'SECRET_KEY':'PG_PHASE5_SYNTHETIC_ONLY'})
            engine=app.extensions['cc_session_factory'].kw['bind']
            assert engine.dialect.name=='postgresql'
            with engine.connect() as connection:
                assert connection.scalar(text('select version()')).startswith('PostgreSQL')
                assert connection.scalar(text('select version_num from alembic_version')).startswith('0014')
            print('PASS PostgreSQL actual engine and migrations through 0014')

            # Two genuine patients receive the same available slot in separate
            # proposals. One persisted confirmation/slot row must win.
            p1,doctor,c1=setup_case(app,key='pg_same_slot_one',persona='trend_one')
            p2,_,c2=setup_case(app,key='pg_same_slot_two',persona='trend_two')
            common=slot(doctor,day=50,hour=0)
            offer1=proposal(doctor,c1,[common,slot(doctor,day=50,hour=1)])
            offer2=proposal(doctor,c2,[common,slot(doctor,day=50,hour=2)])
            a1,a2=offer1['candidates'][0]['appointment_id'],offer2['candidates'][0]['appointment_id']
            replies=concurrent([lambda:mutate(p1,'POST',BK+'/appointments/'+a1+'/accept',{}),lambda:mutate(p2,'POST',BK+'/appointments/'+a2+'/accept',{})])
            assert sorted(response.status_code for response in replies)==[200,409],[response.json for response in replies]
            with app.extensions['cc_session_factory']() as db:
                assert db.scalar(select(func.count()).select_from(SlotBooking).where(SlotBooking.slot_id==common['id']))==1
                assert sum(db.get(Appointment,key).status=='confirmed' for key in (a1,a2))==1
            print('PASS PostgreSQL simultaneous different offers / same slot: one confirmation')

            # Independent physicians have overlapping valid slots for one real
            # patient: patient-level lock must prevent both appointments.
            p3,d1,c3=setup_case(app,key='pg_overlap_one',persona='history_01')
            p4,d2,c4=setup_case(app,doctor_id='doc_ther',key='pg_overlap_two',persona='history_01')
            o3=proposal(d1,c3,[slot(d1,day=51,hour=h) for h in (0,1)])
            o4=proposal(d2,c4,[slot(d2,day=51,hour=h) for h in (0,2)])
            selected=[o3['candidates'][0]['appointment_id'],o4['candidates'][0]['appointment_id']]
            replies=concurrent([lambda:mutate(p3,'POST',BK+'/appointments/'+selected[0]+'/accept',{}),lambda:mutate(p4,'POST',BK+'/appointments/'+selected[1]+'/accept',{})])
            assert sorted(response.status_code for response in replies)==[200,409],[response.json for response in replies]
            with app.extensions['cc_session_factory']() as db:assert sum(db.get(Appointment,key).status=='confirmed' for key in selected)==1
            print('PASS PostgreSQL simultaneous cross-physician patient overlap: one confirmation')

            # Recipient-bound onboarding invitation redemption uses actual HTTP
            # password sessions and persistent SQL compare-and-set.
            first=app.test_client();new=register(first,'pg-invite-race@qa.test')
            invitation=issue(actor(app),'pg-invite-race@qa.test',['symptoms','diagnosis','medications'])
            clients=[]
            for _ in range(2):
                client=app.test_client();good(mutate(client,'POST','/api/v1/onboarding/login',{'email':'pg-invite-race@qa.test','password':PASSWORD}));clients.append(client)
            replies=concurrent([lambda:accept(clients[0],invitation),lambda:accept(clients[1],invitation)])
            statuses=[response.status_code for response in replies]
            assert statuses.count(200)==1 and all(code in (200,404,409) for code in statuses),[response.json for response in replies]
            from cc_api.onboarding_models import PatientConsent
            from cc_api.models import DoctorPatientLink
            with app.extensions['cc_session_factory']() as db:
                assert db.scalar(select(func.count()).select_from(PatientConsent).where(PatientConsent.invitation_id==invitation['id']))==1
                assert db.scalar(select(func.count()).select_from(DoctorPatientLink).where(DoctorPatientLink.doctor_id=='doc_psy',DoctorPatientLink.patient_id==new['user']['patient_id']))==1
            print('PASS PostgreSQL recipient-bound invitation redemption: one acceptance and one ledger/link')

            # Hold a real consent-revocation transaction while publication waits
            # on its PostgreSQL row lock. No synthetic sleeps or fake responses.
            patient,identity=login(app,'clinical_history');physician=actor(app)
            draft=create(physician,identity['patient_id'],'treatment',{'narrative':'PostgreSQL synthetic publication race','items':[{'item_type':'action','title':'Синтетический план'}]})
            signed=transition(physician,draft,'sign');assert signed.status_code==200
            revoked=Event();waiting=Event();release=Event()
            def after_execute(conn,cursor,statement,parameters,context,executemany):
                if 'update ob_consents set revoked_at' in statement.lower():
                    revoked.set();assert release.wait(20),'Revocation lock was never released by coordinator'
            def before_execute(conn,cursor,statement,parameters,context,executemany):
                if revoked.is_set() and 'update ob_consents set version' in statement.lower():waiting.set()
            event.listen(engine,'after_cursor_execute',after_execute);event.listen(engine,'before_cursor_execute',before_execute)
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    revoke=pool.submit(mutate,patient,'DELETE','/api/v1/patients/me/clinical-links/doc_psy',{})
                    assert revoked.wait(20),'Real revocation UPDATE did not acquire lock'
                    publish=pool.submit(transition,physician,signed.json,'publish')
                    try:assert waiting.wait(20),'Publication did not attempt consent lock'
                    finally:release.set()
                    assert revoke.result(timeout=30).status_code==200
                    response=publish.result(timeout=30);assert response.status_code==404,response.json
                with app.extensions['cc_session_factory']() as db:
                    row=db.get(ClinicalDocument,draft['id']);assert row.status=='signed' and row.published_at is None
            finally:
                release.set();event.remove(engine,'after_cursor_execute',after_execute);event.remove(engine,'before_cursor_execute',before_execute)
            print('PASS PostgreSQL committed revocation wins over waiting publication')

            # Shared disclosure lock spans researchers. Queries differ by only
            # two subjects; exactly one releases a cell and the other suppresses.
            researcher=actor(app,'researcher_01');other,_=second_researcher(app)
            d1=definition(researcher,cohorts=['A']);d2=definition(other,cohorts=['A'],criteria={'include':['observed_value']})
            results=concurrent([lambda:researcher.get(RW+'/definitions/'+d1['id']+'/compute'),lambda:other.get(RW+'/definitions/'+d2['id']+'/compute')])
            assert all(response.status_code==200 for response in results),[response.json for response in results]
            cells=[response.json['items'][0] for response in results]
            assert sorted(cell['suppressed'] for cell in cells)==[False,True],cells
            assert next(cell for cell in cells if cell['suppressed'])['suppression_reason']=='differencing_guard'
            print('PASS PostgreSQL concurrent cross-researcher disclosure serialization')

            # Close all pooled connections, reopen the same migrated DB, and
            # verify genuine persisted rows and authorization remain intact.
            engine.dispose();reopened=create_app(dict(app.config))
            renewed,_=login(reopened,'clinical_history')
            assert actor(reopened).get(CW+'/documents/'+draft['id']).status_code==404
            with reopened.extensions['cc_session_factory']() as db:
                assert db.get(ClinicalDocument,draft['id']).status=='signed'
                assert db.scalar(select(func.count()).select_from(SlotBooking))>=2
            assert renewed.get(CW+'/patients/'+identity['patient_id']+'/documents').json['items']==[]
            cached=actor(reopened,'researcher_01').get(RW+'/definitions/'+d1['id']+'/compute')
            assert cached.status_code==200 and cached.json==results[0].json
            reopened.extensions['cc_session_factory'].kw['bind'].dispose()
            print('PASS PostgreSQL engine-close/reopen persistence and consent revocation')
            print('Phase 5 PostgreSQL: 7 gates PASSED; OIDC/MFA and medical signoff are separate evidence')
        finally:
            if app:app.extensions['cc_session_factory'].kw['bind'].dispose()
            with admin.cursor() as cursor:cursor.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))

if __name__=='__main__':main()
