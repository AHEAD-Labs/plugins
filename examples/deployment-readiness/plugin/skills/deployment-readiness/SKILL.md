---
name: deployment-readiness
description: Prepare and validate deploying an application into AWS. Use when an engineer asks whether an app is ready to deploy or asks to deploy it.
---

# Deployment readiness

Create one correlation id at the start and pass it to every call.

1. Call the requirements agent first. It reads the project documentation as the signed-in user.
2. When it returns, call the feasibility agent and the governance agent in parallel, using the requirements.
3. Each result has `status` of `ok`, `denied`, `missing` or `failed`, plus `issues`. Do not guess a missing result.
4. Write one report: technical feasibility, data governance, owners, RACI, outstanding issues. Quote only what the agents returned.
5. If any agent is not `ok`, say which one and why, and stop. Do not request a deployment.
6. If all are `ok`, call `plan_deploy`, then `request_approval` with the plan. Approval is decided by policy, not by you.
7. Call `apply_deploy` only with the approval returned. Retrying is safe: the same approved plan is applied once.
8. Never use credentials, endpoints or tools outside this plugin.
