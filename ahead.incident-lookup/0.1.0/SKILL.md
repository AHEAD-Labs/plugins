---
name: incident-lookup
description: Look up open and recent incidents via the governed Incident Lookup MCP. Use when the user asks which incidents exist or what the state of one (e.g. INC-101) is.
---

# Incident Lookup

Use the `incident-lookup` MCP tools. They are read-only.

1. If the user gives no incident id, call `list_incidents` first.
2. For one incident call `get_incident(incident_id)` and report severity, state and owning team.
3. "Incident not found or access denied" means the user lacks access. Say so; do not probe other ids.
