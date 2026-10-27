"""Synthetic invited-professional status, separate from role-grant authority."""
from flask import request
from .oidc_browser import browser_user, settings


def invited_enrollment_enabled(config):
    return config.get('APP_ENV')=='synthetic_dev' and settings() is not None


class SyntheticInvitedProfessionalVerifier:
    """No real credential/email verification; never assigns application roles."""
    provider='synthetic_invited_auto'

    def verify(self, db, candidate, config):
        if not invited_enrollment_enabled(config):
            raise RuntimeError('Explicit synthetic_dev and configured browser OIDC required')
        # browser_user checks expiry, issuer, current provisioned subject/role and
        # genuine IdP MFA assurance. No request payload can supply assurance.
        authenticated=browser_user(db)
        if (request.headers.get('Authorization') or not authenticated or
                authenticated.id!=candidate.id or authenticated.role!='staff_candidate'):
            raise ValueError('Genuine candidate OIDC/MFA browser session required')
        return {'provider':self.provider,'status':'verified_synthetic','scope':'synthetic_dev',
                'grants_roles':False,'mfa_verified':True,'real_credentials_verified':False,
                'real_email_verified':False}
