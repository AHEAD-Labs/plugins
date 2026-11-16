# Arm components: what is built here, and what still needs a person

Source: the "Components to add or define" table in the Arm learning guide (updated 13 Nov 2026). Status words
are the guide's: Add, Define, Prove, Keep. "Built" means it exists in this repo and is tested.

| Component | Guide status | Here | Where |
|---|---|---|---|
| Control contract per platform | Add | **Built.** One `contract.yaml` per platform: token validation, authorization, audit event, suspension (with a time limit), rate limit, cost limit, telemetry. Each needs an owner; a gap must say what is missing. Checked on every PR. | `platforms/*/contract.yaml`, `gmo contract` |
| Codex managed configuration | Add | **Built, format unconfirmed.** `requirements.toml` (approval and sandbox floors, allowlist of approved remote servers) and `managed_config.toml` (telemetry on), generated from the signed registry. Suspended or unapproved servers are never listed. | `gmo codex-config` |
| Native gateways (MuleSoft, AWS, KPaaS) | Keep, document | **AWS and Azure built; MuleSoft waiting for access; KPaaS not started.** | `platforms/*`, `docs/mulesoft.md` |
| Approved-artifact registry | Define | **Built.** Signed, immutable records with capability, owner, classification, endpoint, version and evidence. | `src/govpipeline/registry.py` |
| OASIS store, discovery, self-service | Keep, redefine | **Needs a person.** The retain / migrate / consolidate / retire matrix and any Solo Registry role are decisions for the OASIS owner. The feed here is a provisional guess at the contract. | `catalogue.py` |
| OpenAI plugin catalogue | Add | **Partly built.** Marketplaces are generated from the registry. The sync rule is now enforced by `gmo reconcile`. Audience and install policy per plugin are still the same default for every plugin. | `catalogue.py`, `reconcile.py` |
| Common publication stage | Add | **Partly built.** The exact approved version is what the catalogue and allowlist are built from, and reconcile fails on drift. Who may publish to OpenAI, with what permission, and how fast a plugin can be withdrawn are unconfirmed (D8). | `reconcile.py` |
| Shared evaluation baseline + platform checks | Add | **Partly built.** Common checks and platform checks run on every release; agents get contract checks. The Prism (scan) and Sage (evaluation) feeds are not connected. | `checks.py`, `evaluate.py` |
| Plugin package per capability | Add | **Built for the plugin bundle; eval specs extended.** Eval cases can now carry the guide's spec fields (prompt, expected tool path, required facts, safety, platform) and `runs: k`, which is graded as pass^k (all k runs must pass). Grading the tool path and judging answers needs a model and is not built. | `evaluate.py`, `capabilities/*/eval_cases.json` |
| Identity: workload identity, token exchange, OBO | Prove | **OBO proved; SPIFFE not started.** See the table below. | `obo.py`, `agent_client.py` |
| Audit store and telemetry | Define | **Event built; store not.** Every audit record carries user, capability, version and a correlation id that follows one action from the MCP to the agent. Raw arguments and results are never logged. There is still no separate authoritative store and no forwarding to the Arm telemetry destination (listed as gaps in the contracts). | `audit.py`, `correlation.py` |
| Geordie | Define its role | **Needs a person.** Treated as a signal source, not the approver; Codex support unconfirmed. | none |
| Suspension sequence | Define | **Built except running tasks.** See below. | `revocations.py` |
| Classification and data-flow rules | Define | **Partly built.** A restricted capability cannot be distributed externally. Data classes, DLP placement and ECCN confirmation belong to the data owners. | `checks.py` |
| LiteLLM model routing | Confirm scope | **Needs a person.** | none |
| Reusable assets (GitLab library, Nova, Aura) | Keep, reuse | **Needs a person.** | none |
| v1.0 scope list | Decide | **Needs a person.** | none |

## Audit event

Written by every platform for every decision (allow and deny):

`ts`, `event_id`, `correlation_id`, `source` (gateway, mcp, backend), `user`, `capability_id`, `version`, `transport`,
`tool`, `decision`, `reason`. The Azure gateway adds `caller_app` and `upstream_status`.

Never logged by default: tool arguments and tool results. The correlation id comes from the caller's
`x-correlation-id` header when it is well formed (8 to 64 letters, digits, `.`, `_`, `-`), otherwise it is made
on arrival, echoed on the response, and sent on to the agent, so one user action is one trail.

## Suspension sequence

| Step | How it works today | Gap |
|---|---|---|
| Signal | An operator or Geordie raises it | Geordie is not connected |
| Authorised decision | `gmo suspend` by an operator | No approval step or named decision-maker yet |
| Native block | The platform's own list (S3 on AWS, Blob on Azure) is read on every request, 5 s cache, fails closed | MuleSoft not built |
| Running tasks | Calls are short and stateless, so there is nothing long-running to cancel | Long jobs would need cancellation (a conditional feature in the guide) |
| Confirm | A live call returns 401 or 403 with the reason (`platforms/azure/check.py`, AWS deploy checks) | The confirmation is a check, not an alert |
| Catalogue withdrawal | `gmo catalogue` shows `suspended`; `gmo codex-config` drops the server from the allowlist | Withdrawal comes after the block, as the guide requires |

## Identity per backend

| Hop | Mechanism | State |
|---|---|---|
| Codex to the AWS MCP | Entra token, checked at API Gateway and again in the function | Live |
| AWS MCP to the Azure agent | Entra on-behalf-of: the user's token is swapped, never forwarded | Built; live test after the deploy |
| Codex to the Azure agent gateway | Entra token, scope, allowed-callers list | Live |
| Gateway to the agent | The agent's own API key, from a secret; the agent is internal to its environment | Live |
| MCP to its backend | Demo token between services | Replace with SPIFFE (next) |
| Local MCP | OS user | Replace with Entra sign-in (planned) |

## Not in this repo, and why

Items the guide marks "decide before v1.0" (task store, idempotency, cancellation, A2A translation, Second Brain and
so on) are not built, because the guide says to build them only when a confirmed use case needs one.
