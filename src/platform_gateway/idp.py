"""Demo identity provider. Stand-in for Entra/Okta: mints and verifies audience-bound JWTs."""
import os, time
import jwt

ISSUER = "http://127.0.0.1:8802/idp"
BACKEND_AUDIENCE = "gmo-backend"
SECRET = lambda: os.environ.get("GMO_IDP_SECRET", "dev-only-secret-do-not-use-in-production-0123456789")


def mint(sub: str, aud: str, scope: str = "project-status:read", ttl: int = 3600) -> str:
    now = int(time.time())
    return jwt.encode({"iss": ISSUER, "sub": sub, "aud": aud, "scope": scope,
                       "iat": now, "exp": now + ttl}, SECRET(), algorithm="HS256")


def verify(token: str, aud: str) -> dict:
    return jwt.decode(token, SECRET(), algorithms=["HS256"], audience=aud, issuer=ISSUER,
                      options={"require": ["exp", "sub", "aud"]})
