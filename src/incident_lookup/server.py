from typing import Any, Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from . import audit
from .data import ACL, INCIDENTS, NotAllowed

DENIED = "Incident not found or access denied"


def build_server(identity: Callable[[], str], *, transport: str, **kw: Any) -> FastMCP:
    mcp = FastMCP("incident-lookup", **kw)

    @mcp.tool()
    def list_incidents() -> dict[str, Any]:
        """List the incidents the calling user may see."""
        user = identity()
        items = [{"incident_id": i, "title": INCIDENTS[i]["title"]} for i in ACL.get(user, [])]
        audit.record(source="mcp", user=user, tool="list_incidents", transport=transport,
                     decision="allow", reason=f"{len(items)} incidents")
        return {"incidents": items}

    @mcp.tool()
    def get_incident(incident_id: str) -> dict[str, Any]:
        """Get severity, state and owning team for one incident (e.g. INC-101)."""
        user = identity()
        if incident_id not in INCIDENTS or incident_id not in ACL.get(user, []):
            audit.record(source="mcp", user=user, tool="get_incident", transport=transport,
                         project_id=incident_id, decision="deny", reason="NotAllowed")
            raise ToolError(DENIED)
        audit.record(source="mcp", user=user, tool="get_incident", transport=transport,
                     project_id=incident_id, decision="allow")
        return {"incident_id": incident_id, **INCIDENTS[incident_id]}

    return mcp


def schema_server() -> FastMCP:
    """Used by the pipeline to derive the tool schema digest from the built artifact."""
    return build_server(lambda: "x", transport="stdio")
