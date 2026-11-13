# MuleSoft platform adapter (not built)

Placeholder for the adapter described in [docs/mulesoft.md](../../docs/mulesoft.md). It needs Anypoint
sandbox access first. Contract it must satisfy, same as `platforms/aws/`:

- `deploy(registry_dir, capability, version) -> endpoint`  (verifies the release signature first)
- live checks: no/garbage/wrong-audience/wrong-scope token rejected, valid Entra token accepted
- suspension and audit hooks mapped to the platform's own mechanisms
