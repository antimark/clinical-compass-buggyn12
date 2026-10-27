"""One-time idempotent OpenAPI extension: preserves v0.3 copy under reference/api_v03."""
from pathlib import Path
import yaml
p=Path('contracts/openapi.yaml');spec=yaml.safe_load(p.read_text())
spec['info']['version']='0.8.0-synthetic'
spec['info']['description']='Synthetic-only evolving contract. x-implementation marks server implementation; no production clinical assurance.'
spec['security']=[{'sessionCookie':[]},{'bearerAuth':[]}]
spec['components']['securitySchemes']['bearerAuth']={'type':'http','scheme':'bearer','bearerFormat':'OIDC JWT (RS256/ES256; pinned JWKS, MFA required)'}
spec['components']['schemas']['AuthContext']['properties']['csrf_token']={'type':['string','null']}
spec['components']['schemas']['Context']['properties']['role']['enum']=['doctor','patient','clinic_admin','researcher','platform_admin']
spec['components']['schemas'].update({
  'CaseIntake':{'type':'object','required':['text','symptoms','conditions','questionnaire_results'],
    'properties':{'text':{'type':'string','maxLength':2000},'symptoms':{'type':'array','items':{'type':'string'}},'conditions':{'type':'array','items':{'type':'string'}},'questionnaire_results':{'type':'array','items':{'type':'object'}}},'additionalProperties':False},
  'PrevisitCaseDetail':{'type':'object','required':['id','doctor_id','patient_user_id','status','intake','created_at'],
    'properties':{'id':{'type':'string'},'doctor_id':{'type':'string'},'patient_user_id':{'type':'string'},'status':{'type':'string'},'created_at':{'type':'string'},'intake':{'$ref':'#/components/schemas/CaseIntake'}}},
  'PrevisitCreate':{'type':'object','required':['doctor_id','text','case_consent'],
    'properties':{'doctor_id':{'type':'string'},'text':{'type':'string','minLength':1,'maxLength':2000},'case_consent':{'const':True},
    'symptoms':{'type':'array','maxItems':20,'items':{'type':'string'}},'conditions':{'type':'array','maxItems':20,'items':{'type':'string'}}},'additionalProperties':False},
  'InvitationIssue':{'type':'object','required':['target_role','recipient_id','categories'],
    'properties':{'target_role':{'type':'string','enum':['patient','doctor','clinic_admin']},'recipient_id':{'type':'string'},'patient_id':{'type':'string'},
    'categories':{'type':'array','items':{'type':'string','enum':['symptoms','diagnosis','medications','severity']}}},'additionalProperties':False},
  'InvitationIssued':{'type':'object','required':['id','registration_code','target_role','recipient_id','expires_at'],
    'properties':{'id':{'type':'string'},'registration_code':{'type':'string','description':'Shown once; hash only in database'},
    'target_role':{'type':'string'},'recipient_id':{'type':'string'},'expires_at':{'type':'string'},'categories':{'type':'array','items':{'type':'string'}}}},
  'ThreadMessage':{'type':'object','required':['id','thread_type','context_id','sender_id','recipient_id','text','created_at'],
    'properties':{k:{'type':'string'} for k in ('id','thread_type','context_id','sender_id','recipient_id','text','created_at')}},
  'Appointment':{'type':'object','required':['id','case_id','doctor_id','patient_user_id','status','format'],
    'properties':{k:{'type':'string'} for k in ('id','case_id','doctor_id','patient_user_id','proposed_at','format','status')}},
  'ResearchAggregates':{'type':'object','required':['dataset','items','small_cell_threshold','provenance'],
    'properties':{'dataset':{'type':'string'},'measure':{'type':'string'},'items':{'type':'array','items':{
      'type':'object','properties':{'cohort':{'type':'string'},'n':{'type':['integer','null']},'observed_n':{'type':['integer','null']},'missing_n':{'type':['integer','null']},'mean':{'type':['number','null']},'suppressed':{'type':'boolean'},'source':{'type':'string'}}}},
    'small_cell_threshold':{'type':'integer','const':5},'provenance':{'type':'string'},'missingness':{'type':'string'}}},
})
paths=spec['paths'];counter=0

