# Governed MCP Onboarding (MVP)

One custom MCP (`list_projects`, `get_project_status`, synthetic data) registered through a
governed pipeline, run **locally (stdio)** and **remotely (Streamable HTTP behind a gateway)**,
discovered through a catalogue feed, and packaged as a Codex plugin.

```
Git (manifest, skill, code) -> common checks -> evaluate -> platform checks -> signed release in registry
   -> platform deploy (remote) / local install -> catalogue feed + Codex plugin
```

## Run it
```bash
uv sync
uv run pytest tests/unit          # fast
uv run gmo --ws .gmo-demo demo    # full acceptance demo (ports 8801 backend, 8802 remote)
uv run pytest                     # unit + e2e
```

## Layout
| Path | Role |
|---|---|
| `capabilities/<name>/` | one folder per capability: `manifest.yaml`, `SKILL.md`, `eval_cases.json` (Git). Two examples: `project-status` (local + remote), `incident-lookup` (local only) |
| `src/project_status/`, `src/incident_lookup/` | **the artifacts**: one Python package per capability |
| `src/platform_gateway/` | platform-owned: OAuth bearer + audience + scope check, suspension, denial audit, demo IdP |
| `src/backend_service/` | synthetic backend API; owns per-user authorization |
| `src/govpipeline/` | release pipeline, registry, deployer, catalogue, demo |

## Acceptance (all asserted by the demo)
Two execution paths; one versioned release (0.1.0, 0.2.0); approval evidence in
`registry/<cap>/<ver>/{release.json,evaluation.json,checks.json}`; backend authorization (bob
cannot read PRJ-002); audit records user + capability + version; **catalogue removal leaves
remote still serving; suspension blocks it at the gateway**; rollback restores 0.1.0.

## Honest limits / open items
- **OASIS contract unconfirmed.** `catalogue/feed.json` is a provisional OASIS-compatible feed; write the real adapter in `catalogue.py` once the contract is confirmed.
- **OpenAI plugin publication unverified.** The plugin bundle (`.codex-plugin/plugin.json`, `.mcp.json`, skills) and `codex-config.toml` follow the Codex layout as best known; confirm the supported workspace-publication flow. The demo drives the stdio/HTTP paths with the MCP Python client as a stand-in for Codex — Codex itself was not run.
- **Auth is a demo IdP** (HS256 bearer, audience-bound). Real deployment needs Entra/Okta and OAuth discovery for Codex's login flow. Gateway is an in-process stand-in for the native platform gateway.
- **Suspension is enforced remotely only.** A local stdio package already on a laptop is not stopped by the gateway; local revocation = withdraw package + managed config (not built).
- Suspension returns 401 (verifier-level); a platform gateway should return 403 with a reason.
- Signing is HMAC with a dev key; use real signing (e.g. Sigstore/KMS) beyond the MVP.
- Deferred per scope: cross-platform task storage, A2A, multi-region, isolated cells. Phil-meeting transcript review remains outstanding.
