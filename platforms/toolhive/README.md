# ToolHive (KPaaS) platform adapter: planned

`render.py` turns a signed `mcp-image` release into ToolHive resources. Nothing is applied from this repo yet.

Secrets the resources refer to (create them yourself, never commit them), in the namespace of the server:

    kubectl -n toolhive-system create secret generic gmo-<name>-auth \
      --from-literal=hmac="$(openssl rand -base64 48)" \
      --from-file=signing-key=<private key pem> \
      --from-literal=entra-client-secret=<secret of the Entra app gmo-toolhive>

Entra: one app registration (`gmo-toolhive`) with redirect URI `https://<host>/oauth/callback` (to confirm) and the
app roles listed in `allowed_roles`. `entra.json` needs `issuer`, `tenant_id`, `toolhive_client_id`.
