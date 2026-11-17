"""Stage 1: common checks (every capability). Stage 2: platform checks (per deployment platform)."""
import glob, json, os, re
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from .manifest import Manifest
from .registry import Registry
from .util import py


@dataclass
class Check:
    stage: str
    name: str
    passed: bool
    detail: str = ""


REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def common_pre(m: Manifest, reg: Registry, run_tests: bool) -> list[Check]:
    out = [Check("common", "manifest-valid", True, "schema + semver ok")]  # load() already validated
    out.append(Check("common", "version-unreleased", not reg.exists(m.capability_id, m.version),
                     f"{m.capability_id}@{m.version}"))
    out.append(Check("common", "audience-declared", bool(m.audience), ",".join(m.audience)))
    if run_tests:
        import subprocess, sys
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "tests/unit"], cwd=REPO,
                           capture_output=True, text=True)
        out.append(Check("common", "unit-tests", r.returncode == 0, r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[-200:]))
    return out


def common_post(m: Manifest, schema: dict, version_in_artifact: str) -> list[Check]:
    return [
        Check("common", "artifact-version-matches-manifest", schema["version"] == m.version,
              f"artifact={schema['version']} manifest={m.version}"),
        Check("common", "tools-match-manifest", sorted(schema["tools"]) == sorted(m.tools),
              f"artifact={schema['tools']}"),
    ]


def platform_checks(m: Manifest, unpacked: str) -> list[Check]:
    out: list[Check] = []
    for d in m.deployments:
        if d.transport != "streamable-http":
            continue
        host = urlparse(d.endpoint).hostname
        local = host in ("127.0.0.1", "localhost")
        out.append(Check("platform", f"{d.id}:tls-or-loopback", d.endpoint.startswith("https://") or local, d.endpoint))
        out.append(Check("platform", f"{d.id}:oauth-required", d.auth.type == "oauth2-bearer", d.auth.type))
        out.append(Check("platform", f"{d.id}:audience-bound-to-endpoint", d.auth.audience == d.endpoint,
                         f"aud={d.auth.audience}"))
        out.append(Check("platform", f"{d.id}:scopes-declared", bool(d.auth.scopes), ",".join(d.auth.scopes)))
    out.append(Check("platform", "restricted-not-externally-distributed",
                     not (m.classification == "restricted" and "openai-codex-plugin" in m.distribution),
                     f"{m.classification} -> {m.distribution}"))
    if not any(d.transport == "streamable-http" for d in m.deployments):
        out.append(Check("platform", "no-remote-deployment", True, "local-only capability: gateway checks not applicable"))
        return out
    # Behavioural: the *artifact* hosted behind our gateway must refuse unauthenticated callers.
    r = py(["-m", "platform_gateway.selfcheck"], pythonpath=unpacked,
           env={"GMO_AUDIT_LOG": os.devnull, "GMO_REMOTE_ENDPOINT": next(
               (d.endpoint for d in m.deployments if d.transport == "streamable-http"), "http://127.0.0.1:8802/mcp")})
    try:
        res = json.loads(r.stdout.strip().splitlines()[-1])
        out.append(Check("platform", "gateway-rejects-unauthorized", all(x["passed"] for x in res),
                         ",".join(f"{x['case']}={x['status']}" for x in res)))
    except Exception:
        out.append(Check("platform", "gateway-rejects-unauthorized", False, r.stderr[-200:]))
    return out


def common_agent(m: Manifest) -> list[Check]:
    return [Check("common", "tools-declared", bool(m.tools), ",".join(m.tools))]


_DIGEST = re.compile(r"^[\w.\-/:]+@sha256:[0-9a-f]{64}$")


def agent_checks(m: Manifest) -> list[Check]:
    """Platform checks for an agent that runs behind a platform gateway (no wheel to inspect)."""
    d = m.deployments[0]
    out = [
        Check("platform", "agent-image-pinned-by-digest", bool(_DIGEST.match(d.image or "")), d.image or ""),
        Check("platform", "gateway-image-pinned-by-digest", bool(_DIGEST.match(d.gateway_image or "")), d.gateway_image or ""),
        Check("platform", f"{d.id}:tls", (d.endpoint or "").startswith("https://"), d.endpoint or ""),
        Check("platform", f"{d.id}:entra-oauth-required", d.auth.type == "oauth2-bearer"
              and "login.microsoftonline.com" in (d.auth.issuer or ""), d.auth.issuer or d.auth.type),
        Check("platform", f"{d.id}:audience-is-entra-api", (d.auth.audience or "").startswith("api://"), d.auth.audience or ""),
        Check("platform", f"{d.id}:scopes-declared", bool(d.auth.scopes), ",".join(d.auth.scopes)),
        Check("platform", f"{d.id}:allowed-callers-declared", bool(d.auth.allowed_callers),
              f"{len(d.auth.allowed_callers)} calling app(s)"),
        Check("platform", f"{d.id}:agent-reachable-only-through-gateway", d.ingress == "gateway-only", str(d.ingress)),
        Check("platform", "restricted-not-externally-distributed",
              not (m.classification == "restricted" and "openai-codex-plugin" in m.distribution),
              f"{m.classification} -> {m.distribution}"),
    ]
    return out