def add(path,methods):
 global counter
 if path not in paths:paths[path]={}
 for method, (name,tag,summary,body,schema) in methods.items():
  counter+=1
  pth={'operationId':name,'tags':[tag],'summary':summary,
       'x-implementation':'integrated-synthetic','x-security-boundary':'server role/tenant/case authorization',
       'responses':{'200':{'description':'Scoped response'},'201':{'description':'Created'},'403':{'$ref':'#/components/responses/Forbidden'},'422':{'$ref':'#/components/responses/Validation'}}}
  if body is not None:
   if isinstance(body,str):ref={'$ref':'#/components/schemas/'+body}
   else:ref=body
   pth['requestBody']={'required':True,'content':{'application/json':{'schema':ref}}}
  if schema:
   pth['responses']['200']['content']={'application/json':{'schema':{'$ref':'#/components/schemas/'+schema}}}
  paths[path][method]=pth
T={'type':'object','properties':{'text':{'type':'string'}}}
add('/public/doctors',{'get':('listPublicDoctors','Doctor','Public directory, no clinical data',None,None)})
add('/public/doctors/{slug}',{'get':('getPublicDoctor','Doctor','Public doctor profile only',None,None)})
add('/invitations',{'post':('issueInvitation','Auth','Recipient bound hashed invitation','InvitationIssue','InvitationIssued')})
add('/invitations/accept',{'post':('redeemInvitation','Auth','Single-use atomic token redemption',{'type':'object','required':['registration_code'],'properties':{'registration_code':{'type':'string'}}},None)})
add('/invitations/{invitation_id}/revoke',{'post':('revokeInvitation','Auth','Issuer revokes pending invitation',{'type':'object'},None)})
add('/previsit-cases',{'get':('listPrevisitCases','Clinical workflow','Participant case list only',None,None),
 'post':('createPrevisitCase','Clinical workflow','Case-scoped consent, no automatic link','PrevisitCreate','PrevisitCaseDetail')})
add('/previsit-cases/{case_id}',{'get':('getPrevisitCase','Clinical workflow','Participant-scoped immutable snapshot',None,'PrevisitCaseDetail')})
add('/previsit-cases/{case_id}/messages',{'get':('listCaseMessages','Clinical workflow','Separate previsit thread',None,None),
 'post':('postCaseMessage','Clinical workflow','Atomic one-patient-message-before-reply policy',T,'ThreadMessage')})
add('/previsit-cases/{case_id}/appointment-requests',{'post':('requestCaseAppointment','Clinical workflow','Patient requests a time without link',{'type':'object'},'Appointment')})
add('/previsit-cases/{case_id}/offers',{'post':('offerCaseAppointment','Clinical workflow','Clinician offers time without link',{'type':'object','required':['proposed_at','format'],'properties':{'proposed_at':{'type':'string'},'format':{'type':'string','enum':['video','audio','in_person']}}},'Appointment')})
add('/appointments',{'get':('listAppointments','Clinical workflow','Actor-scoped appointment list',None,None)})
add('/appointments/{appointment_id}/confirm',{'post':('confirmAppointment','Clinical workflow','Patient confirms clinician offer',{'type':'object'},'Appointment')})
add('/patient/care-team-visibility',{'get':('listCareTeamVisibility','Clinical workflow','Patient owns pair-scoped grants',None,None)})
add('/care-team/visibility',{'post':('setCareTeamVisibility','Clinical workflow','Grant or revoke pair presence only',{'type':'object','required':['doctor_a','doctor_b','allow'], 'properties':{'doctor_a':{'type':'string'},'doctor_b':{'type':'string'},'allow':{'type':'boolean'}}},None)})
add('/doctors/{doctor_id}/shared-patients',{'get':('listSharedPairPseudonyms','Doctor','Minimal pair-specific pseudonyms, no counts of hidden patients',None,None)})
add('/threads/{kind}/{other_id}/messages',{'get':('listSeparatedMessages','Clinical workflow','Separated doctor_peer vs patient_doctor',None,None),
 'post':('postSeparatedMessage','Clinical workflow','Participants only, no implicit clinical share',T,'ThreadMessage')})
