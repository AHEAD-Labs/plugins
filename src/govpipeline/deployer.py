"""Platform-specific deployment (here: a local process-based platform simulator).
Runs ONLY artifacts whose signed release record and wheel digest verify."""
import json, os, signal, socket, subprocess, sys, time
from urllib.parse import urlparse

from platform_gateway import idp
from . import build, mcpclient as mc
from .registry import Registry
from .workspace import Workspace


def _state_path(ws, name): return os.path.join(ws.state, f"{name}.json")


def _load(ws, name) -> dict:
    try:
        return json.load(open(_state_path(ws, name)))
    except FileNotFoundError:
        return {}


def _save(ws, name, s): json.dump(s, open(_state_path(ws, name), "w"), indent=2)


def materialize(ws: Workspace, cap: str, ver: str) -> tuple[dict, str]:
    reg = Registry(ws.registry)
    rec = reg.load(cap, ver)  # verifies signature + wheel digest, refuses unapproved
    dest = build.unpack(reg.wheel_path(rec), os.path.join(ws.runtime, cap, ver))
    return rec, dest


def _wait_port(port: int, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"port {port} not ready")


def _kill(pid: int):
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def _spawn(ws, name, args, env, port):
    log = open(os.path.join(ws.logs, f"{name}.log"), "ab")
    p = subprocess.Popen([sys.executable, *args], env={**os.environ, **ws.env(), **env},
                         stdout=log, stderr=log, start_new_session=True)
    _wait_port(port)
    return p.pid


# ---- backend (platform-owned, version-independent)
def start_backend(ws: Workspace, port=8801) -> None:
    st = _load(ws, "backend")
    if st.get("pid"): _kill(st["pid"])
    pid = _spawn(ws, "backend", ["-m", "backend_service.app"], {"GMO_BACKEND_PORT": str(port)}, port)
    _save(ws, "backend", {"pid": pid, "port": port})


# ---- remote deployment
def deploy_remote(ws: Workspace, cap: str, ver: str, *, reason: str = "deploy") -> dict:
    rec, dest = materialize(ws, cap, ver)
    d = next(x for x in rec["deployments"] if x["transport"] == "streamable-http")
    port = urlparse(d["endpoint"]).port
    st = _load(ws, f"remote-{cap}")
    if st.get("pid"): _kill(st["pid"]); time.sleep(0.5)
    env = {"PYTHONPATH": dest, "GMO_REMOTE_ENDPOINT": d["endpoint"], "CAPABILITY_VERSION": ver,
           "GMO_BACKEND_URL": f"http://127.0.0.1:{_load(ws, 'backend').get('port', 8801)}"}
    pid = _spawn(ws, "remote", ["-m", "platform_gateway.remote_main"], env, port)
    hist = st.get("history", [])
    hist.append({"version": ver, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "reason": reason})
    new = {"capability_id": cap, "active_version": ver, "endpoint": d["endpoint"], "audience": d["auth"]["audience"],
           "pid": pid, "history": hist, "artifact_sha256": rec["artifact"]["sha256"]}
    _save(ws, f"remote-{cap}", new)
    _smoke(new)
    return new


def _smoke(st):
    async def go():
        tok = idp.mint("alice", st["audience"])
        async with mc.http_session(st["endpoint"], tok) as s:
            ok, p = await mc.call(s, "list_projects")
            assert ok and p["projects"], "post-deploy smoke test failed"
    mc.run(go())


def rollback_remote(ws: Workspace, cap: str = "ahead.project-status") -> dict:
    st = _load(ws, f"remote-{cap}")
    versions = [h["version"] for h in st["history"]]
    # most recent version different from the active one
    prev = next((v for v in reversed(versions) if v != st["active_version"]), None)
    if not prev:
        raise RuntimeError("no previous release to roll back to")
    return deploy_remote(ws, st["capability_id"], prev, reason=f"rollback from {st['active_version']}")


def stop_all(ws: Workspace):
    for f in os.listdir(ws.state):
        if f.startswith("remote-") or f == "backend.json":
            st = _load(ws, f[:-5])
            if st.get("pid"): _kill(st["pid"])


# ---- local distribution (package materialised on the user's machine)
def install_local(ws: Workspace, cap: str, ver: str) -> dict:
    rec, dest = materialize(ws, cap, ver)
    entry = next(d for d in rec["deployments"] if d["transport"] == "stdio")["package"]["entrypoint"]
    st = {"capability_id": cap, "version": ver, "command": sys.executable,
          "args": ["-m", entry], "env": {"PYTHONPATH": dest, "CAPABILITY_VERSION": ver}}
    _save(ws, f"local-{cap}", st)
    return st


def state(ws: Workspace, name: str) -> dict:
    return _load(ws, name)
