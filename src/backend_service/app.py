"""Backend API (synthetic). Owns authorization: it trusts only the MCP service identity,
and decides per end-user (X-On-Behalf-Of) which projects are visible. Audits every decision."""
import os, sys

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from platform_gateway import idp
from project_status import audit, data


def _caller(request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None, JSONResponse({"error": "unauthenticated"}, 401)
    try:
        claims = idp.verify(auth[7:], idp.BACKEND_AUDIENCE)
    except Exception:
        return None, JSONResponse({"error": "invalid_token"}, 401)
    if not claims["sub"].startswith("svc:") or "backend:read" not in claims.get("scope", "").split():
        return None, JSONResponse({"error": "forbidden_service"}, 403)
    user = request.headers.get("x-on-behalf-of")
    if not user:
        return None, JSONResponse({"error": "missing_on_behalf_of"}, 400)
    return user, None


def _audit(request, user, decision, reason="", project_id=None, tool=None):
    audit.record(source="backend", user=user, tool=tool, transport="http", decision=decision,
                 reason=reason, project_id=project_id,
                 version=request.headers.get("x-capability-version"))


async def projects(request: Request):
    user, err = _caller(request)
    if err: return err
    items = data.list_for(user)
    _audit(request, user, "allow", f"{len(items)} projects", tool="GET /projects")
    return JSONResponse({"projects": items})


async def project(request: Request):
    user, err = _caller(request)
    if err: return err
    pid = request.path_params["project_id"]
    try:
        res = data.status_for(user, pid)
    except data.NotFound:
        _audit(request, user, "deny", "NotFound", pid, "GET /projects/{id}")
        return JSONResponse({"error": "not_found"}, 404)
    except data.AccessDenied:
        _audit(request, user, "deny", "AccessDenied", pid, "GET /projects/{id}")
        return JSONResponse({"error": "forbidden"}, 403)
    _audit(request, user, "allow", project_id=pid, tool="GET /projects/{id}")
    return JSONResponse(res)


async def health(_): return JSONResponse({"ok": True})


app = Starlette(routes=[Route("/healthz", health), Route("/projects", projects),
                        Route("/projects/{project_id}", project)])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("GMO_BACKEND_PORT", "8801")),
                log_level="warning")
