"""Gateway in front of the Azure tag-compliance agent (a Container App).

Every call is checked BEFORE it reaches the agent:
  1. a valid Entra token for THIS API (signature, issuer, audience, expiry)
  2. the tag-compliance:read scope
  3. the calling app (azp) is on the allowed-callers list: user token via OBO or Codex only
  4. the capability is not suspended (shared Azure Blob list, short cache, fails closed)
Then it forwards with the agent's own API key (the user's token is never passed on) and writes one
audit line per decision: user, calling app, capability, version, tool, decision.
"""
import json, os, time, uuid

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from platform_gateway import entra, revocations

CAP = os.environ.get("GMO_CAPABILITY_ID", "ahead.tag-compliance")
VER = os.environ.get("CAPABILITY_VERSION", "0.1.0")
SCOPE = os.environ.get("GMO_REQUIRED_SCOPE", "tag-compliance:read")
ALLOWED = {c for c in os.environ.get("GMO_ALLOWED_CALLERS", "").split(",") if c}


def audit(**kw) -> None:  # stdout -> Container Apps -> Log Analytics
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event_id": uuid.uuid4().hex,
                      "source": "gateway", "capability_id": CAP, "version": VER, "transport": "streamable-http", **kw}), flush=True)


def deny(status: int, reason: str, **ctx) -> JSONResponse:
    audit(decision="deny", reason=reason, **ctx)
    h = {"WWW-Authenticate": 'Bearer error="invalid_token"'} if status == 401 else {}
    return JSONResponse({"error": reason}, status_code=status, headers=h)


async def health(_: Request) -> Response:
    return JSONResponse({"ok": True, "capability": CAP, "version": VER})


async def mcp(request: Request) -> Response:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return deny(401, "no_token", user=None)
    try:
        c = entra.verify(auth[7:])
    except Exception as e:  # bad signature, expired, wrong audience or issuer
        return deny(401, f"invalid_token:{type(e).__name__}", user=None)
    user, caller = c["sub"], c.get("azp")
    ctx = {"user": user, "caller_app": caller}
    if SCOPE not in c["scope"].split():
        return deny(403, "insufficient_scope", **ctx)
    if ALLOWED and caller not in ALLOWED:
        return deny(403, "caller_not_allowed", **ctx)
    try:
        why = revocations.check(CAP, VER, user)
    except Exception:
        return deny(503, "revocation_list_unavailable", **ctx)  # fail closed
    if why:
        return deny(403, f"suspended:{why}", **ctx)
    body = await request.body()
    tool = None
    try:
        msg = json.loads(body)
        if isinstance(msg, dict) and msg.get("method") == "tools/call":
            tool = (msg.get("params") or {}).get("name")
    except ValueError:
        pass
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(os.environ["GMO_AGENT_URL"], content=body, headers={
            "Content-Type": "application/json", "Accept": request.headers.get("accept", "application/json"),
            "x-api-key": os.environ["GMO_AGENT_KEY"]})
    audit(decision="allow", tool=tool, upstream_status=r.status_code, **ctx)
    return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type", "application/json"))


app = Starlette(routes=[Route("/health", health), Route("/mcp", mcp, methods=["POST"])])
