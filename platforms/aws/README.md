# AWS platform adapter (account sandbox, us-east-1)

Runs the approved `project-status` remote MCP as **Lambda + API Gateway (HTTP API)**.
Everything is named `gmo-*` and tagged `project=governed-mcp-onboarding`.

    uv run --extra aws python platforms/aws/bootstrap.py [--email you@x] # once: budget, bucket, roles
    uv run --extra aws python platforms/aws/deploy.py --registry <dir> --version 0.1.0
    uv run --extra aws python platforms/aws/bootstrap.py --destroy       # remove what bootstrap made

| Piece | What it is |
|---|---|
| `package.py` | verifies the registry release, builds the arm64 Lambda zip |
| `deploy.py` | creates/updates the function + API, sets throttling, runs the LIVE selfcheck |
| `bootstrap.py` | budget, S3 state (revocations), GitHub OIDC role, Lambda role |

Known limits of this first pass:
- Token check still uses the demo HS256 IdP inside the function. The native API Gateway JWT
  authorizer needs RS256/JWKS, so it arrives with Entra.
- Backend is the in-process synthetic backend (no separate backend service yet).
- Suspension: the gateway reads `s3://gmo-state-<acct>/revocations.json` with a 5 s cache, so a
  suspension takes effect within ~5 s (`GMO_REVOCATION_TTL`).
- The Lambda stays in the open internet path; private connectivity is not addressed.

## Entra (real identity)
`platforms/entra/setup.py` creates the `gmo-project-status` API app (scope `project-status:read`)
and the `gmo-codex-client` public client; `--destroy` removes both. Pass its JSON to deploy:

    python platforms/entra/setup.py > .gmo-demo/entra.json
    uv run --extra aws python platforms/aws/deploy.py --registry <dir> --version 0.1.0 --entra .gmo-demo/entra.json

The API Gateway JWT authorizer checks issuer, audience and scope before the function runs; the
function validates the token again and applies suspension per user. The demo HS256 IdP is
rejected once Entra is on.
