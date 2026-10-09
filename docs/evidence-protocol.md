# Evidence and decision policy

The default configuration has no trusted issuers, no calibrated likelihood ratios,
and no claimed identity acceptance rate. A face similarity is a measurement, not
an identity probability. All decisions are research outputs, including
`experimental_supported`; none means government accreditation or verified identity.

## Trust boundary

`examples/trust.json` and `examples/policy.json` are safe startup configurations.
The service administrator may select local configuration files at startup. Their
paths and contents must never be accepted in an HTTP verification request. The
loader requires a regular owner-controlled file that other users cannot write.
The default files deliberately trust no public key. A submitted token cannot
introduce its own key or likelihood ratio.

An issuer entry has this shape. The public key is an unpadded base64url encoding
of a 32-byte Ed25519 public key; the placeholder is deliberately invalid:

```json
{
  "version": 1,
  "audience": "mirid-identity",
  "issuers": {
    "independent-enrolment-provider/key-2026-01": {
      "public_key": "REPLACE_WITH_PINNED_32_BYTE_PUBLIC_KEY",
      "max_lifetime_seconds": 300,
      "factors": {
        "identity-bound-hardware-key": {
          "independence_group": "provider-enrolment-and-recovery",
          "identity_bound": true
        },
        "ordinary-account-possession": {
          "independence_group": "provider-enrolment-and-recovery",
          "identity_bound": false
        }
      }
    }
  }
}
```

`identity_bound: true` is an administrator's trust decision about an issuer's
identity enrolment process. It is not something a claimant may assert. A hardware
key or account login alone establishes possession; it does not establish civil
identity. Issuer assertions should originate from an independent authenticated
provider. Do not give the local claimant a signing key and treat its signatures as
independent proof. Different issuers can still share a recovery dependency; assign
them the same `independence_group` when that is the case.

## Signed assertion

The wire format is `base64url(payload_bytes).base64url(signature)`. The signature
is Ed25519 over the exact bytes
`b"mirid-identity-assertion-v1\\x00" + payload_bytes`, where the domain separator ends
in one NUL byte, not the literal characters `\\x00`. The payload is JSON with
exactly these fields:

```json
{
  "v": 1,
  "iss": "independent-enrolment-provider/key-2026-01",
  "sub": "issuer-recognised-subject-identifier",
  "aud": "mirid-identity",
  "challenge": "SERVER_ISSUED_RANDOM_SESSION_CHALLENGE",
  "nonce": "ISSUER_GENERATED_RANDOM_NONCE_AT_LEAST_22_CHARACTERS",
  "iat": 1791590400,
  "exp": 1791590700,
  "factor": "identity-bound-hardware-key",
  "evidence_digest": "64_lowercase_hex_sha256_characters_binding_this_transaction"
}
```

The sample timestamps are illustrative and are not fresh credentials. The
`sign_assertion` Python utility is for issuer implementations and tests; it is
not a service signing endpoint. An issuer must independently authenticate the
subject and review the assertion's scope before signing.

The server creates a one-use challenge and binds it to a subject, audience and
digest of the immutable reference/probe transaction. It consumes the session
before evaluating proofs. Failed or expired sessions cannot be reused. The
assertion verifier checks the configured key, factor, audience, subject, digest,
challenge, issue time, expiry, maximum age and nonce. A successful verification
consumes that nonce atomically. Invalid signatures do not reserve attacker-chosen
nonces. A batch in which a later proof fails can consume earlier valid nonces;
retry with a new session and fresh assertions.

The in-memory store is appropriate to the local prototype: a restart also loses
all outstanding sessions. Deployments spanning processes must share a session
and nonce database, rather than issuing process-local challenges inconsistently.
The provided SQLite stores support an owner-only file when persistence is needed.
Neither store writes facial images or embeddings.

## Conditional research calculation

For identity hypothesis `H`, posterior odds are calculated in log space:

```text
log posterior odds = log prior odds + log LR_face
                   + sum(log LR_factor_i_given_already_counted_evidence)
minimum log LR_face = log target odds - log prior odds
                    - sum(log LR_factor_i_given_already_counted_evidence)
```

No prior, target or LR is accepted from a claimant. The default has none. Real
calibration requires representative, consented genuine/impostor and attack data,
uncertainty bounds and a documented target-risk decision. A configured number
cannot prove its own scientific validity.

`face_calibration` is an object with `model_id`, `model_sha256`, `bands` and
`provenance`. Every band contains numeric `lower`, `upper` and `likelihood_ratio`.
Bands cover cosine similarity from -1 to 1 continuously, with nondecreasing LRs.
Bounds are lower-inclusive and upper-exclusive except the final upper bound 1.
Calibration is invalid for a different model ID or model fingerprint.

Each `factor_calibrations` entry has `issuer`, `factor`, `independence_group`,
`conditional_on`, `likelihood_ratio`, `likelihood_ratio_semantics` and
`provenance`. `likelihood_ratio_semantics` must be exactly
`uniform_conditional_lower_bound`. `conditional_on` must match
the exact sequence already counted: `['face']` for the first factor, then for
example `['face', 'document-provider-recovery']` for the next. Calibration must
justify a conservative LR across EVERY supported face-score bin and the exact
evidence context, including all eligible preceding-factor choices and the
documented group-selection rule. This is a uniform lower bound, not a
per-observed-score LR.
For example, an LR fitted only for similarity 0.7 cannot be reused to calculate
an acceptance threshold of 0.4. The present implementation deliberately requires
the uniform bound to make that threshold calculation valid. If that condition
cannot be established empirically, leave the factor calibration absent; a
per-bin conditional model would need a different evaluator. The reported
posterior is a model-based lower bound only when the calibration, prior and
conditional scope hold. It is not a universal identity confidence.
The evaluator does not infer independence from different factor names. At most
one factor per recovery group contributes. If several applicable proofs share a
group, the smallest eligible LR contributes. Pure account-possession evidence is
reported but does not increase the identity probability.

Both calibration objects include this provenance structure:

```json
{
  "document": "reports/independent-calibration.json",
  "sha256": "SHA256_OF_THAT_REPORT",
  "target_risk_document": "reports/target-risk.json",
  "target_risk_sha256": "SHA256_OF_THE_TARGET_RISK_REPORT",
  "independently_validated": true
}
```

The loader checks report fingerprints against the files, and the evaluator
requires `independently_validated` for evidence to contribute. The flag represents
the administrator's recorded assessment; software cannot establish report
authorship or independence from a flag. Never mark synthetic test numbers as a
real calibration. The test suite uses visibly synthetic fixtures only.

Quality and certified liveness gates apply independently of the arithmetic.
`certified_liveness_factors` contains approved `issuer/factor` names and requires
an actual verified signed assertion. A webcam capture, blink, pose change or
checkbox does not satisfy this gate. The server must configure an appropriately
tested provider before claiming certified liveness.

## Outputs

- `insufficient_evidence`: calibration or a required quality, liveness or
  identity-enrolment gate is missing.
- `review_required`: calibrated evidence does not meet the configured research
  target.
- `experimental_supported`: calibrated evidence meets the research target and
  configured gates. This remains an experimental result.

Reports contain the posterior under the configured model, required face LR,
corresponding calibrated score threshold, counted and ignored factors, and
calibration fingerprints. These values describe the configured research model;
they are not guaranteed error rates for an untested population.

The signing primitive uses the maintained Python
[cryptography Ed25519 implementation](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/).
