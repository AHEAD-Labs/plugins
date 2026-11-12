"""Discovery + publication metadata. One feed entry and one plugin folder PER capability.

OASIS: the integration contract is NOT yet confirmed. `feed.json` is a provisional,
OASIS-compatible metadata feed (release status + install details); replace `to_oasis()` with
the real adapter once the contract is confirmed.
Codex: the plugin bundle follows the documented Codex plugin layout as best known; the
supported publication flow into an OpenAI workspace catalogue is a validation item.
The skill is read from the approved release in the registry, never from the working tree.
"""
import json, os, shutil, time

from platform_gateway import revocations
from . import deployer
from .registry import Registry
from .workspace import Workspace

CONTRACT = "provisional-oasis-compatible/v0 (UNCONFIRMED)"


def _status(cap, ver) -> str:
    return "suspended" if revocations.check(cap, ver, None) else "approved"


def build_feed(ws: Workspace) -> dict:
    reg = Registry(ws.registry)
    entries = []
    for cap in reg.capabilities():
        vers = reg.versions(cap)
        if not vers: continue
        remote, local = deployer.state(ws, f"remote-{cap}"), deployer.state(ws, f"local-{cap}")
        rec = reg.load(cap, remote.get("active_version") or local.get("version") or vers[-1])
        install = {}
        for d in rec["deployments"]:
            if d["transport"] == "stdio":
                install["local"] = {"transport": "stdio", "command": local.get("command", "python"),
                                    "args": local.get("args", ["-m", d["package"]["entrypoint"]]),
                                    "env": local.get("env", {}), "artifact": rec["artifact"]}
            else:
                install["remote"] = {"transport": "streamable-http", "endpoint": d["endpoint"], "auth": d["auth"]}
        entries.append({
            "capability_id": cap, "name": rec["name"], "description": rec["description"],
            "owner": rec["owner"], "classification": rec["classification"], "audience": rec["audience"],
            "version": rec["version"], "status": _status(cap, rec["version"]),
            "released_versions": [{"version": v, "status": _status(cap, v)} for v in vers],
            "schema_digest": rec["schema_digest"], "artifact_sha256": rec["artifact"]["sha256"],
            "evidence": {"evaluation_sha256": rec["evaluation"]["sha256"],
                         "approved_by": rec["approval"]["approved_by"],
                         "pipeline_run": rec["approval"]["pipeline_run"],
                         "approved_at": rec["approval"]["approved_at"]},
            "install": install, "distribution": rec["distribution"],
            "note": "Catalogue status is informational. Revocation is enforced at the gateway.",
        })
    return {"contract": CONTRACT, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "entries": entries}


def build_codex_plugin(ws: Workspace, entry: dict, base: str, only: str | None = None) -> str | None:
    """Write one plugin folder under `base`. only="remote" keeps just the remote server (OpenAI
    workspace marketplace: OpenAI cannot start a local stdio process on a laptop)."""
    reg = Registry(ws.registry)
    name = entry["capability_id"].split(".")[-1]
    install = {k: v for k, v in entry["install"].items() if only in (None, k)}
    if not install:
        return None
    entry = {**entry, "install": install}
    root = os.path.join(base, "plugins", name)
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(os.path.join(root, ".codex-plugin"))
    os.makedirs(os.path.join(root, "skills", name))
    shutil.copy(os.path.join(reg.dir(entry["capability_id"], entry["version"]), "SKILL.md"),
                os.path.join(root, "skills", name, "SKILL.md"))
    json.dump({"name": name, "version": entry["version"], "description": entry["description"],
               "skills": "./skills/", "mcpServers": "./.mcp.json"},
              open(os.path.join(root, ".codex-plugin", "plugin.json"), "w"), indent=2)
    servers = {}
    if "local" in entry["install"]:
        i = entry["install"]["local"]
        servers[f"{name}-local"] = {"command": i["command"], "args": i["args"], "env": i["env"]}
    if "remote" in entry["install"]:
        servers[f"{name}-remote"] = {"url": entry["install"]["remote"]["endpoint"],
                                     "bearer_token_env_var": name.upper().replace("-", "_") + "_TOKEN"}
    json.dump({"mcpServers": servers}, open(os.path.join(root, ".mcp.json"), "w"), indent=2)
    # Plain Codex config.toml equivalent (stable fallback while plugin publication is validated)
    toml = []
    for sname, s in servers.items():
        toml.append(f"[mcp_servers.{sname}]")
        if "command" in s:
            toml.append(f'command = "{s["command"]}"')
            toml.append("args = " + json.dumps(s["args"]))
            toml.append(f"env = {{ {', '.join(f'{k} = {json.dumps(v)}' for k, v in s['env'].items())} }}")
        else:
            toml += [f'url = "{s["url"]}"', f'bearer_token_env_var = "{s["bearer_token_env_var"]}"']
        toml.append("")
    open(os.path.join(root, "codex-config.toml"), "w").write("\n".join(toml))
    return root


def write_marketplace(base: str, name: str, display: str, plugin_names: list[str]) -> str:
    """Codex marketplace index (same shape as the marketplace.json files Codex ships with)."""
    path = os.path.join(base, ".agents", "plugins", "marketplace.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump({"name": name, "interface": {"displayName": display},
               "plugins": [{"name": n, "source": {"source": "local", "path": f"./plugins/{n}"},
                            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                            "category": "Engineering"} for n in plugin_names]},
              open(path, "w"), indent=2)
    return path


def publish(ws: Workspace) -> dict:
    """Two marketplaces, both generated from the registry:
    - catalogue/            LOCAL marketplace: Codex on a laptop reads it (local + remote servers)
    - catalogue/openai-workspace/   what an admin imports into the OpenAI workspace from GitHub
                                    (remote servers only)"""
    feed = build_feed(ws)
    os.makedirs(ws.catalogue, exist_ok=True)
    openai_base = os.path.join(ws.catalogue, "openai-workspace")
    for d in ("plugins", ".agents", "openai-workspace"):
        shutil.rmtree(os.path.join(ws.catalogue, d), ignore_errors=True)
    json.dump(feed, open(os.path.join(ws.catalogue, "feed.json"), "w"), indent=2)
    local, openai = [], []
    for e in feed["entries"]:
        if "openai-codex-plugin" not in e["distribution"]:
            continue
        build_codex_plugin(ws, e, ws.catalogue)
        local.append(e["capability_id"].split(".")[-1])
        if build_codex_plugin(ws, e, openai_base, only="remote"):
            openai.append(e["capability_id"].split(".")[-1])
    write_marketplace(ws.catalogue, "ahead-local", "AHEAD (local)", local)
    if openai:
        write_marketplace(openai_base, "ahead-openai-workspace", "AHEAD (OpenAI workspace)", openai)
    return feed
