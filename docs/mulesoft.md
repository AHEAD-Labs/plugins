# MuleSoft at Arm: what is known, and how it plugs into this MVP

Status: research note, 13 Nov 2026. **Nothing here is built.** We have no Anypoint access yet.

## Sources and how far to trust them
| Source | What it gave | Trust |
|---|---|---|
| 2 Sep "Session 2" discovery notes (Arm, Pradeep/Radek) | How Arm-i uses MuleSoft | Notes written by AHEAD, not a transcript |
| 12 Oct engineering deep dive notes (AHEAD internal) | SaaS and air-gap concern | Internal notes |
| 19 Oct MuleSoft Professional Services agenda (Kyle) | Self-hosted questions, still open | Agenda only, no answers |
| "Capability broker options" (Kyle, 1 Oct) | How Agent Fabric components work, what is unproven | AHEAD working doc, cites MuleSoft docs |
| Arm comments K-010, K-011, K-025, K-033, design guide C9 | Arm's own positions | Arm text |
| **6 Nov final architecture review transcript** | **Almost nothing on MuleSoft** (agenda item and one joke) | Read in full |

Several search results were AI-generated summaries; the above were checked against the documents.

## What Arm is doing with MuleSoft
1. **Arm-i is built on MuleSoft Agent Fabric.** It is an enterprise conversational front door for business processes (onboarding, ServiceNow, HR). Domain agents call governed APIs, not systems of record directly. Sign-in is Entra, with on-behalf-of (OBO) delegation down the call chain. Production rollout was targeted for mid-October.
2. **Arm corrected our wording** (Graeme, C-097/C-123/C-124): Arm-i is a *consumer* of services behind Agent Fabric, not its front door. Agent Fabric is an **intent router**, not the place all agents run. OASIS should own agent metadata and MuleSoft consumes the relevant part.
3. **Decisions D4/D5:** MuleSoft keeps its own native gateway and API policies. It is one of three platforms (MuleSoft, AWS, KPaaS). In the MVP design Arm expects: an Anypoint sandbox, one test API, one agent in Agent Fabric, Entra as identity provider.
4. **Open concern, deployment model.** Export-controlled environments allow no managed SaaS and no outbound calls (an API key that phones home is a blocker). Whether a self-hosted, air-gapped Agent Fabric exists is still being asked of MuleSoft Professional Services.
5. **Open design points from Arm:** two-way sync between OASIS and MuleSoft (who owns which fields, K-025); MuleSoft-to-Anypoint direct calls need a governed path (K-033); whether MuleSoft's own MCP/A2A connectors replace a custom adapter (K-011).

## How Agent Fabric works (per AHEAD's reading of MuleSoft docs, not yet proven at Arm)
- **Agent Registry** (Anypoint Exchange): inventory of agents and MCP servers. Scanners keep it current.
- **Omni Gateway** (formerly Flex Gateway): runtime enforcement in front of agents, APIs, MCP servers. Validates the Entra JWT, applies MCP access rules, can run an Entra OBO policy. The OBO policy is **not available in Local Mode**, so plan on Managed or Connected Mode.
- **Agent Broker:** orchestrates agents over A2A. **MCP Bridge** exposes Exchange APIs as MCP tools.
- **Not yet proven against Arm's tenant ("Spike 4"):** Codex connecting to an Omni Gateway MCP instance, a denied caller stopped before the target, the OBO policy producing a correctly scoped token in a multi-hop call.
- **Useful for us:** a PoC showed Codex can complete an Entra OAuth login to a JWT-protected remote MCP endpoint **when given a fully qualified scope** (for us: `api://<api-app-id>/project-status:read`).

## Where it fits in this repo
A MuleSoft deployment is a **platform adapter**, like `platforms/aws/`. A capability's manifest would say `platform: mulesoft`. The adapter would:
1. register the approved release as an asset in the Agent Registry (id, version, schema digest, owner);
2. publish the MCP endpoint through Omni Gateway with the Entra JWT policy, MCP access rules and, where required, the OBO policy;
3. run the same **live platform checks** as AWS: no token, garbage token, wrong audience, wrong scope all rejected; valid Entra token accepted;
4. map suspension to a gateway policy or registry deregistration (mechanism **unverified**);
5. emit gateway logs in the common audit event (user, capability, version).
Registry, signing, review gate and catalogue stay unchanged: they are platform-neutral.

## What is needed before building
- Anypoint sandbox access, and an Agent Fabric entitlement.
- Answer to the self-hosted / air-gapped question (decides whether this is even viable for export-controlled work).
- Confirmation of which gateway mode (Managed or Connected) Arm will run.
- Who owns agent metadata: OASIS, the approved-artifact registry, or the MuleSoft registry (R2).
