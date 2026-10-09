# Mirid Identity

Mirid Identity is the open-source age-verification layer being built for Mirid,
with deployment planned for Australia once the service is ready. It combines
local facial comparison with trusted identity and age evidence. The aim is to
accommodate legitimate changes in appearance while meeting a defined assurance
target.

This first release compares two supplied face images using OpenCV YuNet and
SFace, verifies signed evidence against configured trusted issuers, and can
evaluate administrator-supplied calibrated policies. No empirical calibration or
trusted issuer is supplied by default. It includes a native Mirid interface for image
selection, camera capture, and signed-evidence transactions.

Version 0.1.0 supplies the face-comparison and signed-evidence foundations.
It does not yet issue age-verification decisions or enforce access in Mirid.
Trusted age claims, holder binding, an age policy and validated decision criteria
remain to be integrated. The current research result labels describe the
validation state of these components, not the purpose of the product.
See [the defined service scope](docs/service-scope.md).

## What the result means

A cosine similarity is a model score, not a probability of identity. A webcam
capture is not certified liveness. Possession of an account key only supports a
legal identity when the key's enrollment is independently bound to that identity.

Uncalibrated comparisons return a research result. Configured policies need
documented calibration, trusted issuer keys, dependency groups, and a defined
threat model. The software does not claim government accreditation, certify an
ID document, or make another organisation accept a verification result.

## Design

- Run facial inference locally with pinned, integrity-checked model weights.
- Process reference and probe images in memory, outside chat and model providers.
- Bind every signed assertion to a subject, audience, fresh challenge and the
  exact image transaction. Reject expiry, replay, unknown issuers and tampering.
- Derive identity binding and correlated-factor groups from trusted configuration.
- Combine calibrated conditional likelihood ratios in log-odds space.
- Keep uncertainty visible and support additional evidence when a result is
  inconclusive.

The research calculation is:

    configured odds = assumed prior odds * calibrated face-bin LR
                    * product of uniform conditional factor LR lower bounds

The implementation starts with the facial contribution, then applies evidence
likelihood ratios calibrated conditionally on the preceding evidence. Each
factor must have a documented conservative lower bound valid across every
calibrated face-score bin and eligible preceding-factor choice in its context.
An LR estimated only at the observed face score cannot be reused to derive a
different face threshold. The reported posterior has a lower-bound interpretation
only when the prior, face calibration and uniform conditional bounds hold for
the intended population and threat model.
Multiple checks with a shared compromise or recovery path must not be counted as
independent multipliers. Stronger evidence can reduce the facial likelihood
ratio required by the same overall risk target; it cannot turn an unmeasured
model score into a validated probability.

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[face,test]'
.venv/bin/mirid-identity models download
.venv/bin/mirid-identity compare reference.jpg probe.jpg
.venv/bin/pytest
```

The model download is separate from comparison. After installation and download,
the comparison does not contact a model provider. See the CLI help for model
directory options. Keep personal photos, private keys and trust configuration
outside the repository.

## Mirid integration

Open **Identity verification** from Mirid's tools menu. Choose a reference photo,
then capture or select a comparison photo. The optional signed-evidence panel
prepares a short-lived challenge for configured issuers and evaluates returned
assertions against that same transaction.

The `/identity` routes accept only local clients. Images and session state are
ephemeral; comparison images are not added to conversations, synchronised,
included in telemetry, or written to an audit log. Explicitly exported research
reports should contain numerical results and configuration fingerprints, not
biometric images or embeddings.

## Evidence and registration

See [the registration routes](docs/registration.md),
[the application readiness template](docs/application-readiness.md),
[the signed-evidence protocol and policy schema](docs/evidence-protocol.md),
[the evaluation protocol](docs/evaluation.md), and
[the milestone record](docs/milestones.json).

A real acceptance study needs consented genuine comparisons across appearance
changes, held-out images, impostor comparisons, and presentation/injection attack
tests. Passing one person's example is a useful development case, not an estimate
of community-wide false acceptance or rejection rates.

## Licence

Mirid Identity source is licensed under Apache-2.0. Model files retain their
upstream licences, supplied in `src/mirid_identity/model-licenses`. These notices describe the
upstream distribution terms; they do not constitute an independent audit of the
training data.
