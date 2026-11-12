import json, os

import pytest

from govpipeline import registry as regmod
from govpipeline.manifest import load
from platform_gateway import idp, revocations
from project_status import data

MANIFEST = os.path.join(os.path.dirname(__file__), "..", "..", "capabilities", "project-status", "manifest.yaml")


def test_acl():
    assert len(data.list_for("alice")) == 4
    assert [p["project_id"] for p in data.list_for("bob")] == ["PRJ-001"]
    assert data.list_for("mallory") == []
    with pytest.raises(data.AccessDenied): data.status_for("bob", "PRJ-002")
    with pytest.raises(data.NotFound): data.status_for("alice", "PRJ-999")


def test_manifest_valid_and_strict(tmp_path):
    m = load(MANIFEST)
    assert m.capability_id == "ahead.project-status" and {d.transport for d in m.deployments} == {"stdio", "streamable-http"}
    bad = open(MANIFEST).read().replace("version: 0.1.0", "version: v1")
    p = tmp_path / "m.yaml"; p.write_text(bad)
    with pytest.raises(Exception): load(str(p))


def test_token_audience_binding():
    t = idp.mint("alice", "aud-a")
    assert idp.verify(t, "aud-a")["sub"] == "alice"
    with pytest.raises(Exception): idp.verify(t, "aud-b")


def test_suspension_scoping(tmp_path, monkeypatch):
    monkeypatch.setenv("GMO_REVOCATIONS", str(tmp_path / "r.json"))
    assert revocations.check("c", "1.0.0", "u") is None
    revocations.suspend("c", version="2.0.0", reason="x", by="t")
    assert revocations.check("c", "2.0.0", "u") == "x" and revocations.check("c", "1.0.0", "u") is None
    revocations.suspend("c", user="mallory", reason="y", by="t")
    assert revocations.check("c", "1.0.0", "mallory") == "y" and revocations.check("c", "1.0.0", "u") is None
    revocations.lift("c", version="2.0.0")
    assert revocations.check("c", "2.0.0", "u") is None


def test_registry_signature_and_digest(tmp_path):
    reg = regmod.Registry(str(tmp_path))
    wheel = tmp_path / "x.whl"; wheel.write_bytes(b"abc")
    from govpipeline.util import sha256_file
    rec = {"capability_id": "c", "version": "1.0.0", "status": "approved",
           "artifact": {"filename": "x.whl", "sha256": sha256_file(str(wheel))}}
    reg.publish(rec, str(wheel), {})
    assert reg.load("c", "1.0.0")["version"] == "1.0.0"
    with pytest.raises(FileExistsError): reg.publish(rec, str(wheel), {})
    (tmp_path / "c" / "1.0.0" / "x.whl").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="digest"): reg.load("c", "1.0.0")
    p = tmp_path / "c" / "1.0.0" / "release.json"
    r = json.load(open(p)); r["status"] = "approved"; r["version"] = "9.9.9"; json.dump(r, open(p, "w"))
    with pytest.raises(ValueError, match="signature"): reg.load("c", "1.0.0")
