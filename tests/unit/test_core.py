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
    import re
    bad = re.sub(r"(?m)^version: .*$", "version: v1", open(MANIFEST).read())
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


def test_registry_signature_and_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("GMO_SIGNING_KEY", "unit-test-only-signing-key-0123456789")  # never depend on a CI secret
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


AGENT = os.path.join(os.path.dirname(__file__), "..", "..", "capabilities", "tag-compliance", "manifest.yaml")


def _agent_manifest(tmp_path, **edit):
    import yaml
    y = yaml.safe_load(open(AGENT))
    d = y["deployments"][0]
    for k, v in edit.items():
        (d["auth"] if k in ("allowed_callers",) else d)[k] = v
    p = tmp_path / "manifest.yaml"; p.write_text(yaml.safe_dump(y))
    return load(str(p))


def test_agent_manifest_is_a_container_image_not_a_package(tmp_path):
    import yaml
    m = load(AGENT)
    assert m.kind == "agent" and m.python_package is None and m.deployments[0].image
    y = yaml.safe_load(open(AGENT)); y["python_package"] = "x"
    p = tmp_path / "m.yaml"; p.write_text(yaml.safe_dump(y))
    with pytest.raises(Exception, match="container image"): load(str(p))


def test_agent_checks_gate_the_release(tmp_path):
    from govpipeline import checks
    failed = lambda m: {c.name.split(":")[-1] for c in checks.agent_checks(m) if not c.passed}
    good = _agent_manifest(tmp_path, ingress="gateway-only")
    assert failed(good) == set()
    assert failed(_agent_manifest(tmp_path, ingress="public")) == {"agent-reachable-only-through-gateway"}
    assert failed(_agent_manifest(tmp_path, ingress="gateway-only", image="reg.io/a:latest")) == {"agent-image-pinned-by-digest"}
    assert failed(_agent_manifest(tmp_path, ingress="gateway-only", allowed_callers=[])) == {"allowed-callers-declared"}


def test_agent_release_is_signed_and_pinned_by_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("GMO_SIGNING_KEY", "unit-test-only-signing-key-0123456789")
    reg = regmod.Registry(str(tmp_path))
    img = "r.io/a@sha256:" + "a" * 64
    rec = {"capability_id": "ahead.a", "version": "1.0.0", "status": "approved", "kind": "agent",
           "artifact": {"type": "container-image", "image": img, "sha256": "a" * 64}}
    reg.publish(rec, None, {})
    assert reg.load("ahead.a", "1.0.0")["artifact"]["image"] == img  # no file to hash: the signature pins the digest
    p = tmp_path / "ahead.a" / "1.0.0" / "release.json"
    r = json.load(open(p)); r["artifact"]["image"] = "r.io/a@sha256:" + "b" * 64; json.dump(r, open(p, "w"))
    with pytest.raises(ValueError, match="signature"): reg.load("ahead.a", "1.0.0")
