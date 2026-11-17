# External plugins (the team runs its own server)

Two ways a capability reaches the catalogue:

| Kind | Who runs the server | What the PR contains | What the pipeline can prove |
| --- | --- | --- | --- |
| `mcp` | we build and deploy it | server code, manifest | code, wheel digest, behaviour |
| `agent` | we deploy a pinned image behind a gateway | manifest, image digest | image digest, ingress, behaviour after deploy |
| `external` | the submitting team | the plugin folder, manifest, `tools.json` | tool list, plugin folder, auth settings; NOT the server code |

## Submitting
Copy `examples/external-plugin/` to `capabilities/<name>/` and fill it in:
- `manifest.yaml` with `kind: external`, the live endpoint, Entra auth, owner, classification, and `gateway:`.
- `tools.json`: the server's `tools/list` result (names and input schemas).
- `plugin/`: `.codex-plugin/plugin.json`, `.app.json`, `skills/<name>/SKILL.md`, `assets/`.
- `eval_cases.json`.

## What is checked and signed
https, OAuth with an issuer, audience and scopes, tool list equals the manifest, plugin folder has the required files, and the
gateway position is explicit. The signed record pins the tool-list digest and the digest of the whole plugin folder; the catalogue
publishes that approved folder byte for byte, and loading the record fails if the folder was changed.

## What is not covered
- The server's code and behaviour. The eval is a contract check only; a live eval needs a token and is not run in CI.
- Suspension and audit hold only with `gateway: platform`. With `gateway: none` the manifest needs a written `risk_acceptance`
  and the data must be public or internal; the only lever then is removing the plugin from the marketplace and the allowlist.
- Drift: a live `tools/list` that differs from `tools.json` is not detected yet (needs a token for the endpoint).
- `.app.json` is only checked to be valid JSON. Its format is unconfirmed.
