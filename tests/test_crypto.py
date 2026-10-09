import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mirid_identity.crypto import (
    AssertionVerifier, DOMAIN, EvidenceError, FactorTrust, NonceStore,
    SessionStore, TrustedIssuer, b64url, load_trust_config, sign_assertion,
)


NOW = 1_800_000_000
DIGEST = hashlib.sha256(b"immutable reference/probe transaction").hexdigest()
CHALLENGE = "server-random-challenge-0123456789abcdef"


@pytest.fixture
def setup():
    key = Ed25519PrivateKey.generate()
    issuer = TrustedIssuer(key.public_key(), {
        "hardware": FactorTrust("recovery-provider-a", True),
        "account": FactorTrust("recovery-provider-a", False),
    })
    nonces = NonceStore()
    verifier = AssertionVerifier({"issuer-a": issuer}, nonces, "mirid-identity")
    yield key, verifier
    nonces.close()


def token(key, **changes):
    args = dict(issuer="issuer-a", subject="subject-a", audience="mirid-identity", challenge=CHALLENGE, evidence_digest=DIGEST, factor="hardware", issued_at=NOW, expires_at=NOW + 60)
    args.update(changes)
    return sign_assertion(key, **args)


def verify(verifier, value, **changes):
    args = dict(subject="subject-a", challenge=CHALLENGE, evidence_digest=DIGEST, now=NOW)
    args.update(changes)
    return verifier.verify(value, **args)


def test_actual_signature_and_server_factor_meaning(setup):
    key, verifier = setup
    bound = verify(verifier, token(key))
    possession = verify(verifier, token(key, factor="account"))
    assert bound.identity_bound is True
    assert possession.identity_bound is False
    assert bound.independence_group == possession.independence_group == "recovery-provider-a"
    assert bound.evidence_digest == DIGEST


def test_self_signed_key_is_not_trusted(setup):
    _, verifier = setup
    forged_key = Ed25519PrivateKey.generate()
    with pytest.raises(EvidenceError, match="invalid_signature"):
        verify(verifier, token(forged_key))
    with pytest.raises(EvidenceError, match="unknown_issuer"):
        verify(verifier, token(forged_key, issuer="attacker-key"))


@pytest.mark.parametrize("change,error", [
    ({"subject": "subject-b"}, "wrong_subject"),
    ({"audience": "different-app"}, "wrong_audience"),
    ({"challenge": "another-server-challenge-0123456789"}, "wrong_challenge"),
    ({"evidence_digest": "b" * 64}, "wrong_evidence_digest"),
    ({"factor": "admin-identity"}, "untrusted_factor"),
    ({"issued_at": NOW + 1}, "future_assertion"),
    ({"issued_at": NOW - 300, "expires_at": NOW}, "expired_assertion"),
    ({"expires_at": NOW + 301}, "assertion_lifetime_exceeded"),
    ({"issued_at": True}, "invalid_iat"),
    ({"nonce": "short"}, "invalid_nonce"),
])
def test_wrong_binding_expiry_and_claims_rejected(setup, change, error):
    key, verifier = setup
    with pytest.raises(EvidenceError, match=error):
        verify(verifier, token(key, **change))


def test_tampered_payload_rejected(setup):
    key, verifier = setup
    original = token(key)
    payload64, signature64 = original.split(".")
    payload = base64.urlsafe_b64decode(payload64 + "=" * (-len(payload64) % 4))
    tampered = payload.replace(b"subject-a", b"subject-b")
    with pytest.raises(EvidenceError, match="invalid_signature"):
        verify(verifier, b64url(tampered) + "." + signature64, subject="subject-b")


@pytest.mark.parametrize("payload_change,error", [
    (lambda p: p[:-1] + b',"likelihood_ratio":100000}', "invalid_claims"),
    (lambda p: p[:-1] + b',"identity_bound":true}', "invalid_claims"),
    (lambda p: p[:-1] + b',"sub":"subject-a"}', "duplicate_json_key"),
    (lambda p: p.replace(b'"v":1', b'"v":NaN'), "nonfinite_json"),
])
def test_even_signed_claims_cannot_add_probability_or_assurance(setup, payload_change, error):
    key, verifier = setup
    encoded, _ = token(key).split(".")
    original = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    payload = payload_change(original)
    with pytest.raises(EvidenceError, match=error):
        verify(verifier, b64url(payload) + "." + b64url(key.sign(DOMAIN + payload)))


