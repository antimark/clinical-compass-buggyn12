"""Pinned-key OIDC validation; browser identity never grants application roles."""
import json
import os
import jwt
from flask import request


def decode_identity_token(token, *, audience=None):
    keyset = json.loads(os.environ['CC_OIDC_JWKS_JSON'])
    header = jwt.get_unverified_header(token)
    algorithm = header.get('alg')
    if algorithm not in ('RS256', 'ES256'):
        raise ValueError('Unsupported token algorithm')
    key = next((k for k in keyset['keys'] if k.get('kid') == header.get('kid')
                and k.get('use', 'sig') == 'sig' and k.get('alg', algorithm) == algorithm), None)
    if key is None:
        raise ValueError('Unknown signing key')
    claims = jwt.decode(token, key=jwt.PyJWK.from_dict(key).key, algorithms=[algorithm],
        issuer=os.environ['CC_OIDC_ISSUER'], audience=audience or os.environ['CC_OIDC_AUDIENCE'],
        options={'require': ['sub', 'exp', 'iat', 'iss', 'aud']}, leeway=0)
    if not isinstance(claims['sub'], str) or not claims['sub']:
        raise ValueError('Invalid subject')
    return claims


def has_staff_assurance(claims):
    amr = claims.get('amr', [])
    acr = claims.get('acr')
    accepted_acr = {value.strip() for value in os.environ.get('CC_OIDC_MFA_ACR', 'urn:mfa').split(',') if value.strip()}
    return ((isinstance(amr, list) and all(isinstance(value, str) for value in amr)
             and ('mfa' in amr or {'pwd', 'otp'}.issubset(amr))) or
        (isinstance(acr, str) and acr in accepted_acr))


def verified_subject():
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return None
    claims = decode_identity_token(header[7:])
    return claims['sub'] if has_staff_assurance(claims) else None
