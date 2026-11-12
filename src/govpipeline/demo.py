"""End-to-end demonstration. Exits non-zero if any acceptance claim fails."""
import json, os, shutil, sys

import yaml

from platform_gateway import idp, revocations
from . import catalogue, deployer, mcpclient as mc
from .cli import MANIFEST, MANIFEST2
from .registry import Registry
from .release import ReleaseRejected, release
from .workspace import Workspace

CAP = "ahead.project-status"
FAILS: list[str] = []


def check(ok: bool, msg: str):
    print(("  PASS  " if ok else "  FAIL  ") + msg)
    if not ok: FAILS.append(msg)


def step(t): print(f"\n== {t}")


def audit_records(ws) -> list[dict]:
    return [json.loads(l) for l in open(ws.audit_log)] if os.path.exists(ws.audit_log) else []


def run_demo(ws_dir: str) -> int:
    if os.path.exists(ws_dir): shutil.rmtree(ws_dir)
    ws = Workspace(ws_dir)
    os.environ.update(ws.env())
    try:
        return _run(ws)
    finally:
        deployer.stop_all(ws)


def _run(ws: Workspace) -> int:
    step("1. Approval pipeline: two versions of one capability")
    v2dir = os.path.join(ws.work, "project-status-0.2.0")   # a later commit of the same capability folder
    shutil.copytree(os.path.dirname(MANIFEST), v2dir)
    m2 = os.path.join(v2dir, "manifest.yaml")
    y = yaml.safe_load(open(m2)); y["version"] = "0.2.0"
    yaml.safe_dump(y, open(m2, "w"))
    for path in (MANIFEST, m2):
        rec = release(path, ws, run_tests=True)
        n = len(rec["approval"]["checks"])
        check(rec["status"] == "approved", f"{rec['version']} approved ({n} checks, "
              f"sha256 {rec['artifact']['sha256'][:12]}…, schema {rec['schema_digest'][:12]}…)")
    try:
        release(MANIFEST, ws, run_tests=False); check(False, "re-release of 0.1.0 must be rejected")
    except ReleaseRejected:
        check(True, "re-releasing 0.1.0 is rejected (immutable releases)")

    step("2. Platform deployment (remote) + local install + catalogue update")
    deployer.start_backend(ws)
    deployer.deploy_remote(ws, CAP, "0.1.0")
    st = deployer.deploy_remote(ws, CAP, "0.2.0", reason="upgrade")
    deployer.install_local(ws, CAP, "0.2.0")
    feed = catalogue.publish(ws)
    check(st["active_version"] == "0.2.0", "remote runs 0.2.0 (post-deploy smoke test passed)")

    step("3. Discovery: read catalogue feed, use ITS install details (as Codex would)")
    entry = next(e for e in json.load(open(os.path.join(ws.catalogue, "feed.json")))["entries"]
                 if e["capability_id"] == CAP)
    check(entry["status"] == "approved" and entry["version"] == "0.2.0",
          f"feed lists {entry['capability_id']}@{entry['version']} status={entry['status']}")
    loc, rem = entry["install"]["local"], entry["install"]["remote"]
    plugin = os.path.join(ws.catalogue, "plugins", "project-status")
    check(os.path.exists(os.path.join(plugin, ".codex-plugin", "plugin.json")), "Codex plugin bundle generated")

    async def local_as(user, tool, **a):
        async with mc.stdio_session(loc["command"], loc["args"], {**loc["env"], "GMO_USER": user}) as s:
            return await mc.call(s, tool, **a)

    async def remote_as(user, tool, **a):
        async with mc.http_session(rem["endpoint"], idp.mint(user, rem["auth"]["audience"])) as s:
            return await mc.call(s, tool, **a)

    step("4. Invoke BOTH deployments")
    ok, p = mc.run(local_as("alice", "list_projects"))
    check(ok and len(p["projects"]) == 4, "local/stdio: alice lists 4 projects")
    ok, p = mc.run(remote_as("alice", "list_projects"))
    check(ok and len(p["projects"]) == 4, "remote/HTTPS+bearer: alice lists 4 projects")
    ok, p = mc.run(remote_as("alice", "get_project_status", project_id="PRJ-003"))
    check(ok and p["status"] == "blocked", "remote: get_project_status(PRJ-003) = blocked")

    step("5. Unauthorized access fails")
    check(mc.run(mc.http_status(rem["endpoint"], None)) == 401, "remote: no token -> 401")
    check(mc.run(mc.http_status(rem["endpoint"], idp.mint("alice", "https://other.example/mcp"))) == 401,
          "remote: token for another audience -> 401")
    check(mc.run(mc.http_status(rem["endpoint"], idp.mint("alice", rem["endpoint"], scope="x:y"))) == 401,
          "remote: token without scope -> 401")
    ok, p = mc.run(remote_as("bob", "get_project_status", project_id="PRJ-002"))
    check(not ok, "remote: bob denied PRJ-002 (backend authorization)")
    ok, p = mc.run(local_as("bob", "get_project_status", project_id="PRJ-002"))
    check(not ok, "local: bob denied PRJ-002")

    step("6. Audit identifies user, capability, version")
    recs = audit_records(ws)
    def has(**kw): return any(all(r.get(k) == v for k, v in kw.items()) for r in recs)
    check(has(source="mcp", user="alice", transport="stdio", capability_id=CAP, version="0.2.0", decision="allow"),
          "stdio call audited: alice / ahead.project-status / 0.2.0")
    check(has(source="mcp", user="alice", transport="streamable-http", capability_id=CAP, version="0.2.0", decision="allow"),
          "remote call audited: alice / ahead.project-status / 0.2.0")
    check(has(source="backend", user="bob", decision="deny", project_id="PRJ-002", version="0.2.0"),
          "backend denial audited: bob / PRJ-002 / 0.2.0")
    check(has(source="gateway", decision="deny"), "gateway admission denials audited")

    step("7. Catalogue removal is NOT revocation")
    feed_path = os.path.join(ws.catalogue, "feed.json")
    json.dump({"entries": []}, open(feed_path, "w"))
    ok, _ = mc.run(remote_as("alice", "list_projects"))
    check(ok, "entry removed from catalogue, remote still serves requests (so removal is not a kill switch)")

    step("8. Targeted suspension of 0.2.0 blocks remote execution")
    revocations.suspend(CAP, version="0.2.0", reason="demo: incident INC-0001", by="demo-operator")
    check(mc.run(mc.http_status(rem["endpoint"], idp.mint("alice", rem["endpoint"]))) == 401,
          "remote 0.2.0: valid alice token now rejected at the gateway")
    check(has(source="gateway", decision="deny", version="0.2.0") and
          any("suspended" in r["reason"] for r in audit_records(ws)), "suspension denial audited with reason")
    catalogue.publish(ws)
    e = next(x for x in json.load(open(feed_path))["entries"] if x["capability_id"] == CAP)
    check(e["status"] == "suspended", "catalogue regenerated and now shows status=suspended")

    step("9. Rollback restores the approved 0.1.0")
    st = deployer.rollback_remote(ws)
    check(st["active_version"] == "0.1.0", "rollback deployed 0.1.0 (digest-verified from registry)")
    ok, _ = mc.run(remote_as("alice", "list_projects"))
    check(ok, "remote works again on 0.1.0")
    check(any(r["version"] == "0.1.0" and r["source"] == "mcp" and r["transport"] == "streamable-http"
              for r in audit_records(ws)), "audit shows calls served by 0.1.0")
    check(revocations.check(CAP, "0.2.0", "alice") is not None, "0.2.0 remains suspended after rollback")

    step("10. A second capability gets its own folder, plugin and feed entry")
    CAP2 = "ahead.incident-lookup"
    rec2 = release(MANIFEST2, ws, run_tests=False)
    check(rec2["status"] == "approved", "incident-lookup 0.1.0 approved (local-only: gateway checks not applicable)")
    deployer.install_local(ws, CAP2, "0.1.0")
    feed = catalogue.publish(ws)
    plugins = os.path.join(ws.catalogue, "plugins")
    check(sorted(os.listdir(plugins)) == ["incident-lookup", "project-status"], "two plugin folders: " + ", ".join(sorted(os.listdir(plugins))))
    check(len(feed["entries"]) == 2, "feed.json has 2 entries")
    mcp2 = json.load(open(os.path.join(plugins, "incident-lookup", ".mcp.json")))["mcpServers"]
    check(list(mcp2) == ["incident-lookup-local"], "incident-lookup .mcp.json lists only its own (local) server")
    mk = lambda *p: json.load(open(os.path.join(ws.catalogue, *p, ".agents", "plugins", "marketplace.json")))["plugins"]
    check([x["name"] for x in mk()] == ["incident-lookup", "project-status"], "local marketplace.json lists both plugins")
    ow = os.path.join(ws.catalogue, "openai-workspace")
    check([x["name"] for x in mk("openai-workspace")] == ["project-status"] and os.listdir(os.path.join(ow, "plugins")) == ["project-status"],
          "OpenAI-workspace marketplace has only the plugin with a remote server (local-only incident-lookup excluded)")
    ow_mcp = json.load(open(os.path.join(ow, "plugins", "project-status", ".mcp.json")))["mcpServers"]
    check(list(ow_mcp) == ["project-status-remote"], "OpenAI-workspace plugin carries only the remote server URL")
    loc2 = deployer.state(ws, f"local-{CAP2}")

    async def inc_as(user, tool, **a):
        async with mc.stdio_session(loc2["command"], loc2["args"], {**loc2["env"], "GMO_USER": user}) as s:
            return await mc.call(s, tool, **a)
    ok, p = mc.run(inc_as("alice", "get_incident", incident_id="INC-101"))
    check(ok and p["severity"] == "sev2", "incident-lookup: alice reads INC-101")
    ok, p = mc.run(inc_as("bob", "get_incident", incident_id="INC-101"))
    check(not ok, "incident-lookup: bob denied INC-101")
    check(any(r["capability_id"] == CAP2 and r["version"] == "0.1.0" and r["user"] == "alice" for r in audit_records(ws)),
          "audit separates capabilities: alice / ahead.incident-lookup / 0.1.0")

    print("\n" + ("ACCEPTANCE: all checks passed" if not FAILS else f"ACCEPTANCE FAILED: {len(FAILS)} check(s)"))
    print(f"audit log: {ws.audit_log}\nregistry:  {ws.registry}\nfeed:      {ws.catalogue}/feed.json")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(run_demo(".gmo-demo"))
