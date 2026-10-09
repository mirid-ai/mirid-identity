"""Conservative research decisions from calibrated, conditionally scoped evidence.

Only startup policy files can supply priors and likelihood ratios. A cosine score
is not a probability. This module never emits an accredited or verified status.
The hypothesis being modelled is that the claimant is the enrolled identity.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
import sys
import time
from typing import Any, Sequence

from .crypto import EvidenceError, VerifiedEvidence, read_admin_json


LivenessEvidence = VerifiedEvidence


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EvidenceError(f"invalid_{name}")
    return float(value)


def _probability(value: Any, name: str) -> float:
    value = _number(value, name)
    if not 0 < value < 1:
        raise EvidenceError(f"invalid_{name}")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise EvidenceError(f"invalid_{name}")
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise EvidenceError(f"invalid_{name}")
    return value


@dataclass(frozen=True)
class CalibrationProvenance:
    document: str
    sha256: str
    target_risk_document: str
    target_risk_sha256: str
    independently_validated: bool

    def __post_init__(self) -> None:
        _text(self.document, "calibration_document")
        _text(self.target_risk_document, "target_risk_document")
        _sha(self.sha256, "calibration_sha256")
        _sha(self.target_risk_sha256, "target_risk_sha256")
        if type(self.independently_validated) is not bool:
            raise EvidenceError("invalid_validation_flag")


@dataclass(frozen=True)
class ScoreBand:
    lower: float
    upper: float
    likelihood_ratio: float

    def __post_init__(self) -> None:
        low, high, lr = _number(self.lower, "band_lower"), _number(self.upper, "band_upper"), _number(self.likelihood_ratio, "face_likelihood_ratio")
        if not -1 <= low < high <= 1 or lr <= 0:
            raise EvidenceError("invalid_score_band")


@dataclass(frozen=True)
class FaceCalibration:
    model_id: str
    model_sha256: str
    bands: tuple[ScoreBand, ...]
    provenance: CalibrationProvenance

    def __post_init__(self) -> None:
        _text(self.model_id, "model_id")
        _sha(self.model_sha256, "model_sha256")
        object.__setattr__(self, "bands", tuple(self.bands))
        if not self.bands or not isinstance(self.provenance, CalibrationProvenance):
            raise EvidenceError("invalid_face_calibration")
        previous: ScoreBand | None = None
        for band in self.bands:
            if not isinstance(band, ScoreBand):
                raise EvidenceError("invalid_score_band")
            if previous and (band.lower != previous.upper or band.likelihood_ratio < previous.likelihood_ratio):
                raise EvidenceError("noncontiguous_or_nonmonotone_calibration")
            previous = band
        if self.bands[0].lower != -1 or self.bands[-1].upper != 1:
            raise EvidenceError("incomplete_score_calibration")

    def likelihood_ratio(self, score: float) -> float:
        for band in self.bands:
            if band.lower <= score < band.upper or score == 1 and band.upper == 1:
                return band.likelihood_ratio
        raise EvidenceError("uncalibrated_score")


@dataclass(frozen=True)
class FactorCalibration:
    issuer: str
    factor: str
    independence_group: str
    conditional_on: tuple[str, ...]
    likelihood_ratio: float
    provenance: CalibrationProvenance
    likelihood_ratio_semantics: str = "uniform_conditional_lower_bound"

    def __post_init__(self) -> None:
        for name in ("issuer", "factor", "independence_group"):
            _text(getattr(self, name), name)
        if "/" in self.factor:
            raise EvidenceError("invalid_factor")
        object.__setattr__(self, "conditional_on", tuple(self.conditional_on))
        if self.independence_group == "face" or len(set(self.conditional_on)) != len(self.conditional_on):
            raise EvidenceError("invalid_conditional_context")
        if not self.conditional_on or self.conditional_on[0] != "face" or self.independence_group in self.conditional_on:
            raise EvidenceError("invalid_conditional_context")
        for item in self.conditional_on:
            _text(item, "conditional_context")
        if _number(self.likelihood_ratio, "factor_likelihood_ratio") <= 0 or not isinstance(self.provenance, CalibrationProvenance):
            raise EvidenceError("invalid_factor_calibration")
        if self.likelihood_ratio_semantics != "uniform_conditional_lower_bound":
            raise EvidenceError("factor_requires_uniform_conditional_lower_bound")


@dataclass(frozen=True)
class DecisionPolicy:
    policy_id: str = "research-default"
    prior_probability: float | None = None
    target_probability: float | None = None
    face_calibration: FaceCalibration | None = None
    factor_calibrations: tuple[FactorCalibration, ...] = ()
    require_quality: bool = True
    require_certified_liveness: bool = True
    require_identity_bound_factor: bool = True
    certified_liveness_factors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.policy_id, "policy_id")
        for name in ("require_quality", "require_certified_liveness", "require_identity_bound_factor"):
            if type(getattr(self, name)) is not bool:
                raise EvidenceError(f"invalid_{name}")
        if self.prior_probability is not None:
            _probability(self.prior_probability, "prior_probability")
        if self.target_probability is not None:
            _probability(self.target_probability, "target_probability")
        if (self.prior_probability is None) != (self.target_probability is None):
            raise EvidenceError("incomplete_risk_policy")
        if self.prior_probability is not None and self.target_probability <= self.prior_probability:
            raise EvidenceError("target_must_exceed_prior")
        if self.face_calibration is not None and not isinstance(self.face_calibration, FaceCalibration):
            raise EvidenceError("invalid_face_calibration")
        object.__setattr__(self, "factor_calibrations", tuple(self.factor_calibrations))
        object.__setattr__(self, "certified_liveness_factors", tuple(self.certified_liveness_factors))
        seen = set()
        for factor in self.factor_calibrations:
            if not isinstance(factor, FactorCalibration):
                raise EvidenceError("invalid_factor_calibration")
            key = (factor.issuer, factor.factor, factor.conditional_on)
            if key in seen:
                raise EvidenceError("duplicate_factor_calibration")
            seen.add(key)
        for name in self.certified_liveness_factors:
            _text(name, "certified_liveness_factor")
            if "/" not in name or not all(name.rsplit("/", 1)):
                raise EvidenceError("invalid_certified_liveness_factor")


@dataclass(frozen=True)
class DecisionResult:
    status: str
    reasons: tuple[str, ...]
    calibrated: bool
    posterior_probability: float | None
    face_likelihood_ratio: float | None
    minimum_face_likelihood_ratio: float | None
    minimum_face_similarity: float | None
    counted_factors: tuple[str, ...]
    ignored_factors: tuple[str, ...]
    policy_id: str
    model_id: str
    log_posterior_odds: float | None
    minimum_log_face_likelihood_ratio: float | None = None
    calibration_fingerprints: tuple[str, ...] = ()
    assurance: str = "research_only_not_accredited"
    probability_interpretation: str = "conditional_model_lower_bound_if_uniform_calibration_holds"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _log_odds(probability: float) -> float:
    return math.log(probability) - math.log1p(-probability)


def _posterior(log_odds: float) -> float:
    if log_odds >= 0:
        return 1 / (1 + math.exp(-log_odds))
    exp = math.exp(log_odds)
    return exp / (1 + exp)


def evaluate_identity(
    face_similarity: float | None,
    evidence: Sequence[VerifiedEvidence],
    policy: DecisionPolicy,
    *,
    model_id: str,
    model_sha256: str,
    quality_passed: bool,
    liveness: LivenessEvidence | None = None,
    now: float | None = None,
) -> DecisionResult:
    """Calculate research support; accepts only server-verified evidence objects.

    The caller must consume the session before calling this function. A factor
    calibration is eligible only for the exact previously counted context. Its
    LR must be a conservative bound valid over EVERY calibrated face-score bin,
    not a conditional estimate specific to the observed score. This uniform
    bound is what makes reusing it for an adaptive score threshold legitimate.
    Within a recovery group, only one factor contributes, using the lowest
    eligible LR if multiple calibrated assertions are present. No unchecked
    independence assumption or client-provided confidence enters this function.
    """
    if not isinstance(policy, DecisionPolicy) or type(quality_passed) is not bool:
        raise EvidenceError("invalid_evaluation_input")
    current = _number(time.time() if now is None else now, "time")
    _text(model_id, "model_id")
    _sha(model_sha256, "model_sha256")
    if face_similarity is not None:
        face_similarity = _number(face_similarity, "face_similarity")
        if not -1 <= face_similarity <= 1:
            raise EvidenceError("invalid_face_similarity")
    proofs = list(evidence)
    if liveness is not None:
        if not isinstance(liveness, VerifiedEvidence):
            raise EvidenceError("unverified_liveness")
        if liveness not in proofs:
            proofs.append(liveness)
    binding = None
    unique_proofs = []
    seen_assertions = set()
    for proof in proofs:
        if not isinstance(proof, VerifiedEvidence):
            raise EvidenceError("unverified_evidence")
        if proof.issued_at > current or proof.expires_at <= current:
            raise EvidenceError("stale_verified_evidence")
        this_binding = (proof.subject, proof.audience, proof.challenge, proof.evidence_digest)
        if binding is not None and this_binding != binding:
            raise EvidenceError("mixed_evidence_bindings")
        binding = this_binding
        if proof.assertion_id not in seen_assertions:
            unique_proofs.append(proof)
            seen_assertions.add(proof.assertion_id)
    proofs = unique_proofs
    reasons: list[str] = []
    ignored: list[str] = []
    gates_failed = False
    if policy.require_quality and not quality_passed:
        reasons.append("face_quality_gate_failed")
        gates_failed = True
    approved_liveness = any(f"{p.issuer}/{p.factor}" in policy.certified_liveness_factors for p in proofs)
    if policy.require_certified_liveness and not approved_liveness:
        reasons.append("certified_liveness_missing")
        gates_failed = True
    identity_bound = any(p.identity_bound for p in proofs)
    if policy.require_identity_bound_factor and not identity_bound:
        reasons.append("identity_bound_enrolment_evidence_missing")
        gates_failed = True

    face = policy.face_calibration
    usable = face is not None and face.provenance.independently_validated
    if face_similarity is None:
        reasons.append("face_comparison_missing")
        usable = False
    if not usable:
        reasons.append("independent_face_calibration_missing")
    elif face.model_id != model_id or face.model_sha256 != model_sha256:
        reasons.append("face_calibration_model_mismatch")
        usable = False
    if policy.prior_probability is None or policy.target_probability is None:
        reasons.append("documented_risk_policy_missing")
        usable = False
    if not usable:
        return DecisionResult("insufficient_evidence", tuple(reasons), False, None, None, None, None, (), tuple(f"{p.issuer}/{p.factor}:not_used_without_face_calibration" for p in proofs), policy.policy_id, model_id, None)

    face_lr = face.likelihood_ratio(face_similarity)
    log_prior = _log_odds(policy.prior_probability)
    context = ["face"]
    log_factor_lr = 0.0
    counted: list[str] = []
    consumed_assertions: set[str] = set()
    fingerprints = [face.provenance.sha256, face.provenance.target_risk_sha256]

    # Calibrations are evaluated in administrator-defined order. The context is
    # a chain rule context, not a statement that differently named factors are
    # automatically independent. Alternative contexts can be supplied explicitly.
    for calibration in policy.factor_calibrations:
        if calibration.independence_group in context or tuple(context) != calibration.conditional_on:
            continue
        candidates = []
        for other in policy.factor_calibrations:
            if other.independence_group != calibration.independence_group or other.conditional_on != tuple(context) or not other.provenance.independently_validated:
                continue
            for proof in proofs:
                if (proof.issuer, proof.factor, proof.independence_group) == (other.issuer, other.factor, other.independence_group) and proof.identity_bound:
                    candidates.append((other.likelihood_ratio, f"{proof.issuer}/{proof.factor}", other, proof))
        if not candidates:
            continue
        lr, name, selected, proof = min(candidates, key=lambda item: (item[0], item[1]))
        log_factor_lr += math.log(lr)
        context.append(selected.independence_group)
        counted.append(name)
        consumed_assertions.add(proof.assertion_id)
        fingerprints.extend((selected.provenance.sha256, selected.provenance.target_risk_sha256))

    for proof in proofs:
        if proof.assertion_id in consumed_assertions:
            continue
        name = f"{proof.issuer}/{proof.factor}"
        if not proof.identity_bound:
            ignored.append(name + ":account_possession_or_nonidentity_evidence")
        elif proof.independence_group in context:
            ignored.append(name + ":shared_recovery_group_not_multiplied")
        else:
            ignored.append(name + ":conditional_calibration_missing")
    if proofs and not counted:
        reasons.append("no_calibrated_identity_factor_counted")
    if policy.require_identity_bound_factor and not counted:
        gates_failed = True

    log_posterior = log_prior + math.log(face_lr) + log_factor_lr
    required_log_face = _log_odds(policy.target_probability) - log_prior - log_factor_lr
    required_face = math.exp(required_log_face) if required_log_face <= math.log(sys.float_info.max) else None
    threshold = next((band.lower for band in face.bands if math.log(band.likelihood_ratio) >= required_log_face), None)
    meets = log_posterior >= _log_odds(policy.target_probability)
    if gates_failed:
        status = "insufficient_evidence"
    elif meets:
        status = "experimental_supported"
        reasons.append("configured_research_target_met")
    else:
        status = "review_required"
        reasons.append("configured_research_target_not_met")
    return DecisionResult(status, tuple(reasons), True, _posterior(log_posterior), face_lr, required_face, threshold, tuple(counted), tuple(ignored), policy.policy_id, model_id, log_posterior, required_log_face, tuple(dict.fromkeys(fingerprints)))


def _provenance(entry: Any, parent: Path) -> CalibrationProvenance:
    if not isinstance(entry, dict) or set(entry) != {"document", "sha256", "target_risk_document", "target_risk_sha256", "independently_validated"}:
        raise EvidenceError("invalid_provenance")
    provenance = CalibrationProvenance(**entry)
    for field_name, digest_name in (("document", "sha256"), ("target_risk_document", "target_risk_sha256")):
        path = (parent / getattr(provenance, field_name)).resolve()
        # The fingerprint pins evidence, but cannot itself prove the report's
        # scientific validity or independence. That is an operator responsibility.
        with path.open("rb") as stream:
            hasher = hashlib.sha256()
            for chunk in iter(lambda: stream.read(128 * 1024), b""):
                hasher.update(chunk)
            digest = hasher.hexdigest()
        if digest != getattr(provenance, digest_name):
            raise EvidenceError("calibration_document_fingerprint_mismatch")
    return provenance


def load_policy_config(path: str | Path) -> DecisionPolicy:
    """Load the startup admin policy and check referenced report fingerprints."""
    path = Path(path)
    data = read_admin_json(path)
    expected = {"version", "policy_id", "prior_probability", "target_probability", "face_calibration", "factor_calibrations", "require_quality", "require_certified_liveness", "require_identity_bound_factor", "certified_liveness_factors"}
    if not isinstance(data, dict) or set(data) != expected or type(data["version"]) is not int or data["version"] != 1:
        raise EvidenceError("invalid_policy_config")
    face = data["face_calibration"]
    if face is not None:
        if not isinstance(face, dict) or set(face) != {"model_id", "model_sha256", "bands", "provenance"} or not isinstance(face["bands"], list):
            raise EvidenceError("invalid_face_calibration_config")
        bands = []
        for band in face["bands"]:
            if not isinstance(band, dict) or set(band) != {"lower", "upper", "likelihood_ratio"}:
                raise EvidenceError("invalid_score_band_config")
            bands.append(ScoreBand(**band))
        face = FaceCalibration(face["model_id"], face["model_sha256"], tuple(bands), _provenance(face["provenance"], path.parent))
    if not isinstance(data["factor_calibrations"], list) or not isinstance(data["certified_liveness_factors"], list):
        raise EvidenceError("invalid_policy_lists")
    factors = []
    for factor in data["factor_calibrations"]:
        if not isinstance(factor, dict) or set(factor) != {"issuer", "factor", "independence_group", "conditional_on", "likelihood_ratio", "provenance", "likelihood_ratio_semantics"} or not isinstance(factor["conditional_on"], list):
            raise EvidenceError("invalid_factor_calibration_config")
        factors.append(FactorCalibration(factor["issuer"], factor["factor"], factor["independence_group"], tuple(factor["conditional_on"]), factor["likelihood_ratio"], _provenance(factor["provenance"], path.parent), factor["likelihood_ratio_semantics"]))
    return DecisionPolicy(data["policy_id"], data["prior_probability"], data["target_probability"], face, tuple(factors), data["require_quality"], data["require_certified_liveness"], data["require_identity_bound_factor"], tuple(data["certified_liveness_factors"]))
