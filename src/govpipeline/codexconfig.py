"""Codex managed configuration, generated from the signed registry (R1: "what the agent may attempt").

requirements.toml  enforced and not overridable: approval floor, sandbox floor, and an allowlist of remote MCP
                   servers. Only approved, not-suspended capabilities with a remote deployment get an entry,
                   so a user cannot quietly add an unapproved remote server on a managed device.
managed_config.toml  starting values: Codex telemetry switched on (it is off by default).

FORMAT STATUS: written from the Codex enterprise guide as summarised in the Arm learning guide (secondary
source). Field names must be checked against OpenAI's current managed-configuration docs before rollout.
Local (stdio) servers are NOT pinned: their identity is a command on a laptop, which an allowlist cannot
tell apart from an unapproved one with the same command. That is a gap, listed in the output.
"""
import os, time

from platform_gateway import revocations
from . import deployer
from .registry import Registry
from .workspace import Workspace

APPROVAL = ["untrusted", "on-request"]          # "never" (no prompts) is not allowed
SANDBOX = ["read-only", "workspace-write"]      # "danger-full-access" is not allowed


def build(ws: Workspace, otel_endpoint: str | None = None) -> dict[str, str]:
    reg = Registry(ws.registry)
    servers, skipped_local, suspended = [], [], []
    for cap in reg.capabilities():
        vers = reg.versions(cap)
        if not vers:
            continue
        rec = reg.load(cap, vers[-1])
        name = cap.split(".")[-1]
        if revocations.check(cap, rec["version"], None):
            suspended.append(cap); continue
        aws = deployer.state(ws, f"aws-{cap}")
        for d in rec["deployments"]:
            if d["transport"] == "streamable-http":
                servers.append((f"{name}-remote", aws.get("endpoint", d["endpoint"]), cap, rec["version"]))
            elif d["transport"] == "stdio":
                skipped_local.append(cap)
    head = [f"# Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from the signed registry. Do not edit by hand.",
            "# FORMAT UNCONFIRMED: check field names against OpenAI's current managed-configuration docs.", ""]
    req = head + [f"allowed_approval_policies = {APPROVAL!r}".replace("'", '"'),
                  f"allowed_sandbox_modes = {SANDBOX!r}".replace("'", '"'), ""]
    for n, url, cap, ver in servers:
        req += [f"# {cap}@{ver}", f"[mcp_servers.{n}]", f'identity = {{ url = "{url}" }}', ""]
    if suspended:
        req += ["# not allowed (suspended): " + ", ".join(suspended), ""]
    if skipped_local:
        req += ["# NOT PINNED (local stdio servers cannot be identified by an allowlist): " + ", ".join(sorted(set(skipped_local))), ""]
    cfg = head + ["# Codex telemetry is off by default; this switches it on for managed devices."]
    cfg += (["[otel]", f'exporter = {{ otlp-http = {{ endpoint = "{otel_endpoint}" }} }}', "log_user_prompt = false"]
            if otel_endpoint else ["# [otel] not written: no telemetry destination given (--otel-endpoint). This is an open gap."])
    return {"requirements.toml": "\n".join(req) + "\n", "managed_config.toml": "\n".join(cfg) + "\n"}


def write(ws: Workspace, otel_endpoint: str | None = None) -> str:
    out = os.path.join(ws.catalogue, "codex-managed")
    os.makedirs(out, exist_ok=True)
    for name, body in build(ws, otel_endpoint).items():
        open(os.path.join(out, name), "w").write(body)
    return out
