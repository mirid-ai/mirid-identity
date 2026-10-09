# Australian applicant entity route

Official-source research checked 10 October 2026. This document contains general
eligibility and preparation information only. No company, ABN or director ID has
been applied for by this project, and no fee has been paid. Personal details,
identity documents, application answers and signed consents belong in private
company records, not this public repository.

## Relevant applicant types

Digital ID Act 2024 section 14(2) permits accreditation applications from an
Australian incorporated body corporate, a registered foreign company, or the
specified Commonwealth/state/territory public bodies. An ordinary individual or
sole trader is not in that list. Neither a business name nor an ABN creates an
eligible incorporated applicant. The Act's general definition of `entity` is
broader, but it does not override section 14(2). The current Federal Register
version list identifies the 21 February 2025 compilation as the latest version.
[Digital ID Act, section 14](https://www.legislation.gov.au/C2024A00025/2025-02-21/2025-02-21/text/original/epub/OEBPS/document_1/document_1.html),
[current versions](https://www.legislation.gov.au/C2024A00025/latest/versions)

For a new private Australian applicant, a proprietary company limited by shares
(`Pty Ltd`) is a practical route to that body-corporate requirement. This is a
route assessment, not a statement that incorporation confers accreditation or
that developing verification software automatically requires accreditation.

## Company and product scope

The proposed business is a software company. Its defined service is Mirid's own
age-verification layer, being developed for planned activation in Australia
using facial comparison and trusted cryptographic identity and age evidence.
A generic company name can hold this and other software projects without making
its legal name the product name. The applicable accreditation scope and detailed
production operating requirements still need to be specified.

The current implementation compares faces and verifies session-bound identity
assertions; it does not yet verify age. Age claims and issuer trust, calibration,
liveness evidence and the age policy must be implemented and validated before
production activation. No age threshold or accredited status is assumed here.

Incorporation establishes the legal entity. Acceptance of its software or
verification results by another platform requires that platform's agreement;
company registration does not establish that acceptance or regulatory approval.
See the [LinkedIn recovery and integration research](linkedin-acceptance.md).

## Straightforward company route

A proprietary company can have one person as both its sole director and sole
shareholder. At least one director must normally live in Australia; directors
must be at least 18, eligible to act and have applied for a director ID before
appointment. A secretary is optional for a proprietary company. Written and
signed officeholder consent must be retained.
[ASIC officeholder requirements](https://www.asic.gov.au/for-business-and-companies/companies/company-building-blocks/company-officeholders-directors-and-secretaries),
[ASIC director eligibility](https://www.asic.gov.au/for-business-and-companies/small-business-director-essentials/becoming-a-company-director)

Before submission, settle the company name, registration state, registered office
and principal place of business, director/member details, share structure and
governance arrangement. ASIC allows the assigned ACN to be used as the company
name if a separate name is not chosen. It issues an ACN and registration
certificate when the company is registered.
[ASIC company registration](https://www.asic.gov.au/for-business-and-companies/companies/register-a-company)

If the same person is sole director and sole shareholder, ASIC says the ordinary
replaceable rules do not apply. Do not describe that arrangement as adopting
replaceable rules without considering the applicable single-person provisions.
[ASIC replaceable rules](https://www.asic.gov.au/for-business-and-companies/companies/register-a-company/the-replaceable-rules-for-company-governance)

## Current fees and published timings

| Step | Government charge | Published timing or limitation |
| --- | --- | --- |
| Director ID | Free | Online is the fastest route; successful online completion displays the number. Personal identity checks can require another route. |
| Ordinary company registration with share capital | AUD 636 from 1 July 2026 | BRS form takes around 15 minutes; confirmation should arrive within 2 business days if required documents and payment are complete. |
| Proprietary company annual review | AUD 342 from 1 July 2026 | Recurring company obligation, separate from the incorporation fee. |
| ABN | Free through the government | Successful straight-through applications issue immediately; referred applications have a 20-business-day review aim. |
| Separate business name, if needed | AUD 47 for 1 year or AUD 108 for 3 years from 1 July 2026 | Required if trading under a name different from the registered company name; not itself incorporation. |

Fee figures are from the Australian Government's current fee-change notice.
ASIC's current fee pages returned unresolved template placeholders during this
research. Recheck the actual government payment summary before approving a
transaction. These figures exclude private intermediary fees.
[Government fee notice](https://business.gov.au/news/changes-for-businesses-from-1-july-2026),
[company-registration timing](https://business.gov.au/registrations/register-a-company),
[ABRS director ID](https://www.abrs.gov.au/director-identification-number),
[ABR processing](https://www.abr.gov.au/business-super-funds-charities/applying-abn),
[ABN government fee](https://abr.business.gov.au/FAQ/ABNBasics)

The Business Registration Service currently displays an intermittent disruption
notice for company/business-name registrations and payments. Treat the ordinary
two-business-day guidance as conditional, not a promised finish date.
[Business Registration Service](https://register.business.gov.au/)

## Human identity step: director ID

ABRS requires the prospective director to apply personally; an agent, accountant
or lawyer cannot apply for the person's director ID. Apply before appointment.
Existing director IDs are retained rather than creating another one.
[ABRS application rules](https://www.abrs.gov.au/director-identification-number/top-questions-when-applying-director-id)

Online application uses myID with at least Standard identity strength, residential
address details held by the ATO and answers to two ATO-record questions. Providing
a TFN is optional. The person should enter identity and tax details directly in
the official ABRS/myID flow.
[ABRS identity requirements](https://www.abrs.gov.au/director-identification-number/apply-director-identification-number/verify-your-identity)

A new driver's licence is not necessarily a prerequisite: Standard myID accepts
two supported documents, and a birth certificate followed by Medicare can be an
available combination when the records match. Standard myID does not require the
Strong-level selfie process. Document verification still has to succeed.
[myID identity-strength requirements](https://www.myid.gov.au/how-to-set-up-myid?path=increase-your-identity-strength)

If online identity setup is unavailable, ABRS has a telephone path. Its document
list includes a full Australian birth certificate or eligible passport as a
primary document and Medicare as a secondary document, plus ATO record checks.
For residents in Australia, ABRS says to phone first; it sends a paper application
if it cannot issue the director ID by phone. No phone or paper completion
time is promised here.
[ABRS alternative identity checks](https://www.abrs.gov.au/director-identification-number/apply-director-identification-number/verify-your-identity)

## ABN after incorporation

An ASIC-registered Corporations Act company is entitled to an ABN. The company
needs its own ACN before obtaining its company ABN; a person's existing sole
trader ABN is not the company's ABN. A company also needs its own TFN. Select any
additional tax registrations according to the actual business circumstances.
[ABR company entitlement](https://www.abr.gov.au/business-super-funds-charities/applying-abn/abn-entitlement/companies-and-other-entities),
[government tax-registration guidance](https://business.gov.au/registrations/register-for-taxes/tax-registration-for-your-business)

## What can be prepared and what needs the person

Preparation can cover official name-availability searches, a comparison of
available names, draft registration answers, unsigned consent records, proposed
share/member records and a final fee/submission summary. A name search is not a
reservation or registration. Drafts should retain unconfirmed fields as blank.

The person supplies and confirms their legal details, chooses the ownership and
company arrangements, personally completes director ID identity proof, gives
required consents, and reviews the final declarations and fee before submission.
No declarations should be made from guessed facts and no private identity details
should be copied into the open-source project.

## Nonprofit alternatives

Open-source licensing does not require nonprofit incorporation. A Victorian
incorporated association is only relevant if a genuine member-based nonprofit
organisation is intended: Consumer Affairs Victoria requires at least five
members, no operation for members' profit, and a meeting with at least 21 days'
notice before voting to incorporate. That is not a shortcut for a one-person
company. No nonprofit structure is selected here.
[Victorian incorporation process](https://www.consumer.vic.gov.au/clubs-and-fundraising/incorporated-associations/incorporated-association-registration-process)
