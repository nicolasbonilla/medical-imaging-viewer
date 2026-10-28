# PRB-022 — The Sign-In Page and Documents Claim Security and Compliance the Device Does Not Have

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: see PRB-020. GitHub Issue: not raised.*

**Problem ID**: PRB-022
**Reporter**: browser capture of the release candidate, 2026-10-28 (F15); search of the whole interface and of the
documents by the AI coding agent
**Date**: 2026-10-28
**Version**: `main` @ `70cc5c7`
**Severity**: **Major** (proposed; labelling / information supplied by the manufacturer that is not true — EU MDR
art. 7 prohibits misleading claims; no patient-harm path of its own). **PENDING owner approval.**
**Status**: OPEN — DRAFT. Fix on branch `fix/platform-security-findings-prb020` for the items marked FIXED.

**Description and findings** (each verified against the code; production configuration was not read):

| # | Where (`main` @ `70cc5c7`) | Claim | Fact | Here |
|---|---|---|---|---|
| 1 | `LoginPage.tsx:414` | "MFA enforced · NIST SP 800-63B AAL2" | Sign-in is password only (`authentication.py` login); WebAuthn passkeys are an optional *alternative* single factor; nothing requires a second factor for any role. AAL2 requires two factors | **FIXED** (removed) |
| 2 | `LoginPage.tsx:414` | "Data never leaves your jurisdiction" | The AI report draft is sent to an external model provider; hosting region is not stated anywhere verifiable | **FIXED** (removed) |
| 3 | `LoginPage.tsx:395-396` | badges "HIPAA 2026", "ISO 27001 2022" | No HIPAA assessment and no ISO 27001 certification exist | **FIXED** (removed) |
| 4 | `LoginPage.tsx:398` | badge "TLS 1.3" | TLS ends at Google's front ends; the minimum version is not enforced (REQ-SEC-001 itself says TLS 1.2 or higher); `TLS_MIN_VERSION` applies only to the app's own server, which is off (`TLS_ENABLED=false`) | **FIXED** (removed); "IEC 62304 Class C" and "AES-256 · at rest" kept (software safety class; encryption at rest per REQ-SEC-006) |
| 5 | `en/es/de.json` `auth.securityBadges.iso27001`, `.hipaa` ("ISO 27001:2022 Compliant", "HIPAA Secure") | unused keys, ready to be shown again | — | **FIXED** (removed) |
| 6 | `authentication.py:284` | "Please verify your email to activate your account" | No e-mail verification exists | **FIXED** (true message) |
| 7 | `patients.py` search docstring | "Supports full-text search on name, MRN, and email" | `query` is ignored | **FIXED** (docstring) |
| 8 | `README.md:28`, `:614`; `00_IEC_62304_Master_Compliance_Document.md:1239`; `ISMS-001:153`, `:201` | "HIPAA compliant" badge; authentication "Firebase Auth + JWT + WebAuthn" — COMPLIANT | Firebase Auth is not used for sign-in; single factor | **FIXED** (rows corrected, status set to "re-assessment pending (owner)"); README badge removed (CAPA-014 removes it identically) |
| 9 | `backend/scripts/README.md:520` | "ISO 27001:2022 Compliant" | no certification | **FIXED** |
| 10 | `reportViewer.hipaaNote` (en/es/de), `README.md:39`, `:290`, `frontend/src/api/aiReport.ts:21` | "HIPAA Compliant — no PHI transmitted" | the AI report sent free text (CAPA-014) | **NOT CHANGED HERE** — removed by CAPA-014 (PR #67, on the release branch); changing it here would conflict |
| 11 | `README.md:617`; `04_Software_Architecture_Design.md:61`, `:131`; `12_Cybersecurity_Assessment.md:33`, `:69`, `:113`; `ISMS-001:120`, `:161`, `:162`, `:203`, `:207` | "TLS 1.3 enforced" | not verified; see row 4 | **OPEN** — owner to verify the TLS policy of Cloud Run / Firebase Hosting in production and correct (README:617 is next to a CAPA-014 change and would conflict) |
| 12 | `ISMS-001:162` | "JWT RS256 (tokens)" | the code signs with HS256 (`config.py` `JWT_ALGORITHM` default) | **OPEN** (owner) |
| 13 | `LoginPage.tsx:187` | "AI-Powered Brain MRI Analysis · IEC 62304 Class C Medical Device" | the device is not CE-marked; whether and how to state its regulatory status on the sign-in page is a regulatory decision | **OPEN** — owner decision (e.g. "Not CE-marked — not for clinical use" or the intended-use statement) |
| 14 | `LoginPage.tsx:407-411` | links "Privacy Policy · Terms of Service · Cookie Policy" | all point to `#` (no document) | **OPEN** — owner decision (link the real documents or remove) |
| 15 | `LoginPage.tsx:139-142`, `:270-281` | Google / Apple / GitHub sign-in buttons ("coming soon — contact admin for early access") | not implemented | **OPEN** — owner decision (they suggest a capability that does not exist) |
| 16 | `LoginPage.tsx:394` (badge "IEC 62304 · Class C", kept by the first version of this fix) | looked like the removed certification badges | no conformity assessment exists; the software safety class is a development-process classification, not a certificate | **FIXED** (review of PR #70, m7: badge removed; the subtitle, row 13, stays an owner decision) |
| 17 | `README.md:609` | "The security architecture **satisfies IEC 81001-5-1:2021** … **95% alignment**" | no conformity assessment; the ISMS-001 mapping is a self-assessment with rows under re-assessment | **FIXED** (review of PR #70, m7: reworded to "designed against …; no conformity assessment or certification has been performed") |

**Root Cause**: marketing and "research-backed" badge text written into the interface and documents without a
requirement or a verification step; nothing checks a claim against the code.

**Fix** (rows marked FIXED): requirement **REQ-REG-011** (no security, privacy or compliance claim that is not
verified); risk control **RC-086** (sign-in page and translation files free of the claims, test-bound).

**Verification**: `frontend/src/pages/LoginPage.prb020.test.tsx` — `rc086 prb022 *` (2 tests: the rendered page has
no MFA / multi-factor / AAL2 / 800-63 / jurisdiction / HIPAA / ISO 27001 / TLS 1.3 text; the translation files no longer
hold the badge claims). Both fail on `70cc5c7`. Negative controls F4, F5. Documents: by inspection (diff of this PR).

**Owner decisions (PENDING)**: severity Major; rows 11–15; whether a labelling review (all claims in the interface,
README, web site and QMS documents) is added as a CAPA action (proposed).

## Review of PR #70 (2026-10-28) *(review of PR #70, 2026-10-28 — DRAFT, PENDING owner approval)*

Rows 16 and 17 added (m7). Test `frontend/src/pages/LoginPage.prb022.review1.test.tsx` — `rc086 prb022 no standard is shown
as a badge` (fails at `7de9334`, `records/risk_verification/PRB-020_review1_tests_on_7de9334_2026-10-28.json`); negative control VF6 (`records/risk_verification/PRB-020_negative_controls_2026-10-28.json`). README by inspection.