def mcp_image_checks(m: Manifest) -> list[Check]:
    """An MCP shipped as an image and hosted by ToolHive. ToolHive treats a server with no OIDC config as open to
    anyone who can reach it, so token settings, a unique audience and the allowed roles are mandatory here."""
    d = m.deployments[0]
    return [
        Check("platform", "mcp-image-pinned-by-digest", bool(_DIGEST.match(d.image or "")), d.image or ""),
        Check("platform", f"{d.id}:tls", (d.endpoint or "").startswith("https://"), d.endpoint or ""),
        Check("platform", f"{d.id}:entra-oauth-required", d.auth.type == "oauth2-bearer"
              and "login.microsoftonline.com" in (d.auth.issuer or ""), d.auth.issuer or d.auth.type),
        Check("platform", f"{d.id}:audience-unique-to-endpoint", d.auth.audience == d.endpoint, f"aud={d.auth.audience}"),
        Check("platform", f"{d.id}:scopes-declared", bool(d.auth.scopes), ",".join(d.auth.scopes)),
        Check("platform", f"{d.id}:allowed-roles-declared", bool(d.allowed_roles), ",".join(d.allowed_roles)),
        Check("platform", "restricted-not-externally-distributed",
              not (m.classification == "restricted" and "openai-codex-plugin" in m.distribution), f"{m.classification} -> {m.distribution}"),
    ]


def plugin_files(base: str) -> dict:
    """The submitted plugin folder (Codex plugin layout). `.app.json` content is not confirmed: only that it is valid JSON."""
    root = os.path.join(base, "plugin")
    skills = sorted(glob.glob(os.path.join(root, "skills", "*", "SKILL.md")))
    return {"root": root, "skills": skills}


def _json_ok(path: str) -> bool:
    try:
        json.load(open(path)); return True
    except (OSError, ValueError):
        return False


def external_checks(m: Manifest, base: str, snapshot: list) -> list[Check]:
    """A capability whose server the submitting team runs: we cannot inspect the code, so we pin what we can see
    (the tool list, the plugin folder) and make the gateway position explicit."""
    d, pf = m.deployments[0], plugin_files(base)
    names = sorted(t.get("name", "") for t in snapshot)
    out = [
        Check("platform", f"{d.id}:tls", (d.endpoint or "").startswith("https://"), d.endpoint or ""),
        Check("platform", f"{d.id}:oauth-required", d.auth.type == "oauth2-bearer" and bool(d.auth.issuer), d.auth.issuer or d.auth.type),
        Check("platform", f"{d.id}:audience-declared", bool(d.auth.audience), d.auth.audience or ""),
        Check("platform", f"{d.id}:scopes-declared", bool(d.auth.scopes), ",".join(d.auth.scopes)),
        Check("platform", "tools-snapshot-matches-manifest", names == sorted(m.tools), ",".join(names)),
        Check("platform", "plugin-manifest-valid", _json_ok(os.path.join(pf["root"], ".codex-plugin", "plugin.json")), ".codex-plugin/plugin.json"),
        Check("platform", "plugin-app-json-valid", _json_ok(os.path.join(pf["root"], ".app.json")), ".app.json (content not validated: format unconfirmed)"),
        Check("platform", "plugin-has-skill", bool(pf["skills"]), f"{len(pf['skills'])} skill(s)"),
        Check("platform", "gateway-position-explicit",
              d.gateway == "platform" or (d.gateway == "none" and bool(d.risk_acceptance) and m.classification in ("public", "internal")),
              "behind a platform gateway" if d.gateway == "platform" else
              f"NO gateway: suspension and audit cannot be enforced; risk accepted: {d.risk_acceptance or 'missing'}"),
        Check("platform", "restricted-not-externally-distributed",
              not (m.classification == "restricted" and "openai-codex-plugin" in m.distribution), f"{m.classification} -> {m.distribution}"),
    ]
    return out


def as_dicts(cs: list[Check]) -> list[dict]:
    return [asdict(c) for c in cs]
