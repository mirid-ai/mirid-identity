# Application preparation - not submitted

Prepared 10 October 2026. This is a working evidence index, not an official form,
attestation or application. Unknown applicant details remain `null` in
[application-readiness.json](application-readiness.json). No regulator has been
contacted. No registration, accreditation or government-service access is claimed.

The proposed Australian business is a software company. Its defined service is
Mirid's own age-verification layer, being developed for planned activation in
Australia using facial comparison and trusted cryptographic identity and age
evidence. The company can develop other software as well. Its legal name,
registration state, authorised officer and any accreditation scope still need
confirmation. A standalone matching algorithm, a DVS identity service provider
and an accredited Digital ID service have different scopes.

The present implementation compares faces and verifies session-bound identity
assertions. It does not yet verify age. Production activation requires an
implemented and validated age-claim protocol, trusted age-evidence issuers,
calibration, liveness evidence and a defined age policy. No age threshold is
selected in this preparation document, and no accreditation is claimed.

## Current technical evidence

| Item | Current evidence | Application meaning |
| --- | --- | --- |
| Open-source implementation | `src/mirid_identity`, Apache-2.0 licence, model licence notices | Reviewable research implementation |
| One-to-one face comparison | Pinned YuNet/SFace models, quality checks, cosine score | Uncalibrated research measurement |
| Signed identity evidence | `docs/evidence-protocol.md`, real Ed25519 tests | Protocol implementation; no trusted production enrolment provider configured |
| Signed age evidence and age decision | Not implemented; no age threshold selected | Define authenticated age claims, issuer trust, subject/session binding and the age policy before activation |
| Recovery dependencies | Conditional evidence contexts and one contribution per recovery group | Research decision logic, not validated factor error rates |
| Calibration and liveness | Empty defaults; missing evidence stops a positive research decision | Independent calibration and presentation-attack testing still required |
| Mirid integration | Local API; transient image storage; consent step | Prototype behaviour to assess against the intended production environment |
| Independent assurance | No independent report supplied | Not ready to attest compliance or submit a complete application |

## Applicant and service fields to complete

Use a private copy of the JSON template for these answers. Keep the public
repository's applicant fields blank; do not infer them from a GitHub username or
the local computer account:

- Legal entity name and type; ABN/ACN if applicable; registered address.
- Authorised officer, role and evidence of authority; contact person and details.
- Intended accredited service type, proofing level, relying parties and requested
  conditions.
- Enrolment process and authoritative document source; trust-provider contracts;
  intended deployment and data environment.
- Age-evidence sources, signed claim semantics and the applicable age policy;
  production acceptance and fallback requirements for Mirid.
- Approved DVS gateway, if that separate access route is selected.
- Independent biometric and other assessors; report scopes, versions and findings.

## Forms and evidence index

Use the regulator's current forms, not this document as a substitute. The official
forms page currently lists a service/contact form updated 25 June 2026 and an
accreditation application updated 22 September 2026. It also lists organisation,
appropriateness, associated-person and declaration forms. All applicants first
request submission instructions by emailing the Digital ID Regulator; the page
says completed forms or applications must not be emailed to that address.
[Official Digital ID Regulator forms](https://www.digitalidsystem.gov.au/digital-id-accreditation/digital-id-regulator-forms)

| Package item | Preparation status |
| --- | --- |
| Organisation and authorised officer details | Applicant fields unfilled |
| Service and contact person details | Mirid's own age-verification layer for planned Australian activation; contact unfilled |
| Accreditation application and requested conditions | Not completed; evidence outstanding |
| Statement of scope and applicability | Service purpose defined; production age policy, deployment and assurance scope outstanding |
| Age-verification implementation and evidence | Age-claim protocol and trusted age-evidence providers outstanding |
| Privacy impact assessment | Not supplied |
| Protective security and fraud assessments | Not supplied |
| Accessibility/usability assessment and testing | Not supplied |
| Independent penetration testing | Not supplied |
| Independent biometric matching/PAD reports | Not supplied |
| Technical-testing attestation | Cannot be signed on current evidence |
| Appropriateness and associated-person evidence | Applicant-specific information unfilled |
| Authorised officer declarations | Not signed |

This list is a preparation index. The complete set depends on the chosen service,
proofing level, conditions and data environment; assess it against the current
application form and guidance before making declarations.
[ACCC application guidance](https://www.digitalidsystem.gov.au/sites/default/files/2025-02/ACCC%20Digital%20ID%20Guidance%20-%20Applying%20for%20Accreditation%20v1.1.pdf)

## Initial enquiry draft - not sent

To: DigitalIDRegulator@accc.gov.au

Subject: Submission process and service scope enquiry - Mirid Identity

```text
Hello Digital ID Regulator team,

I am [AUTHORISED OFFICER NAME AND ROLE] acting for [LEGAL ENTITY NAME].
We are a software company developing Mirid Identity as Mirid's own age-verification
layer for planned activation in Australia. The intended service combines facial
comparison with trusted cryptographic identity and age evidence.

We are considering accreditation as [SERVICE TYPE] at [PROOFING LEVEL, IF KNOWN],
with [PRODUCTION OPERATING DETAILS]. The current implementation performs
one-to-one face comparison and can verify session-bound cryptographic identity
assertions from separately trusted issuers. It does not yet verify age and is
not accredited. The age-claim protocol, trusted age-evidence providers, age
policy, independent biometric calibration, liveness and assurance evidence
remain to be completed before production activation.

Please provide the current process for submitting a completed application and
the organisation/service registration forms. We would also appreciate guidance
on the appropriate application scope for [SPECIFIC SCOPE QUESTION].

No completed application or identity documents are attached to this enquiry.

Regards,
[NAME]
[ROLE]
[LEGAL ENTITY]
[CONTACT DETAILS]
```

Replace the brackets with confirmed details and review the completed message
before any authorised send. Contacting the regulator is an enquiry milestone,
not the accreditation finish line.

## Timing comparison

The planned licence-process start is Monday 12 October 2026, subject to the
applicant's confirmation. The country/state and whether this means replacement,
renewal or first issue remain unknown. Record actual start, application
acceptance, temporary/digital availability and physical receipt separately.

For the software, record working release, regulator enquiry, completed forms
submitted, application accepted as complete and accreditation decision as
separate events. Leave completion dates blank until supported by the actual
receipt, decision or delivery. Do not count an unanswered enquiry as registration
or extrapolate an accreditation deadline from the DVS registration timeline.
