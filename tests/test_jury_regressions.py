"""Jury repairs: recover committed guest transfers without duplication or disclosure."""
from test_patient_experience import app, login, detail, save, submit, assignments
from test_onboarding import mutate
PX='/api/v1/patient-experience/questionnaires'

def test_guest_transfer_key_recovers_only_same_patient_completed_assignment(app):
    client,_=login(app)
    payload={'definition_id':'eval_phq_2_v1','idempotency_key':'guest-transfer-once'}
    row=mutate(client,'POST',PX+'/self-assign',payload).json
    definition=detail(client,row)['definition']
    assert save(client,row,{q['id']:2 for q in definition['questions']}).status_code==200
    assert submit(client,row,key=payload['idempotency_key']).status_code==201
    before=len(assignments(client))
    recovered=mutate(client,'POST',PX+'/self-assign',payload)
    assert recovered.status_code==200 and recovered.json['id']==row['id']
    assert recovered.json['status']=='submitted' and len(assignments(client))==before
    other,_=login(app,'trend_two')
    separate=mutate(other,'POST',PX+'/self-assign',payload)
    assert separate.status_code==201 and separate.json['id']!=row['id']
    new=mutate(client,'POST',PX+'/self-assign',{**payload,'idempotency_key':'new-explicit-assessment'})
    assert new.status_code==201 and new.json['id']!=row['id']


def test_invalid_transfer_keys_fail_closed(app):
    client,_=login(app)
    for key in ('','x'*81,17,False):
        response=mutate(client,'POST',PX+'/self-assign',{'definition_id':'eval_phq_2_v1','idempotency_key':key})
        assert response.status_code==422
