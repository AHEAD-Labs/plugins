"""One implementation, any transport. Hosts (stdio launcher, platform gateway) inject
the backend, the identity source and transport-specific FastMCP settings."""
from typing import Any, Awaitable, Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from . import audit
from .backend import Backend
from .data import AccessDenied, NotFound

DENIED_MSG = "Project not found or access denied"


AGENT_ID = "ahead.tag-compliance"


def build_server(backend: Backend, identity: Callable[[], str], *, transport: str,
                 agent: Callable[[str, str], Awaitable[str]] | None = None,
                 **fastmcp_kwargs: Any) -> FastMCP:
    """`agent(request, answer)` calls the governed Azure agent as the signed-in user. Only the remote,
    Entra-protected host provides it; on any other transport the tool exists (same schema) but refuses."""
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

    @mcp.tool()
    async def check_tag_compliance(request: str, answer: str = "") -> dict[str, Any]:
        """Ask the Azure tag-compliance agent which resources in a resource group lack an owner tag.
        If the agent asks for a subscription or resource group, send the user's reply in `answer`."""
        user = identity()
        if agent is None:
            audit.record(source="mcp", user=user, tool="check_tag_compliance", transport=transport,
                         decision="deny", reason="agent_needs_signed_in_remote_session")
            raise ToolError("The tag-compliance agent is only available on the signed-in remote server")
        try:
            text = await agent(request, answer)
        except PermissionError as e:
            audit.record(source="mcp", user=user, tool="check_tag_compliance", transport=transport,
                         decision="deny", reason=f"{AGENT_ID}: {e}")
            raise ToolError("The agent refused this request")
        except Exception as e:
            audit.record(source="mcp", user=user, tool="check_tag_compliance", transport=transport,
                         decision="deny", reason=f"{AGENT_ID}: unavailable ({type(e).__name__})")
            raise ToolError("The agent is not available right now")
        audit.record(source="mcp", user=user, tool="check_tag_compliance", transport=transport,
                     decision="allow", reason=f"called {AGENT_ID} on the user's behalf")
        return {"agent": AGENT_ID, "answer": text}

    return mcp


def schema_server() -> FastMCP:
    """Used by the pipeline to derive the tool schema digest from the built artifact."""
    from .backend import InProcessBackend
    return build_server(InProcessBackend(), lambda: "x", transport="stdio")
