# Azure adapter: gateway in front of the tag-compliance agent

    python platforms/entra/agent_setup.py                                  # Entra: agent API app + OBO secret (SSM)
    python platforms/azure/deploy.py --cfg .gmo-demo/entra-agent.json      # storage, image, Container App
    uv run --with azure-identity --with azure-storage-blob python platforms/azure/check.py --cfg .gmo-demo/entra-agent.json
    python platforms/azure/deploy.py --destroy                             # removes the gateway, storage, image; never the agent

What the gateway enforces before the agent sees anything: Entra token for this API, `tag-compliance:read`,
caller app on the allowed list (the MCP that does OBO, and Codex), not suspended (Azure Blob list, 5 s cache,
fails closed), then one audit line per decision. The agent's API key stays inside the gateway.

Limits: the agent's own public URL still works (close it once nothing else needs it); the OBO secret is a
client secret in SSM (a federated credential is better); the gateway runs one small always-on replica.
