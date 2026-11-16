"""Reconcile: the registry, the deployments and the catalogue must agree on version, status and endpoint (R3).
Each run gets its own correlation id. A source that cannot be read is reported as unknown, never as agreeing."""
import json, os, time, uuid

from platform_gateway import revocations
from . import deployer
from .registry import Registry
from .workspace import Workspace


def run(ws: Workspace) -> dict:
    reg, findings, checked = Registry(ws.registry), [], []
    feed_path = os.path.join(ws.catalogue, "feed.json")
    feed = {e["capability_id"]: e for e in json.load(open(feed_path))["entries"]} if os.path.exists(feed_path) else None
    add = lambda cap, kind, detail: findings.append({"capability_id": cap, "kind": kind, "detail": detail})
    if feed is None:
        add("*", "catalogue-unreadable", f"{feed_path} not found: cannot compare the catalogue")
    for cap in reg.capabilities():
        vers = reg.versions(cap)
        if not vers:
            continue
        rec = reg.load(cap, vers[-1])
        latest, sus = rec["version"], bool(revocations.check(cap, rec["version"], None))
        checked.append(cap)
        if feed is not None and "oasis" in rec["distribution"]:
            e = feed.get(cap)
            if not e:
                add(cap, "missing-from-catalogue", f"{cap}@{latest} is approved but not in the feed")
            else:
                if e["version"] != latest:
                    add(cap, "catalogue-version-differs", f"feed {e['version']} vs registry {latest}")
                if (e["status"] == "suspended") != sus:
                    add(cap, "catalogue-status-differs", f"feed says {e['status']}, suspension list says {'suspended' if sus else 'not suspended'}")
        st = deployer.state(ws, f"aws-{cap}")
        if st:
            if st.get("version") != latest:
                add(cap, "deployment-version-differs", f"deployed {st.get('version')} vs registry {latest}")
            if feed is not None and cap in feed:
                ep = (feed[cap]["install"].get("remote") or {}).get("endpoint")
                if ep and ep != st.get("endpoint"):
                    add(cap, "endpoint-differs", f"catalogue {ep} vs deployment {st.get('endpoint')}")
    return {"run_id": uuid.uuid4().hex, "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "checked": checked, "drift": findings, "in_agreement": not findings}
