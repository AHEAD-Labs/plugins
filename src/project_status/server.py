"""One implementation, any transport. Hosts (stdio launcher, platform gateway) inject
the backend, the identity source and transport-specific FastMCP settings."""
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from . import audit
from .backend import Backend
from .data import AccessDenied, NotFound

DENIED_MSG = "Project not found or access denied"


def build_server(backend: Backend, identity: Callable[[], str], *, transport: str,
                 **fastmcp_kwargs: Any) -> FastMCP:
    mcp = FastMCP("project-status", **fastmcp_kwargs)

    @mcp.tool()
    async def list_projects() -> dict[str, Any]:
        """List the projects the calling user is allowed to see."""
        user = identity()
        projects = await backend.list_projects(user)
        audit.record(source="mcp", user=user, tool="list_projects", transport=transport,
                     decision="allow", reason=f"{len(projects)} projects")
        return {"projects": projects}

    @mcp.tool()
    async def get_project_status(project_id: str) -> dict[str, Any]:
        """Get status, percent complete and next milestone for one project (e.g. PRJ-001)."""
        user = identity()
        try:
            result = await backend.get_status(user, project_id)
        except (AccessDenied, NotFound) as e:
            audit.record(source="mcp", user=user, tool="get_project_status", transport=transport,
                         project_id=project_id, decision="deny", reason=type(e).__name__)
            raise ToolError(DENIED_MSG)  # same message either way: no project enumeration
        audit.record(source="mcp", user=user, tool="get_project_status", transport=transport,
                     project_id=project_id, decision="allow")
        return result

    return mcp


def schema_server() -> FastMCP:
    """Used by the pipeline to derive the tool schema digest from the built artifact."""
    from .backend import InProcessBackend
    return build_server(InProcessBackend(), lambda: "x", transport="stdio")
