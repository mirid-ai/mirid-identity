# Mirid Identity service scope

Confirmed product direction: 10 October 2026.

Mirid Identity is Mirid's own open-source age-verification layer. The software
company develops and operates this product. Australian activation is planned
once the service is implemented and validated. The company's wider purpose
remains software development and distribution.

## Intended verification flow

1. Obtain an age or date-of-birth claim from a configured, trusted source. A
   facial similarity score does not establish age.
2. Bind that claim to the person and transaction being verified, using the
   document/credential and appropriate holder checks.
3. Evaluate facial comparison alongside trusted, cryptographically confirmed
   authentication evidence. Account authentication must have a defined binding
   to the identity claim. Calibrated policy must account for shared recovery and
   compromise paths so repeated evidence is not treated as independent.
4. Apply Mirid's configured age requirement and the validated verification
   policy. The age threshold has not yet been selected; do not infer one from
   the deployment country or from this document.
5. Return the minimum decision Mirid needs, bound to its audience, subject and
   transaction, with expiry and replay protection. The intended result is an age
   eligibility claim rather than routine disclosure of a full birth date or ID.

The design goal is to accommodate legitimate facial variation when the complete
evidence supports the same assurance target. That requires measurement and
validation of the combined policy, not an arbitrary lowering of face thresholds.

## Current implementation and remaining work

Version 0.1.0 implements local one-to-one face comparison, a native Mirid screen,
trusted-issuer signature verification, transaction binding, replay prevention
and a configurable evidence policy. Its default result remains uncalibrated.

It does not yet implement trusted age-claim ingestion, an age eligibility
decision, a production Mirid access gate, document authentication or certified
liveness. These are delivery requirements for the age-verification layer.
Configured trusted sources, calibration, attack testing, privacy and operational
handling, and the intended assurance scope must be completed before activation.
The user-facing flow also needs a defined route for an inconclusive result.

Research labels on current measurements are evidence-status labels. They do not
reduce the product to an unrelated experiment or make age verification an
optional future application.

## Applicant and external acceptance

The applicant company is being prepared. Incorporation, service accreditation
and deployment readiness are separate milestones. This scope does not claim
that company registration or a software release establishes any of them.

The same facial identity package is also intended to support attempts to obtain
external acceptance, including account recovery. LinkedIn acceptance is a
separate relying-party decision; it is not implied by Mirid using its own layer.
See [the LinkedIn acceptance research](linkedin-acceptance.md).