add('/patients/me/clinical',{'get':('patientClinicalRecords','Patient','Patient-only clinician-confirmed records',None,None)})
add('/doctors/me/patients/{patient_id}/clinical',{'get':('clinicianScopedClinical','Doctor','Grant filtered diagnoses and medications',None,None)})
add('/doctors/me/patients/{patient_id}/diagnoses',{'post':('confirmClinicalDiagnosis','Doctor','Clinician-confirmed condition only',{'type':'object','required':['label'],'properties':{'label':{'type':'string'}}},None)})
add('/doctors/me/patients/{patient_id}/medications',{'post':('addClinicianMedication','Doctor','Clinical link medication scope required',{'type':'object','required':['label'],'properties':{'label':{'type':'string'}}},None)})
add('/instruments',{'get':('listInstrumentMetadata','Clinical workflow','Instrument metadata; licensed item text omitted',None,None)})
add('/instruments/assignments',{'get':('listInstrumentAssignments','Clinical workflow','Assignment ACL',None,None),'post':('assignInstrument','Clinical workflow','Requires clinical link',{'type':'object','required':['patient_id','instrument_id'],'properties':{'patient_id':{'type':'string'},'instrument_id':{'type':'string'}}},None)})
add('/instruments/assignments/{assignment_id}/submit',{'post':('submitInstrumentResult','Patient','Validate scores; no diagnosis',{'type':'object','required':['scores'],'properties':{'scores':{'type':'array','items':{'type':'integer','minimum':0,'maximum':3}}}},None)})
add('/research/cohorts',{'get':('recomputeStudyAggregates','Research','Filters, missing values, small-cell suppression',None,'ResearchAggregates')})
add('/research/export',{'get':('exportStudyAggregates','Research','CSV aggregates only',None,None)})
add('/research/synthetic-summary',{'get':('legacyResearchSyntheticSummary','Research','Legacy metrics, dynamically recomputed',None,None)})
add('/ai/summary-drafts',{'post':('createMockSummaryDraft','AI','disabled, deterministic_mock, approved_provider fail-closed',{'type':'object','required':['recipient_doctor_id'],'properties':{'recipient_doctor_id':{'type':'string'}}},None)})
add('/ai/summary-drafts/{draft_id}/approve',{'post':('approveSummaryRecipient','AI','Explicit patient review & recipient approval',{'type':'object','required':['approve'],'properties':{'approve':{'const':True}}},None)})
add('/doctors/me/ai-summaries',{'get':('getApprovedSummaries','AI','Only specifically approved recipient',None,None)})
add('/audit/me',{'get':('readOwnAudit','Auth','No arbitrary actor lookup',None,None)})
add('/patients/me/clinical-links/{doctor_id}',{'delete':('revokeOwnClinicalLink','Patient','Patient revocation invalidates clinical access and paired presence',None,None)})
add('/previsit-cases/{case_id}/withdraw',{'post':('withdrawCaseConsent','Patient','Revoke doctor access to case snapshot and chat',{'type':'object'},None)})
add('/patients/me/check-ins',{'get':('listPatientCheckins','Patient','Read own minimized self-report trend points',None,None)})
add('/patients/me/links',{'get':('listPatientLinkedClinicians','Patient','Server-verified links only',None,None)})
add('/doctors/me/linked-patients',{'get':('listClinicianLinkedAccounts','Doctor','Tenant and grant scoped chat recipients',None,None)})
# Refine user-facing contract: status proof is server route coverage, not clinical safety.
p.write_text(yaml.safe_dump(spec,allow_unicode=True,sort_keys=False,width=110))
print('extended',counter,'operations; total',len(paths),'paths')
