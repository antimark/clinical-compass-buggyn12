"""Seeded demo credentials: fixed hashes, never plain text. Synthetic-dev only.

Passwords are delivered separately to the project owner in a TXT document.
All user identities and permissions remain those in the existing demo database.
"""
from sqlalchemy import select
from .models import User
from .onboarding_models import LocalIdentity
from .utilities import utc_now

# User id, synthetic email, PBKDF2-SHA256 password hash.
DEMO_ACCOUNT_HASHES = [
    ('pat_01', 'pat_01@compass-demo.test', 'pbkdf2:sha256:600000$37f0550939fe02514990ef82b85d40fe$9f64d43c37bb293c802bba25cdedcaa46fd5ab8a92501b256bd86f9c4e608dfd'),
    ('pat_02', 'pat_02@compass-demo.test', 'pbkdf2:sha256:600000$14d4a2a3ef5d6c64a9ee6957b1bd1bff$2765acd07ecafd3f574992ac1f7185b10df2f77873742e513aec68799076a6a6'),
    ('pat_03', 'pat_03@compass-demo.test', 'pbkdf2:sha256:600000$ea78b653df06fe15b124bf8ac5decfeb$3717671ceea1c6902b30fa5dd24fb9a6013753c35c575aa338e50e23f8e09724'),
    ('doc_psy', 'doc_psy@compass-demo.test', 'pbkdf2:sha256:600000$b6bc0885609e355b4acd5d11cdbbd9c3$febc76d09b80729966446f67e9de265864a977c5ce383cbcc526f2a3302b512f'),
    ('doc_ther', 'doc_ther@compass-demo.test', 'pbkdf2:sha256:600000$93b0fe722479cb439b83de13abf16c75$156f928a14f411234ceaba2d154d6184de4c3250bd5f174098f1979ee21913fc'),
    ('doc_other', 'doc_other@compass-demo.test', 'pbkdf2:sha256:600000$487bbd64b30bddd2ead0f5992daeb9a6$f2e35e672d901a08f9acf2984dc698056dc83de6744e475150490c63672abb3c'),
    ('clinic_01', 'clinic_01@compass-demo.test', 'pbkdf2:sha256:600000$c8d13b27d23d0b43a0ef4ff4fa04c509$07bdf061970ff983d788abd490afb8716b495f8c7da539724c743ce0146d7948'),
    ('researcher_01', 'researcher_01@compass-demo.test', 'pbkdf2:sha256:600000$0804ee04afe6b6179a94fe125bd919fa$168335b34495280155381d9c3d458780db8c920d104711ebd5bebaab88d960ae'),
    ('platform_01', 'platform_01@compass-demo.test', 'pbkdf2:sha256:600000$57f6b39871f79190e245fa8f5bb92b2f$1f302d1991b747b417aef0908593c1d4674933f3c570a9e306929680acbe02c3'),
 ]

def seed_demo_accounts(SessionLocal):
    # Run on each synthetic-dev startup: also migrates existing fixture databases.
    # Never reset user-supplied local passwords or overwrite unrelated identities.
    with SessionLocal.begin() as db:
        for user_id, email, password_hash in DEMO_ACCOUNT_HASHES:
            user = db.get(User, user_id)
            if user is None:
                raise RuntimeError(f'Missing seeded demo user: {user_id}')
            if db.get(LocalIdentity, user_id):
                continue
            other = db.scalar(select(LocalIdentity).where(LocalIdentity.email == email))
            if other:
                raise RuntimeError(f'Demo email already registered to another identity: {email}')
            db.add(LocalIdentity(user_id=user_id, email=email,
                password_hash=password_hash, email_provider='synthetic_seed',
                email_status='verified_synthetic', created_at=utc_now()))
