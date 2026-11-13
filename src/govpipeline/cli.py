import argparse, json, os, sys

from platform_gateway import idp, revocations
from . import catalogue, deployer
from .release import ReleaseRejected, release
from .workspace import Workspace

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CAPS = os.path.join(REPO, "capabilities")
MANIFEST = os.path.join(CAPS, "project-status", "manifest.yaml")
MANIFEST2 = os.path.join(CAPS, "incident-lookup", "manifest.yaml")


def main(argv=None):
    p = argparse.ArgumentParser("gmo", description="Governed MCP onboarding")
    p.add_argument("--ws", default=os.environ.get("GMO_WS", ".gmo"), help="workspace dir")
    sp = p.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("release", help="checks -> evaluate -> approve into registry")
    r.add_argument("--manifest", help="one manifest (default: every capabilities/*/manifest.yaml)")
    r.add_argument("--skip-tests", action="store_true")
    r.add_argument("--dry-run", action="store_true", help="run all checks, do not write to the registry (PR mode)")
    r.add_argument("--only-new", action="store_true", help="skip capability versions already in the registry (merge mode)")
    d = sp.add_parser("deploy", help="deploy a released version to the remote platform")
    d.add_argument("version"); d.add_argument("--cap", default="ahead.project-status")
    i = sp.add_parser("install-local", help="verify + materialise the local package")
    i.add_argument("version"); i.add_argument("--cap", default="ahead.project-status")
    rb = sp.add_parser("rollback", help="redeploy the previous approved release"); rb.add_argument("--cap", default="ahead.project-status")
    sp.add_parser("backend", help="start the synthetic backend API")
    sp.add_parser("verify", help="check signature + artifact digest of every release in the registry")
    sp.add_parser("stop", help="stop platform processes")
    sp.add_parser("catalogue", help="regenerate discovery feed + Codex plugin bundle")
    s = sp.add_parser("suspend"); s.add_argument("--cap", default="ahead.project-status")
    s.add_argument("--version"); s.add_argument("--user"); s.add_argument("--reason", required=True)
    l = sp.add_parser("lift"); l.add_argument("--cap", default="ahead.project-status")
    l.add_argument("--version"); l.add_argument("--user")
    t = sp.add_parser("token", help="mint a demo bearer token for the remote endpoint")
    t.add_argument("--user", required=True)
    t.add_argument("--audience", default="http://127.0.0.1:8802/mcp")
    sp.add_parser("demo", help="run the end-to-end demonstration")
    a = p.parse_args(argv)

    ws = Workspace(a.ws)
    os.environ.update(ws.env())
    if a.cmd == "release":
        import glob
        from .manifest import load as load_manifest
        from .registry import Registry
        reg = Registry(ws.registry)
        for m in ([a.manifest] if a.manifest else sorted(glob.glob(os.path.join(CAPS, "*", "manifest.yaml")))):
            mf = load_manifest(m)
            if a.only_new and reg.exists(mf.capability_id, mf.version):
                print(f"skip {mf.capability_id}@{mf.version} (already released)"); continue
            try:
                rec = release(m, ws, run_tests=not a.skip_tests, dry_run=a.dry_run)
            except ReleaseRejected as e:
                print(e, file=sys.stderr); return 1
            print(("checks passed (dry run)" if a.dry_run else "approved")+f" {rec['capability_id']}@{rec['version']} sha256={rec['artifact']['sha256'][:16]}…")
    elif a.cmd == "verify":
        from .registry import Registry
        reg, bad, n = Registry(ws.registry), 0, 0
        for cap in reg.capabilities():
            for ver in reg.versions(cap):
                n += 1
                try:
                    reg.load(cap, ver); print(f"ok    {cap}@{ver}")
                except Exception as e:
                    bad += 1; print(f"FAIL  {cap}@{ver}: {e}", file=sys.stderr)
        print(f"{n - bad}/{n} releases verified")
        return 1 if bad or n == 0 else 0
    elif a.cmd == "deploy":
        print(json.dumps(deployer.deploy_remote(ws, a.cap, a.version), indent=2))
    elif a.cmd == "install-local":
        print(json.dumps(deployer.install_local(ws, a.cap, a.version), indent=2))
    elif a.cmd == "rollback":
        print(json.dumps(deployer.rollback_remote(ws, a.cap), indent=2))
    elif a.cmd == "backend":
        deployer.start_backend(ws)
    elif a.cmd == "stop":
        deployer.stop_all(ws)
    elif a.cmd == "catalogue":
        feed = catalogue.publish(ws)
        print(f"{len(feed['entries'])} entries -> {ws.catalogue}/feed.json")
    elif a.cmd == "suspend":
        print(revocations.suspend(a.cap, version=a.version, user=a.user, reason=a.reason,
                                  by=os.environ.get("USER", "operator")))
    elif a.cmd == "lift":
        print(f"lifted {revocations.lift(a.cap, version=a.version, user=a.user)}")
    elif a.cmd == "token":
        print(idp.mint(a.user, a.audience))
    elif a.cmd == "demo":
        from .demo import run_demo
        return run_demo(a.ws)
    return 0


if __name__ == "__main__":
    sys.exit(main())
