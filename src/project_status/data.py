"""Synthetic project data + the authorization rules that guard it."""
PROJECTS = {
    "PRJ-001": {"name": "Atlas Migration", "status": "on_track", "percent_complete": 72,
                "next_milestone": "Cutover rehearsal", "updated": "2026-11-05"},
    "PRJ-002": {"name": "Helios Data Platform", "status": "at_risk", "percent_complete": 41,
                "next_milestone": "Ingestion SLA sign-off", "updated": "2026-11-09"},
    "PRJ-003": {"name": "Orion Security Uplift", "status": "blocked", "percent_complete": 18,
                "next_milestone": "Vendor access approval", "updated": "2026-11-02"},
    "PRJ-004": {"name": "Zephyr Pilot", "status": "completed", "percent_complete": 100,
                "next_milestone": "Retrospective", "updated": "2026-10-28"},
}
ACL = {
    "alice": ["PRJ-001", "PRJ-002", "PRJ-003", "PRJ-004"],
    "bob": ["PRJ-001"],
    "carol": ["PRJ-002", "PRJ-003"],
}


class NotFound(Exception):
    pass


class AccessDenied(Exception):
    pass


def list_for(user: str) -> list[dict]:
    return [{"project_id": p, "name": PROJECTS[p]["name"]} for p in ACL.get(user, [])]


def status_for(user: str, project_id: str) -> dict:
    if project_id not in PROJECTS:
        raise NotFound(project_id)
    if project_id not in ACL.get(user, []):
        raise AccessDenied(project_id)
    return {"project_id": project_id, **PROJECTS[project_id]}
