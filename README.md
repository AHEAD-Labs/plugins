# Governed MCP Onboarding

A working prototype of how an enterprise can put **MCP servers and agents under governance** and
distribute them to **Codex**, without a central gateway. It uses synthetic data only.

## The goal
Arm's engineers use Codex with many MCP servers and agents on different platforms (AWS, Azure,
MuleSoft, KPaaS). The direction (decisions D1-D8): each platform keeps its **own native gateway**,
and a **common process** decides what is approved. This repo tests that idea end to end:
*propose, check, approve, deploy, discover, run, and stop it again*, with the real user's identity on every call.

## How it works
```
capability folder (manifest, skill, tests) in Git
   -> pull request: checks, nothing published
   -> merge: signed, immutable release in the registry
   -> deploy to the platform (AWS today) -> live checks
   -> catalogue + marketplaces (what Codex users see)

At run time:  Codex -> platform gateway (Entra token, scope, allowed caller, not suspended) -> MCP / agent
              every decision writes an audit record: user, capability, version
```

## What exists and works (tested live)
- **Pipeline** on GitHub Actions: PR checks, real signing key, verified registry, deploy to AWS with no stored keys.
- **Remote MCP on AWS** (Lambda + API Gateway) with Entra sign-in, suspension in seconds, and audit.
- **Local MCP in Codex**, from a local marketplace.
- **Azure agent behind a gateway**, reached through a real Entra on-behalf-of exchange (OBO) with allowed callers, suspension and audit.

## What is not done yet
SPIFFE workload identity and a separate backend, the AWS MCP calling the agent itself, pipeline support for
agents, local MCP sign-in, group-based access, Databricks, MuleSoft (needs Anypoint access), one shared audit
format with Geordie, and harvesting and agent-behaviour evaluation. Full picture:
[docs/architecture/](docs/architecture/index.html). MuleSoft findings: [docs/mulesoft.md](docs/mulesoft.md).

## Where things are
| Path | What |
|---|---|
| `capabilities/<name>/` | one folder per capability: `manifest.yaml`, `SKILL.md`, `eval_cases.json` |
| `src/<capability>/` | the MCP code for each capability |
| `src/govpipeline/` | release pipeline, registry, deploy, catalogue |
| `src/platform_gateway/` | gateway logic: Entra token check, suspension, OBO |
| `platforms/aws`, `platforms/azure`, `platforms/entra` | platform adapters and identity setup |
| `.github/workflows/release.yml` | PR checks, release, deploy |

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
