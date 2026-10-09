from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mirid_identity.crypto import AssertionVerifier, EvidenceError, FactorTrust, NonceStore, TrustedIssuer, sign_assertion
from mirid_identity.policy import CalibrationProvenance, DecisionPolicy, FaceCalibration, FactorCalibration, ScoreBand, evaluate_identity, load_policy_config


NOW = 1_800_000_000
MODEL = "synthetic-test-model-never-use-for-real-decisions"
MODEL_SHA = "a" * 64
DIGEST = "b" * 64
CHALLENGE = "test-server-challenge-0123456789abcdef"
# Deliberately synthetic numerical fixtures, not empirical biometric calibration.
PROVENANCE = CalibrationProvenance("synthetic-only", "c" * 64, "synthetic-risk-only", "d" * 64, True)
FACE = FaceCalibration(MODEL, MODEL_SHA, (ScoreBand(-1, 0, 0.1), ScoreBand(0, 0.5, 10), ScoreBand(0.5, 1, 100)), PROVENANCE)


def proof(factor="hardware", group="recovery-a", identity_bound=True, issuer="issuer-a"):
    key = Ed25519PrivateKey.generate()
    verifier = AssertionVerifier({issuer: TrustedIssuer(key.public_key(), {factor: FactorTrust(group, identity_bound)})}, NonceStore(), "mirid-identity")
    signed = sign_assertion(key, issuer=issuer, subject="subject-a", audience="mirid-identity", challenge=CHALLENGE, evidence_digest=DIGEST, factor=factor, issued_at=NOW, expires_at=NOW + 60)
    return verifier.verify(signed, subject="subject-a", challenge=CHALLENGE, evidence_digest=DIGEST, now=NOW)


def policy(factors=(), **changes):
    values = dict(policy_id="synthetic-test-only", prior_probability=0.1, target_probability=0.99, face_calibration=FACE, factor_calibrations=tuple(factors), require_quality=True, require_certified_liveness=False, require_identity_bound_factor=False)
    values.update(changes)
    return DecisionPolicy(**values)


def evaluate(score=0.7, evidence=(), selected=None, **changes):
    args = dict(model_id=MODEL, model_sha256=MODEL_SHA, quality_passed=True, now=NOW)
    args.update(changes)
    return evaluate_identity(score, evidence, selected or policy(), **args)


def factor(name="hardware", group="recovery-a", lr=20, context=("face",), issuer="issuer-a"):
    return FactorCalibration(issuer, name, group, context, lr, PROVENANCE)


def test_research_default_does_not_invent_probability():
    result = evaluate(selected=DecisionPolicy())
    assert result.status == "insufficient_evidence"
    assert result.posterior_probability is None
    assert result.minimum_face_similarity is None
    assert "independent_face_calibration_missing" in result.reasons
    assert "certified_liveness_missing" in result.reasons
    assert result.assurance == "research_only_not_accredited"


def test_actual_signed_factor_changes_required_face_lr_using_bayes():
    base = evaluate(selected=policy())
    additional = evaluate(evidence=[proof()], selected=policy([factor()]))
    assert base.posterior_probability == pytest.approx((0.1 / 0.9 * 100) / (1 + 0.1 / 0.9 * 100))
    assert additional.posterior_probability == pytest.approx((0.1 / 0.9 * 100 * 20) / (1 + 0.1 / 0.9 * 100 * 20))
    assert additional.minimum_face_likelihood_ratio == pytest.approx(base.minimum_face_likelihood_ratio / 20)
    assert base.minimum_face_similarity is None
    assert additional.minimum_face_similarity == 0.5
    assert additional.status == "experimental_supported"
    assert "verified" not in additional.status
    assert additional.calibration_fingerprints == ("c" * 64, "d" * 64)


def test_same_recovery_group_not_multiplied_and_lower_lr_selected():
    evidence = [proof("hardware"), proof("recovery-email")]
    result = evaluate(evidence=evidence, selected=policy([factor(lr=1000), factor("recovery-email", lr=20)]))
    single = evaluate(evidence=[evidence[1]], selected=policy([factor("recovery-email", lr=20)]))
    assert result.posterior_probability == single.posterior_probability
    assert result.counted_factors == ("issuer-a/recovery-email",)
    assert any("shared_recovery_group_not_multiplied" in item for item in result.ignored_factors)


def test_cross_group_factors_need_exact_conditional_context():
    evidence = [proof(), proof("document", "recovery-b")]
    unsupported = evaluate(evidence=evidence, selected=policy([factor(), factor("document", "recovery-b", 30)]))
    supported = evaluate(evidence=evidence, selected=policy([factor(), factor("document", "recovery-b", 30, ("face", "recovery-a"))]))
    assert unsupported.counted_factors == ("issuer-a/hardware",)
    assert supported.counted_factors == ("issuer-a/hardware", "issuer-a/document")
    assert supported.minimum_face_likelihood_ratio == pytest.approx(unsupported.minimum_face_likelihood_ratio / 30)


