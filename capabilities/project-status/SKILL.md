---
name: project-status
description: Look up project lists and delivery status via the governed Project Status MCP. Use when the user asks which projects exist or what the status of a project (e.g. PRJ-001) is.
---

# Project Status

Use the `project-status` MCP tools. They are read-only.

1. If the user does not give a project id, call `list_projects` first and let them choose.
2. For a specific project call `get_project_status(project_id)`.
3. Report status, percent complete and next milestone. Do not guess values the tool did not return.
4. "Project not found or access denied" means the user lacks access. Say so; do not retry with other ids to probe for access.
5. For Azure tag questions use `check_tag_compliance` (remote server only). It calls the governed tag-compliance agent as the signed-in user. If the agent asks which subscription or resource group, ask the user and send the reply in `answer`.
