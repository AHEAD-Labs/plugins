"""Project Status as a container behind a ToolHive proxy (kind mcp-image).

The proxy validates the user's token and applies Cedar policy; this process only serves MCP on port 8080 and
needs to know WHO is asking, because project access depends on the user. It reads the user from the bearer
token the proxy forwards. It does NOT verify the signature: the proxy already did, so this is only safe when
the proxy is the only thing that can reach the port (a NetworkPolicy). It therefore refuses to start unless
GMO_TRUST_PROXY=1 says that is true, and it fails closed: no token, no user, no data.

TO CONFIRM on a cluster: what ToolHive actually forwards (the user's token, or the upstream Entra token it
injects). The claim names tried below cover both.
"""
import base64, contextvars, json, os

from .audit import CORRELATION
from .backend import InProcessBackend
from .server import build_server

USER: contextvars.ContextVar[str | None] = contextvars.ContextVar("gmo_proxy_user", default=None)
CLAIMS = ("preferred_username", "upn", "email", "unique_name", "sub")


def user_from_bearer(header: str | None) -> str | None:
    if not header or not header.lower().startswith("bearer "):
        return None
    try:
        body = header.split(None, 1)[1].split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (IndexError, ValueError):
        return None
    return next((str(claims[c]).lower() for c in CLAIMS if claims.get(c)), None)


class ProxyIdentity:
    """ASGI middleware: put the caller (and correlation id) of this request where the tools can read it."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            h = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            USER.set(user_from_bearer(h.get("authorization")))
            CORRELATION.set((h.get("x-correlation-id") or "")[:64] or None)
        await self.app(scope, receive, send)


def identity() -> str:
    user = USER.get()
    if not user:
        raise PermissionError("no caller identity on the request")  # the tool refuses; nothing is returned
    return user


def build():
    mcp = build_server(InProcessBackend(), identity, transport="streamable-http", host="0.0.0.0", port=8080,
                       streamable_http_path="/mcp", stateless_http=True, json_response=True)
    return ProxyIdentity(mcp.streamable_http_app())


def main() -> None:
    if os.environ.get("GMO_TRUST_PROXY") != "1":
        raise SystemExit("refusing to start: set GMO_TRUST_PROXY=1 only when the ToolHive proxy is the sole way to reach this port")
    import uvicorn
    uvicorn.run(build(), host="0.0.0.0", port=8080, log_level="warning")


if __name__ == "__main__":
    main()
