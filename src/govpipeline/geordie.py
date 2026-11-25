"""Geordie policies as code, and the approved/blocked MCP list generated from the signed registry.

The repo is the source of truth. `gmo geordie` validates the policy files and writes, under the catalogue folder:
  geordie/policies.json      the policies, plus exceptions that have not expired
  geordie/approved-mcp.json  approved capabilities (remote by URL, local by package digest) and a blocked list
How Geordie ingests these is not confirmed: an adapter is added once its import method is known.
"""
import datetime, json, os

import yaml

from platform_gateway import revocations
from . import deployer
from .registry import Registry
from .workspace import Workspace

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DIR = os.path.join(REPO, "policies", "geordie")
MODES = {"monitor", "nudge", "block", "alert"}
OBJECTIVES = {"unauthorized-mcp", "data-leak"}


def load(dir_: str = DIR) -> tuple[list[dict], list[dict]]:
    pols = (yaml.safe_load(open(os.path.join(dir_, "policies.yaml"))) or {}).get("policies", [])
    exc = (yaml.safe_load(open(os.path.join(dir_, "exceptions.yaml"))) or {}).get("exceptions", [])
    return pols, exc


def validate(pols: list[dict], exceptions: list[dict], today: datetime.date | None = None) -> list[str]:
    today, errs, ids = today or datetime.date.today(), [], set()
    for p in pols:
        i = p.get("id", "?")
        if i in ids: errs.append(f"{i}: duplicate id")
        ids.add(i)
        if not p.get("name"): errs.append(f"{i}: name is blank")
        if p.get("objective") not in OBJECTIVES: errs.append(f"{i}: objective must be one of {sorted(OBJECTIVES)}")
        if not p.get("owner"): errs.append(f"{i}: owner is blank")
        if p.get("mode") not in MODES: errs.append(f"{i}: mode must be one of {sorted(MODES)}")
        if p.get("next_mode") and p["next_mode"] not in MODES: errs.append(f"{i}: next_mode must be one of {sorted(MODES)}")
        if not (p.get("when") or {}).get("event"): errs.append(f"{i}: when.event is missing")
        if p.get("mode") in ("nudge", "block") and not p.get("message"): errs.append(f"{i}: {p['mode']} needs a message for the user")
        if p.get("mode") == "block" and not (p.get("approved_by") and p.get("monitor_since")):
            errs.append(f"{i}: block needs approved_by and monitor_since (a policy starts in monitor)")
    for e in exceptions:
        i = e.get("id", "?")
        if e.get("policy") not in ids: errs.append(f"{i}: policy {e.get('policy')} does not exist")
        if not (e.get("owner") and e.get("target") and e.get("reason")): errs.append(f"{i}: needs owner, target and reason")
        try:
            if datetime.date.fromisoformat(str(e.get("expires"))) < today: errs.append(f"{i}: expired on {e['expires']}")
        except ValueError:
            errs.append(f"{i}: expires must be a date (YYYY-MM-DD)")
    return errs


def approved_list(ws: Workspace) -> dict:
    reg, approved, blocked = Registry(ws.registry), [], []
    for cap in reg.capabilities():
        vers = reg.versions(cap)
        if not vers: continue
        rec = reg.load(cap, vers[-1])
        aws = deployer.state(ws, f"aws-{cap}")
        entry = {"capability_id": cap, "kind": rec.get("kind", "mcp"), "version": rec["version"], "name": rec["name"],
                 "classification": rec["classification"], "owner": rec["owner"], "tools": sorted(rec["tools"]),
                 "schema_digest": rec["schema_digest"], "identify": []}
        for d in rec["deployments"]:
            if d["transport"] == "streamable-http":
                entry["identify"].append({"remote_url": aws.get("endpoint", d["endpoint"])})
            else:
                entry["identify"].append({"local_package": d["package"]["entrypoint"], "artifact_sha256": rec["artifact"]["sha256"]})
        (blocked if revocations.check(cap, rec["version"], None) else approved).append(entry)
    return {"generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "approved": approved, "blocked": blocked}


def write(ws: Workspace, dir_: str = DIR) -> str:
    pols, exc = load(dir_)
    errs = validate(pols, exc)
    if errs:
        raise ValueError("geordie policies invalid: " + "; ".join(errs))
    out = os.path.join(ws.catalogue, "geordie")
    os.makedirs(out, exist_ok=True)
    json.dump({"version": 1, "policies": pols, "exceptions": exc}, open(os.path.join(out, "policies.json"), "w"), indent=2)
    json.dump(approved_list(ws), open(os.path.join(out, "approved-mcp.json"), "w"), indent=2)
    return out
