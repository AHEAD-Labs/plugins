import os


class Workspace:
    """All mutable platform state lives under one directory."""
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.registry = os.path.join(self.root, "registry")
        self.runtime = os.path.join(self.root, "runtime")
        self.state = os.path.join(self.root, "deployments")
        self.catalogue = os.path.join(self.root, "catalogue")
        self.logs = os.path.join(self.root, "logs")
        self.audit_log = os.path.join(self.root, "audit", "audit.jsonl")
        self.revocations = os.path.join(self.root, "revocations.json")
        self.work = os.path.join(self.root, "work")
        for d in (self.registry, self.runtime, self.state, self.catalogue, self.logs, self.work,
                  os.path.dirname(self.audit_log)):
            os.makedirs(d, exist_ok=True)

    def env(self) -> dict:
        return {"GMO_AUDIT_LOG": self.audit_log, "GMO_REVOCATIONS": self.revocations}