def test_adaptive_threshold_requires_uniform_conditional_lr_scope():
    with pytest.raises(EvidenceError, match="uniform_conditional_lower_bound"):
        replace(factor(), likelihood_ratio_semantics="specific_to_observed_face_score")
    result = evaluate(evidence=[proof()], selected=policy([factor()]))
    assert result.probability_interpretation == "conditional_model_lower_bound_if_uniform_calibration_holds"
    # The fixture's same lower bound applies in each score bin. Crossing the
    # adaptive threshold changes the outcome without changing factor semantics.
    below = evaluate(0.49, evidence=[proof()], selected=policy([factor()]))
    at = evaluate(result.minimum_face_similarity, evidence=[proof()], selected=policy([factor()]))
    assert below.status == "review_required"
    assert at.status == "experimental_supported"


def test_account_possession_is_not_identity_enrolment():
    result = evaluate(evidence=[proof(identity_bound=False)], selected=policy([factor(lr=100000)], require_identity_bound_factor=True))
    assert result.status == "insufficient_evidence"
    assert result.counted_factors == ()
    assert "identity_bound_enrolment_evidence_missing" in result.reasons
    assert "account_possession" in result.ignored_factors[0]


def test_liveness_requires_named_verified_issuer_assertion():
    selected = policy(require_certified_liveness=True, certified_liveness_factors=("issuer-a/certified-pad",))
    assert evaluate(selected=selected).status == "insufficient_evidence"
    with pytest.raises(EvidenceError, match="unverified_liveness"):
        evaluate(selected=selected, liveness=True)
    pad = proof("certified-pad", "pad-provider", False)
    result = evaluate(selected=selected, liveness=pad)
    assert "certified_liveness_missing" not in result.reasons
    assert result.status == "review_required"


def test_quality_and_model_binding_are_gates():
    assert evaluate(quality_passed=False).status == "insufficient_evidence"
    result = evaluate(model_sha256="0" * 64)
    assert result.status == "insufficient_evidence"
    assert not result.calibrated
    assert "face_calibration_model_mismatch" in result.reasons


def test_unvalidated_calibration_is_never_used():
    unvalidated = replace(FACE, provenance=replace(PROVENANCE, independently_validated=False))
    result = evaluate(selected=policy(face_calibration=unvalidated))
    assert result.posterior_probability is None


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -float("inf"), 1.1, True, "0.99"])
def test_nonfinite_or_coerced_inputs_rejected(score):
    with pytest.raises(EvidenceError, match="invalid_face_similarity"):
        evaluate(score)


@pytest.mark.parametrize("prior", [0, 1, -1, float("nan"), True, "0.1"])
def test_invalid_prior_rejected(prior):
    with pytest.raises(EvidenceError):
        policy(prior_probability=prior)


def test_mixed_sessions_or_stale_proofs_rejected():
    valid = proof()
    with pytest.raises(EvidenceError, match="mixed_evidence_bindings"):
        evaluate(evidence=[valid, replace(valid, subject="other", assertion_id="e" * 64)])
    with pytest.raises(EvidenceError, match="stale_verified_evidence"):
        evaluate(evidence=[valid], now=NOW + 60)
    with pytest.raises(EvidenceError, match="unverified_evidence"):
        evaluate(evidence=[{"likelihood_ratio": 100000}])


def test_adverse_factor_increases_required_face_evidence():
    result = evaluate(evidence=[proof()], selected=policy([factor(lr=0.01)]))
    assert result.minimum_face_likelihood_ratio == pytest.approx(evaluate().minimum_face_likelihood_ratio * 100)
    assert result.status == "review_required"


def test_log_space_extreme_valid_likelihoods_are_json_safe():
    huge_face = replace(FACE, bands=(ScoreBand(-1, 1, 1e300),))
    result = evaluate(evidence=[proof()], selected=policy([factor(lr=1e300)], face_calibration=huge_face))
    assert math.isfinite(result.log_posterior_odds)
    assert result.posterior_probability == 1.0
    json.dumps(result.to_dict(), allow_nan=False)


def test_default_admin_policy_loads():
    path = Path(__file__).parents[1] / "examples" / "policy.json"
    loaded = load_policy_config(path)
    assert loaded == DecisionPolicy()


def test_config_fingerprints_pinned_and_tamper_fails(tmp_path):
    report = tmp_path / "calibration.json"
    risk = tmp_path / "risk.json"
    report.write_text('{"purpose":"synthetic-test-only"}')
    risk.write_text('{"purpose":"synthetic-risk-only"}')
    provenance = {"document": report.name, "sha256": hashlib.sha256(report.read_bytes()).hexdigest(), "target_risk_document": risk.name, "target_risk_sha256": hashlib.sha256(risk.read_bytes()).hexdigest(), "independently_validated": True}
    data = json.loads((Path(__file__).parents[1] / "examples" / "policy.json").read_text())
    data.update(prior_probability=0.1, target_probability=0.99, face_calibration={"model_id": MODEL, "model_sha256": MODEL_SHA, "bands": [{"lower": -1, "upper": 1, "likelihood_ratio": 1}], "provenance": provenance})
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(data))
    assert load_policy_config(path).face_calibration.provenance.sha256 == provenance["sha256"]
    report.write_text("tampered")
    with pytest.raises(EvidenceError, match="fingerprint_mismatch"):
        load_policy_config(path)
