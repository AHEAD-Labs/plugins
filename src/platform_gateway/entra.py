"""Microsoft Entra ID token validation (replaces the demo IdP when GMO_ENTRA_TENANT is set).

Validates RS256 signature against the tenant's published keys, plus issuer, audience and expiry.
Normalises the claims to what the gateway uses: user, scopes, expiry."""
import os

import jwt
from jwt import PyJWKClient

_jwks: PyJWKClient | None = None


def enabled() -> bool:
    return bool(os.environ.get("GMO_ENTRA_TENANT"))


def issuer() -> str:
    return f"https://login.microsoftonline.com/{os.environ['GMO_ENTRA_TENANT']}/v2.0"


def _client() -> PyJWKClient:
    global _jwks  # kept across warm Lambda invocations; keys are cached for an hour
    if _jwks is None:
        _jwks = PyJWKClient(f"https://login.microsoftonline.com/{os.environ['GMO_ENTRA_TENANT']}/discovery/v2.0/keys",
                            cache_keys=True, lifespan=3600)
    return _jwks


def verify(token: str, audience: str | None = None) -> dict:
    key = _client().get_signing_key_from_jwt(token).key
    c = jwt.decode(token, key, algorithms=["RS256"], audience=audience or os.environ["GMO_ENTRA_AUDIENCE"],
                   issuer=issuer(), options={"require": ["exp", "aud", "iss"]})
    user = c.get("preferred_username") or c.get("upn") or c.get("oid")
    if not user:
        raise jwt.InvalidTokenError("no user identity in token")
    return {"sub": user, "scope": c.get("scp", ""), "exp": c["exp"], "oid": c.get("oid"), "azp": c.get("azp")}
