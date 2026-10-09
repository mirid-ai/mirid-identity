import base64
import hashlib
import json
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mirid_identity.crypto import b64url, sign_assertion
from .identity_routes import create_identity_router, evidence_digest
from .local_request_boundary import configure_local_boundary


IMAGE = "data:image/png;base64," + base64.b64encode(b"synthetic fixture bytes").decode()
MODEL_HASH = "a" * 64


def fake_compare(reference, probe):
    assert isinstance(reference, bytes) and isinstance(probe, bytes)
    return {"status": "compared", "cosine_similarity": 0.72,
            "quality_passed": True, "model_id": "test-model", "model_sha256": MODEL_HASH}


def client(tmp_path, host="127.0.0.1"):
    app = FastAPI()
    app.include_router(create_identity_router(tmp_path, comparator=fake_compare,
                                             status_provider=lambda: {"ready": True, "models": []}))
    return TestClient(app, client=(host, 45000))


def images(**extra):
    return dict(reference_image=IMAGE, probe_image=IMAGE, consent=True, **extra)


def test_comparison_is_local_research_only(tmp_path):
    local = client(tmp_path)
    response = local.post("/identity/compare", json=images())
    assert response.status_code == 200
    value = response.json()
    assert value["face"]["cosine_similarity"] == 0.72
    assert value["decision"]["status"] == "insufficient_evidence"
    assert value["decision"]["posterior_probability"] is None
    assert value["research_mode"] is True
    assert response.headers["cache-control"] == "no-store"
    assert "x-robots-tag" not in response.headers
    remote = client(tmp_path, host="192.168.1.2")
    assert remote.get("/identity/status").status_code == 403
    assert remote.post("/identity/compare", json=images()).status_code == 403


def test_consent_invalid_inputs_and_untrusted_probabilities(tmp_path):
    local = client(tmp_path)
    for update in ({"consent": False}, {"reference_image": "https://example.org/photo.jpg"},
                   {"probe_image": "data:image/png;base64,!!"}, {"posterior_probability": 1.0}):
        assert local.post("/identity/compare", json={**images(), **update}).status_code == 400
    duplicate = '{"consent":true,"consent":false}'
    assert local.post("/identity/compare", content=duplicate, headers={"Content-Type": "application/json"}).status_code == 400


def write_trust(tmp_path, key):
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    (tmp_path / "trust.json").write_text(json.dumps({"version": 1, "audience": "test-audience", "issuers": {
        "fixture-issuer": {"public_key": b64url(public), "max_lifetime_seconds": 300,
                           "factors": {"credential": {"independence_group": "enrolled-credential", "identity_bound": True}}}}}))


def token_for(challenge, key, **extra):
    now = int(time.time())
    claims = {"issuer": "fixture-issuer", "subject": challenge["subject"], "audience": challenge["audience"],
              "challenge": challenge["challenge"], "evidence_digest": challenge["evidence_digest"],
              "factor": "credential", "issued_at": now, "expires_at": now + 120}
    return sign_assertion(key, **{**claims, **extra})


def test_real_signed_session_bound_to_images_and_one_use(tmp_path):
    key = Ed25519PrivateKey.generate()
    write_trust(tmp_path, key)
    local = client(tmp_path)
    challenge = local.post("/identity/challenge", json=images(subject="fixture-subject")).json()
    assert challenge["evidence_digest"] == evidence_digest(b"synthetic fixture bytes", b"synthetic fixture bytes")
    assert "reference_image" not in challenge and "probe_image" not in challenge
    payload = {"session_id": challenge["session_id"], "assertions": [token_for(challenge, key)]}
    response = local.post("/identity/verify", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["evidence_verified"] == 1
    assert response.json()["decision"]["status"] == "insufficient_evidence"
    assert local.post("/identity/verify", json=payload).status_code == 409
    assert set(path.name for path in tmp_path.iterdir()) == {"trust.json"}


def test_bad_proof_burns_session_clear_removes_images(tmp_path):
    key = Ed25519PrivateKey.generate()
    write_trust(tmp_path, key)
    local = client(tmp_path)
    challenge = local.post("/identity/challenge", json=images(subject="fixture-subject")).json()
    bad = token_for(challenge, key, evidence_digest="b" * 64)
    response = local.post("/identity/verify", json={"session_id": challenge["session_id"], "assertions": [bad]})
    assert response.status_code == 400
    assert response.json()["decision"]["reasons"] == ["wrong_evidence_digest"]
    assert local.post("/identity/verify", json={"session_id": challenge["session_id"], "assertions": [token_for(challenge, key)]}).status_code == 409
    fresh = local.post("/identity/challenge", json=images(subject="fixture-subject")).json()
    assert local.request("DELETE", "/identity/session", json={"session_id": fresh["session_id"]}).status_code == 200
    assert local.post("/identity/verify", json={"session_id": fresh["session_id"], "assertions": [token_for(fresh, key)]}).status_code == 409


def test_session_capacity_is_bounded(tmp_path):
    local = client(tmp_path)
    sessions = [local.post("/identity/challenge", json=images(subject="fixture-subject")) for _ in range(4)]
    assert all(response.status_code == 200 for response in sessions)
    assert local.post("/identity/challenge", json=images(subject="fixture-subject")).status_code == 429
    local.request("DELETE", "/identity/session", json={"session_id": sessions[0].json()["session_id"]})
    assert local.post("/identity/challenge", json=images(subject="fixture-subject")).status_code == 200
