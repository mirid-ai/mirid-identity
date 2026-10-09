"""Identity adapter review: browser boundary and adversarial signed bindings."""

import logging
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from .identity_routes import create_identity_router
from .local_request_boundary import configure_local_boundary
from .privacy_logging import PrivateAccessLogFilter
from .test_identity_routes import client, fake_compare, images, token_for, write_trust


def boundary_client(tmp_path):
    app = FastAPI()
    app.include_router(create_identity_router(tmp_path, comparator=fake_compare,
                                             status_provider=lambda: {"ready": True, "models": []}))
    configure_local_boundary(app)
    return TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 45000))


@pytest.mark.parametrize("headers,expected", [
    ({"Origin": "https://attacker.example"}, 403),
    ({"Host": "attacker.example:8000"}, 400),
    ({"Origin": "null"}, 403),
    ({"Sec-Fetch-Site": "cross-site"}, 403),
    ({"Origin": "http://127.0.0.1:5173"}, 200),
    ({"Origin": "tauri://localhost"}, 200),
])
def test_production_boundary_guards_identity_route(tmp_path, headers, expected):
    local = boundary_client(tmp_path)
    response = local.post("/identity/compare", json=images(), headers=headers)
    assert response.status_code == expected
    assert "x-robots-tag" not in response.headers
    if expected == 200:
        assert response.json()["decision"]["status"] == "insufficient_evidence"


@pytest.mark.parametrize("override,error", [
    ({"subject": "another-subject"}, "wrong_subject"),
    ({"audience": "another-audience"}, "wrong_audience"),
    ({"challenge": "another-challenge-0123456789abcdef"}, "wrong_challenge"),
    ({"issuer": "self-selected-issuer"}, "unknown_issuer"),
])
def test_wrong_binding_is_rejected_and_burns_http_session(tmp_path, override, error):
    key = Ed25519PrivateKey.generate()
    write_trust(tmp_path, key)
    local = client(tmp_path)
    challenge = local.post("/identity/challenge", json=images(subject="fixture-subject")).json()
    altered_session = {**challenge, "challenge": override.get("challenge", challenge["challenge"])}
    token_overrides = {name: value for name, value in override.items() if name != "challenge"}
    result = local.post("/identity/verify", json={"session_id": challenge["session_id"], "assertions": [token_for(altered_session, key, **token_overrides)]})
    assert result.status_code == 400
    assert result.json()["decision"]["reasons"] == [error]
    assert result.json()["evidence_verified"] == 0
    replay = local.post("/identity/verify", json={"session_id": challenge["session_id"], "assertions": [token_for(challenge, key)]})
    assert replay.status_code == 409
    assert set(p.name for p in tmp_path.iterdir()) == {"trust.json"}


def test_expired_signed_assertion_burns_http_session(tmp_path):
    key = Ed25519PrivateKey.generate()
    write_trust(tmp_path, key)
    local = client(tmp_path)
    challenge = local.post("/identity/challenge", json=images(subject="fixture-subject")).json()
    now = int(time.time())
    expired = token_for(challenge, key, issued_at=now - 120, expires_at=now - 1)
    result = local.post("/identity/verify", json={"session_id": challenge["session_id"], "assertions": [expired]})
    assert result.status_code == 400
    assert result.json()["decision"]["reasons"] == ["expired_assertion"]
    replay = local.post("/identity/verify", json={"session_id": challenge["session_id"], "assertions": [token_for(challenge, key)]})
    assert replay.status_code == 409


def test_repeated_assertion_in_batch_is_not_double_counted(tmp_path):
    key = Ed25519PrivateKey.generate()
    write_trust(tmp_path, key)
    local = client(tmp_path)
    challenge = local.post("/identity/challenge", json=images(subject="fixture-subject")).json()
    signed = token_for(challenge, key)
    result = local.post("/identity/verify", json={"session_id": challenge["session_id"], "assertions": [signed, signed]})
    assert result.status_code == 400
    assert result.json()["decision"]["reasons"] == ["replayed_assertion"]
    assert result.json()["evidence_verified"] == 0


@pytest.mark.parametrize("target", [
    "/identity/challenge?subject=PRIVATE_SUBJECT&reference_image=PRIVATE_IMAGE",
    "/identity/verify?assertion=PRIVATE_SIGNED_ASSERTION",
    "/api/identity/session/PRIVATE_SESSION?source=PRIVATE_CONTENT",
    "/%69dentity/status?subject=PRIVATE_SUBJECT",
])
def test_identity_access_log_redacts_query_and_path_identifiers(target):
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 1,
                               '%s - "%s %s HTTP/%s" %d',
                               ("127.0.0.1:45000", "POST", target, "1.1", 400), None)
    assert PrivateAccessLogFilter().filter(record)
    rendered = record.getMessage()
    assert "PRIVATE_" not in rendered
    assert "/identity/[private]" in rendered
    assert "POST" in rendered and "400" in rendered
