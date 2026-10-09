# Evaluation protocol

## Primary hypothesis

Calibrated identity-bound cryptographic evidence can support acceptance of more
within-person facial variation at an unchanged overall decision-risk target.
The hypothesis must be tested against relevant attackers, including possession
of compromised credentials. Strong cryptography by itself is not an empirical
likelihood ratio for a human identity claim.

## Genuine-user evaluation

With explicit participant consent, collect reference and probe samples across
time, camera, lighting, facial hair and other appearance changes. Keep images
from the same capture session together in a partition. Separate development,
calibration and final evaluation identities/sessions; do not tune on the final
acceptance examples.

An individual participant can run private comparisons locally. Do not publish
their ID, face images, embeddings, legal name or authentication material in the
project's public timeline.

## Attack and error evaluation

Measure at least: genuine false rejections, impostor false acceptances, no-face
and multi-face handling, expired/replayed/tampered evidence, unknown issuers,
wrong subject/audience/image transaction, correlated credentials, account
takeover, stolen genuine documents, printed/video presentations and camera-feed
injection. Camera capture and successful face detection do not establish attack
resistance.

Report trial counts, sampling assumptions and uncertainty. With zero observed
false accepts in N independent, representative impostor trials, a one-sided 95%
binomial upper bound is 1 - 0.05**(1/N), approximately 3/N. Zero errors in a small
demonstration does not establish a very low operational error rate. Repeated
comparisons from the same identities are not automatically independent trials.

## Calibration and decision policy

Publish the model fingerprints, preprocessing, comparison metric, calibration
data provenance, relevant factor context, score-to-likelihood mapping, prior
assumptions, target risk, dependency groups, missing-evidence behaviour and
assurance scope. Treat an unseen factor combination as uncalibrated rather than
inventing an independence assumption.

The current adaptive-threshold evaluator requires every factor's likelihood
ratio to be a uniform conditional lower bound across all calibrated face-score
bins, eligible preceding-factor choices and the documented recovery-group
selection rule. A per-observed-score estimate does not meet that requirement.
Check this uniform scope on held-out data; if it cannot be justified, leave the
factor uncalibrated. A score-specific conditional model would require a different
evaluator that recomputes factor contributions at every candidate threshold.
The output's lower-bound interpretation is conditional on valid prior and face
calibration assumptions as well as these factor bounds; it is not an unconditional
guarantee of operational false-accept probability.

Compare a fixed face-only policy with the combined policy on held-out cases at
the same chosen risk target. A lower false rejection rate is useful only with
the reported false acceptance, attack and uncertainty results alongside it.

## External acceptance

An independently validated algorithm, an accredited identity service and a
relying party's acceptance of its assertions are separate milestones. A local
research result should not be represented as any of those approvals.
