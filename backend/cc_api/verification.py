"""Explicit synthetic-dev verification adapters; these confer no clinical authority."""
import re


def synthetic_enabled(config):
    return bool(config.get('DEMO_MODE')) and config.get('APP_ENV') == 'synthetic_dev'


def evaluation_enabled(config):
    return (config.get('APP_ENV') == 'evaluation_sandbox'
        and config.get('EVALUATION_ACKNOWLEDGED') is True
        and config.get('EVALUATION_TENANT') == 'evaluation_sandbox'
        and bool(config.get('DEMO_MODE')))


def workspace_enabled(config):
    """Technical availability only; does not grant roles, consent or clinical approval."""
    return synthetic_enabled(config) or evaluation_enabled(config)


def normalize_synthetic_email(value):
    if not isinstance(value, str):
        raise ValueError('Synthetic email required')
    email = value.strip().lower()
    if len(email) > 254 or not re.fullmatch(r'[a-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', email):
        raise ValueError('Invalid email')
    domain = email.rsplit('@', 1)[1]
    if not domain.endswith(('.test', '.example')) or '..' in domain:
        raise ValueError('Use a reserved .test or .example synthetic address')
    return email


class SyntheticEmailVerifier:
    provider = 'synthetic_auto'

    def verify(self, email, config):
        if evaluation_enabled(config):
            normalize_synthetic_email(email)
            return {'provider': 'evaluation_local_account', 'status': 'not_verified'}
        if not synthetic_enabled(config):
            raise RuntimeError('Synthetic verification requires explicit synthetic_dev profile')
        normalize_synthetic_email(email)
        return {'provider': self.provider, 'status': 'verified_synthetic'}


class SyntheticProfessionalVerifier:
    provider = 'synthetic_auto'

    def verify(self, user, config):
        if not synthetic_enabled(config):
            raise RuntimeError('Synthetic verification requires explicit synthetic_dev profile')
        if user.role != 'doctor':
            raise ValueError('Existing authorized physician required')
        return {'provider': self.provider, 'status': 'verified_synthetic',
                'scope': 'synthetic_dev', 'grants_roles': False, 'mfa_verified': False}
