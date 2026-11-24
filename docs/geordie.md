# Geordie: how it fits, and the policies to define

Status: DESIGN. Nothing here is connected to a Geordie tenant yet. Geordie's own policy syntax is not documented in anything
we have, so each policy below is written as a rule in plain terms (what to match, mode, owner) to be entered in Geordie's
policy editor, or drafted with its "Ask Geordie" agent. Geordie facts come from the Arm session notes: monitor / nudge /
block modes, policies per platform on an endpoint (for example all of Codex), allow and block lists built from the inventory,
an API that vets an MCP or tool (for example on a pull request), alerts by webhook and API, OpenTelemetry in.

## Policies as code
- `policies/geordie/policies.yaml` holds P1 to P10 below in a neutral schema; `policies/geordie/exceptions.yaml` holds exceptions.
- `gmo geordie --check` runs on every PR: owners named, modes valid, nothing in block mode without `approved_by` and `monitor_since`,
  no expired exception.
- On merge, CI publishes `geordie/policies.json` and `geordie/approved-mcp.json` (approved and blocked MCPs from the signed
  registry) on the `catalogue` branch. This is what Geordie is meant to pick up.
- NOT DONE: the step that loads these into Geordie. Its import method is unknown (the scanner logs "No policy to deploy").

## Division of work
| Layer | Owns | Where |
| --- | --- | --- |
| Registry (signed) | which MCPs are approved, their version, status, classification | this repo |
| Codex requirements.toml | what Codex may start (remote allowlist, approval and sandbox floors) | this repo, `gmo codex-config` |
| Platform gateways (AWS, Azure, ToolHive) | who may call, audit, suspension | platforms/* |
| Geordie | what actually runs on laptops, what data moves, what the registry cannot see | Geordie tenant |

Geordie is the check on everything outside the path the registry controls: local servers, shadow servers, config drift, data
moving to or from MCP servers.

## Integration points (build order)
1. **Approved list feed.** Export the registry as `approved-mcp.json` on the catalogue branch: endpoint (remote) or package
   digest (local), version, classification, status, owner. Geordie imports it as its allow list. Suspended entries go in a block list.
2. **Telemetry in.** Codex OTLP (`managed_config.toml`) and the platform audit records go to the Geordie OTLP endpoint, each
   carrying `user`, `capability_id`, `version` and `correlation_id`. The correlation id is what joins an endpoint event to the
   platform call, which Geordie does not do by itself (it keeps only the starting identity).
3. **Vetting in CI.** Call Geordie's vetting API on any PR that adds an `external` or `mcp-image` capability. Record the result in
   the signed release as evidence.
4. **Alerts out.** Geordie webhook to a small receiver that opens a ticket and, after a person approves, runs `gmo suspend`.
   Automatic suspension only after the policy has run in monitor mode long enough to trust it.

## Policies
Start every policy in **monitor**, review for two weeks, then **nudge**, then **block** where noted.

| # | Policy | Match | Mode path | Why |
| --- | --- | --- | --- | --- |
| P1 | Unauthorized MCP | An MCP server configured in Codex (or another monitored agent) that is not in the approved list: remote by URL, local by command plus package digest | monitor, nudge, block | The core control; `requirements.toml` should already reject it at startup, this catches devices where it is not enforced |
| P2 | Suspended capability still in use | A configured server whose approved-list status is suspended | block | Closes the gap between a suspension and a laptop's cached config |
| P3 | Unknown remote MCP host | A remote MCP URL outside the approved hosts and the corporate domains | nudge, block | Shadow servers on personal cloud accounts |
| P4 | Config tampering | Codex MCP entries, hooks or telemetry settings changed against the managed config; the Geordie hook removed | alert | Geordie does not flag lost coverage on its own |
| P5 | Secrets or personal data in a tool call | Credentials, keys, tokens, connection strings or personal-data patterns in MCP tool arguments or results | nudge, block | Data leak path 1: the agent sends a secret out |
| P6 | Data to a lower-trust server | Content from a restricted or confidential source sent as an argument to an MCP whose registry classification is lower, or to any server with `gateway: none` | block | Data leak path 2: classification mismatch |
| P7 | Exfiltration chain | A tool result containing instructions (prompt injection), followed by an outbound call to a different MCP server | block | Data leak path 3 |
| P8 | Oversized or unusual transfer | Result or argument size, or call rate, far above the tool's baseline | alert | Bulk copy |
| P9 | Local server exposed | A local MCP server listening on a non-loopback address | alert | Shadow server reachable from the network |
| P10 | Tool list changed | An approved server whose tools differ from the signed `schema_digest` (the "rug pull") | alert, block | Needs our reconcile check as the source of truth |

Exceptions (engineering and HPC private servers, K-002) are entries in an exception list with an owner and an expiry date,
not a switch-off of P1 and P3.

## Needed from Geordie or the tenant admin
- Whether the endpoint scanner supports Codex's config file on macOS (it logged "No config files found for any supported apps").
- How an allow list is imported (file, API or URL) and its format.
- The OTLP endpoint and how to authenticate to it.
- The vetting API and its auth.
- The webhook format, and whether Beam can block (not only alert) for Codex in this tenant.
- Whether P5 to P8 are built-in detections or must be written as custom rules.