def test_replayed_nonce_atomic_across_threads(setup):
    key, verifier = setup
    proof = token(key)
    def attempt(_):
        try:
            verify(verifier, proof)
            return "accepted"
        except EvidenceError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(16)))
    assert results.count("accepted") == 1
    assert results.count("replayed_assertion") == 15


def test_invalid_signature_does_not_burn_nonce(setup):
    key, verifier = setup
    nonce = "issuer-random-nonce-0123456789"
    with pytest.raises(EvidenceError, match="invalid_signature"):
        verify(verifier, token(Ed25519PrivateKey.generate(), nonce=nonce))
    assert verify(verifier, token(key, nonce=nonce)).identity_bound


def test_sessions_burn_on_failed_request_and_expiry(setup):
    key, verifier = setup
    sessions = SessionStore()
    session = sessions.create("subject-a", DIGEST, audience="mirid-identity", now=NOW)
    consumed = sessions.consume(session.challenge, now=NOW)
    with pytest.raises(EvidenceError, match="wrong_subject"):
        verifier.verify(token(key, challenge=consumed.challenge, subject="wrong"), subject=consumed.subject, challenge=consumed.challenge, evidence_digest=consumed.evidence_digest, now=NOW)
    with pytest.raises(EvidenceError, match="replayed_session"):
        sessions.consume(session.challenge, now=NOW)
    expired = sessions.create("subject-a", DIGEST, audience="mirid-identity", ttl_seconds=1, now=NOW)
    with pytest.raises(EvidenceError, match="expired_session"):
        sessions.consume(expired.challenge, now=NOW + 1)
    with pytest.raises(EvidenceError, match="replayed_session"):
        sessions.consume(expired.challenge, now=NOW + 1)
    sessions.close()


def test_session_single_consumer_across_threads():
    sessions = SessionStore()
    session = sessions.create("subject-a", DIGEST, audience="mirid-identity", now=NOW)
    def attempt(_):
        try:
            sessions.consume(session.challenge, now=NOW)
            return True
        except EvidenceError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(16))) == 1
    sessions.close()


def test_owner_controlled_trust_config(tmp_path):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    data = {"version": 1, "audience": "mirid-identity", "issuers": {"issuer-a": {"public_key": b64url(public), "max_lifetime_seconds": 300, "factors": {"account": {"independence_group": "same-recovery", "identity_bound": False}}}}}
    path = tmp_path / "trust.json"
    path.write_text(json.dumps(data))
    config = load_trust_config(path)
    assert config.issuers["issuer-a"].factors["account"].identity_bound is False
    path.chmod(0o666)
    with pytest.raises(EvidenceError, match="config_writable_by_other_users"):
        load_trust_config(path)


def test_persistent_nonce_store_survives_reopen(tmp_path, setup):
    key, original = setup
    path = tmp_path / "nonces.sqlite"
    proof = token(key)
    store = NonceStore(path)
    verifier = AssertionVerifier(original.issuers, store, original.audience)
    verify(verifier, proof)
    store.close()
    store = NonceStore(path)
    verifier = AssertionVerifier(original.issuers, store, original.audience)
    with pytest.raises(EvidenceError, match="replayed_assertion"):
        verify(verifier, proof)
    assert path.stat().st_mode & 0o077 == 0
    store.close()


def test_factor_names_cannot_alias_issuer_factor_pairs():
    with pytest.raises(EvidenceError, match="invalid_factor"):
        TrustedIssuer(Ed25519PrivateKey.generate().public_key(), {"other/pad": FactorTrust("group")})


def test_oversized_json_integer_is_a_rejected_proof_not_unhandled_error(setup):
    key, verifier = setup
    # Python 3.11+ imposes an integer-string digit limit; this must surface as
    # a normal evidence rejection even though parsing precedes key lookup.
    payload = b'{"v":' + b"9" * 4400 + b"}"
    signed = b64url(payload) + "." + b64url(key.sign(DOMAIN + payload))
    with pytest.raises(EvidenceError):
        verify(verifier, signed)
