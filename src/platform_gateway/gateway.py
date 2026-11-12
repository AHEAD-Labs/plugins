"""Native platform gateway (stand-in): OAuth bearer validation, audience binding,
scope check, suspension check, and denial audit — before any MCP code runs."""
from mcp.server.auth.provider import AccessToken, TokenVerifier

from project_status import CAPABILITY_ID, __version__, audit
from . import idp, revocations

REQUIRED_SCOPE = "project-status:read"


class GatewayAccessToken(AccessToken):
    subject: str


class GatewayTokenVerifier(TokenVerifier):
    def __init__(self, audience: str):
        self.audience = audience

    def _deny(self, user, reason):
        audit.record(source="gateway", user=user, tool=None, transport="streamable-http",
                     decision="deny", reason=reason)
        return None

    async def verify_token(self, token: str) -> GatewayAccessToken | None:
        try:
            claims = idp.verify(token, self.audience)
        except Exception as e:  # bad signature, expired, wrong audience/issuer
            return self._deny(None, f"invalid_token:{type(e).__name__}")
        user = claims["sub"]
        scopes = claims.get("scope", "").split()
        if REQUIRED_SCOPE not in scopes:
            return self._deny(user, "insufficient_scope")
        reason = revocations.check(CAPABILITY_ID, __version__, user)
        if reason:
            return self._deny(user, f"suspended:{reason}")
        return GatewayAccessToken(token=token, client_id=user, subject=user, scopes=scopes,
                                  expires_at=claims["exp"], resource=self.audience)
