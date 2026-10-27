"""At-least-once durable worker + separately committed idempotent test receiver."""
import json,time,uuid,threading
from sqlalchemy import select,update,or_,and_
from sqlalchemy.exc import SQLAlchemyError,IntegrityError
from werkzeug.exceptions import HTTPException
from .models import User
from .safety_models import SafetyDetection,SafetyOutbox,SafetyAttempt,SafetyInbox
from .safety_service import authorize,audit,enabled
from .clinical_copilot_services import now,dump

class TestInboxTransport:
    def __init__(self,app,factory):self.app=app;self.factory=factory
    def receive(self,outbox_id):
        # Separate committed transaction. Receiver validates ACL under source/grant locks.
        with self.factory.begin() as db:
            out=db.get(SafetyOutbox,outbox_id);det=db.get(SafetyDetection,out.detection_id)
            doctor=db.get(User,det.recipient_id)
            authorize(db,doctor,det.signal_id,lock=True)
            existing=db.scalar(select(SafetyInbox).where(SafetyInbox.outbox_id==outbox_id))
            if existing:return existing.id
            receipt='si_'+uuid.uuid4().hex
            envelope=dict(event_ref=out.id,version=1,created_at=out.created_at,deep_link='/#/doctor/alerts/safety-'+det.signal_id)
            db.add(SafetyInbox(id=receipt,outbox_id=out.id,recipient_id=det.recipient_id,envelope_json=dump(envelope),received_at=now()))
            audit(db,doctor.id,'safety_inbox_received',receipt)
            return receipt

class SafetyRuntime:
    def __init__(self,app,factory):
        self.app=app;self.factory=factory;self.transport=TestInboxTransport(app,factory);self.stop=threading.Event()
    def start(self):
        def loop():
            while not self.stop.is_set():
                try:
                    if not self.run_once():self.stop.wait(.5)
                except SQLAlchemyError:self.stop.wait(1)
        threading.Thread(target=loop,daemon=True,name='cc-safety-outbox').start()
    def close(self):self.stop.set()
    def run_once(self,at=None):
        if not enabled(self.app):return False
        at=time.time() if at is None else at
        token=uuid.uuid4().hex
        with self.factory.begin() as db:
            ready=and_(SafetyOutbox.attempts<5,or_(and_(SafetyOutbox.status.in_(('queued','retry_pending')),SafetyOutbox.next_at<=at),and_(SafetyOutbox.status=='claimed',SafetyOutbox.lease_until<=at)))
            ident=db.scalar(select(SafetyOutbox.id).where(ready).order_by(SafetyOutbox.created_at).limit(1))
            if not ident:
                # Last crashed attempt exhausts bounds too.
                db.execute(update(SafetyOutbox).where(SafetyOutbox.status=='claimed',SafetyOutbox.lease_until<=at,SafetyOutbox.attempts>=5).values(status='dead_letter',lease_token=''))
                return False
            changed=db.execute(update(SafetyOutbox).where(SafetyOutbox.id==ident,ready).values(status='claimed',lease_token=token,lease_until=at+30,attempts=SafetyOutbox.attempts+1))
            if changed.rowcount!=1:return False
            db.execute(update(SafetyAttempt).where(SafetyAttempt.outbox_id==ident,SafetyAttempt.status=='claimed').values(status='lease_expired',finished_at=now()))
            out=db.get(SafetyOutbox,ident,populate_existing=True);number=out.attempts
            db.add(SafetyAttempt(id='st_'+uuid.uuid4().hex,outbox_id=ident,number=number,status='claimed',created_at=now(),finished_at='',receipt=''))
        status='delivered';receipt=''
        try:
            hook=self.app.extensions.get('safety_before_receive')
            if hook:hook(ident)
            receipt=self.transport.receive(ident)
            # Test crash hook raises BaseException: sender lease remains claimed, receiver durable.
            hook=self.app.extensions.get('safety_after_receive')
            if hook:hook(ident)
        except HTTPException:status='invalidated'
        except (OSError,TimeoutError,SQLAlchemyError):status='dead_letter' if number>=5 else 'retry_pending'
        with self.factory.begin() as db:
            out=db.scalar(select(SafetyOutbox).where(SafetyOutbox.id==ident,SafetyOutbox.lease_token==token,SafetyOutbox.status=='claimed'))
            if not out:return True
            if status=='delivered':
                det=db.get(SafetyDetection,out.detection_id)
                try:authorize(db,db.get(User,det.recipient_id),det.signal_id,lock=True)
                except HTTPException:status='invalidated'
            changed=db.execute(update(SafetyOutbox).where(SafetyOutbox.id==ident,SafetyOutbox.lease_token==token,SafetyOutbox.status=='claimed').values(status=status,receipt=receipt,delivered_at=now() if status=='delivered' else '',lease_token='',lease_until=0,next_at=at+min(2**number,60)))
            if changed.rowcount!=1:return True
            attempt=db.scalar(select(SafetyAttempt).where(SafetyAttempt.outbox_id==ident,SafetyAttempt.number==number))
            attempt.status=status;attempt.receipt=receipt;attempt.finished_at=now()
            if status=='invalidated':db.get(SafetyDetection,out.detection_id).status='invalidated'
        return True
