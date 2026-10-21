# Paper H → product: a "Verification evidence" page in the QMS companion

**Status:** proposal (research input). Nothing here is implemented in either repository by this PR.
**Where it ships:** MSTool-AI-QMS (`nicolasbonilla/mstool-ai-qms`), the separate compliance app that
monitors this repository. **Not** in the medical device: no device code, requirement, risk control or
Class C module changes.
**Owner decision needed:** yes (scope and priority, §7).

## 1. Why

Paper H found that, in this project, the verification that failed was verification that *could not
fail* (25 of 33 episodes, `RESULTS.md` §2), that 3 of 18 "implemented" risk controls on `main` carry
an erratum despite passing negative controls, that 3 of 31 source files hashed by the mutation
records on `main` have changed since the mutations were run, and that all 31 approval lines in the
quality records were written by the agent (`RESULTS.md` §3–§4). Each of these is cheap to detect
automatically, and none is visible today without reading JSON records and running `git blame`.

The page turns the paper's measures into a standing view, so the owner, an auditor or a notified
body can see the state of the evidence rather than the claims about it.

## 2. What the page shows

**Banner, always visible:** *"Research input — derived automatically from repository data (Paper H,
`research/paper_h/`). This page is not a verification record and approves nothing."*

| Panel | Content | Source (read-only) |
|---|---|---|
| **A. Risk controls** | One row per control in `rc_test_manifest.json`: status (implemented / not_implemented / deliberately_absent / unverified), hazard, bound tests, negative-control record, **ERRATUM** flag | manifest at `main` and at each open PR head |
| **B. Negative controls** | Per record: mutations, detected, declared equivalent/redundant (with the stated reason), **unexpected survivors**, restored suite green, executed date; whether a mutation re-introduces "the defect as found" | `records/risk_verification/*_negative_controls_*.json` |
| **C. Evidence freshness** | For each record, files whose SHA-256 (UTF-8, LF) no longer matches the file at `main` → **stale evidence** (the code changed after the mutations ran) | `source_sha256` / `test_sha256` in the records vs file contents at `main` |
| **D. Locus of the check** | For each implemented control, the strongest kind of test bound to it: request through the app / real browser / round trip / unit / **source-text only** (heuristic from test names and imports; shown as "heuristic") | test files named in the manifest |
| **E. Verification history** | The 2026-04-12 → 2026-07-18 headline (21/22 → 4/22) and every erratum with its date | RCV summaries, manifest notes |
| **F. Approval provenance** | Each line in a controlled document that records an approval, the commit that wrote it, whether that commit carries the agent trailer, and whether the PR has a formal GitHub review; PRs whose description says approval is pending | `git blame`, GitHub API (reviews, merger) |
| **G. Agent contribution** | Trailer share of commits per month; commits touching controlled documents and Class C modules | git history |

## 3. Alerts (each one maps to a Paper H finding)

| Alert | Rule | Severity | Paper H |
|---|---|---|---|
| Unexpected survivor | a negative-control record lists a mutation not detected and not declared | red | M-class episodes |
| Stale evidence | any hashed file differs at `main` | amber | evidence freshness |
| Control without negative control | `implemented` with no record or no `negative_control` | red | CAPA-001 PA-1 |
| Source-text-only control | the only bound tests read source text (heuristic) | amber | S-class episodes (E10, E19) |
| No "defect as found" mutation | a record for a CAPA fix has no mutation restoring the pre-fix code | amber | CAPA-011 D0 practice |
| Transcribed approval | an approval line written by an agent-trailered commit, on a PR with 0 formal reviews | amber (informational) | RQ4 |
| Erratum on implemented control | manifest note contains ERRATUM | red until re-verified | verified-then-ineffective |

Alerts are information for the owner. The page never changes a record, never approves, never merges.

## 4. How it is built

- **Backend (QMS repo):** a new read-only service, e.g. `backend/app/services/verification_evidence_service.py`,
  using the QMS app's existing GitHub client (`github_service.py`) to read files at a commit SHA and
  `git blame`-equivalent data from the GitHub GraphQL API (`blame` on a ref). No write scope.
- **Parsers:** port, with provenance and their tests, the pure functions of `research/paper_h/`:
  `verification.normalise_record`, `verification.manifest_summary`, `verification.lf_sha256`,
  `verification.evidence_freshness`, `governance.approval_lines_authorship` (adapted to the API).
  Both record schemas (mutation dictionaries; result lists with `BEFORE-*` / `*-old` runs) must be
  supported.
- **Frontend (QMS repo):** a `VerificationEvidencePage.tsx` beside the existing Audit and
  Traceability pages, with the banner of §2 on every panel.
- **Caching:** results keyed by commit SHA; recomputed when `main` or a PR head moves.

## 5. Verification of the page itself (it must be able to fail)

- Fixture repository with known answers (like `research/paper_h/tests/conftest.py::tiny_repo`):
  one stale file, one unexpected survivor, one transcribed approval.
- **Negative controls for the page:** remove each alert rule in turn → its fixture test must fail
  (same discipline as the device's `scripts/safety/*_negative_controls.py`).
- Reproduction check: on the pinned `main` (`6209131`) the page must show 18 implemented controls,
  3 with erratum, 3 stale hashed files, 194/199 mutations detected, 31/31 approval lines written by
  agent-trailered commits — the numbers in `RESULTS.md`.

## 6. Regulatory position

- The QMS companion is quality-system software, not a medical device. Under ISO 13485 §4.1.6 its use
  for quality records needs documented validation proportionate to risk; until then, the page stays
  marked **research input** and is not cited as objective evidence in any record.
- No patient data, production data or secrets are read: only repository files and GitHub metadata.

## 7. Decisions for the owner

1. Build it in the QMS companion (recommended) or keep it as scripts in this repository only.
2. Whether stale evidence (alert C) should also become a CI check in **this** repository — that would
   be a change to the device's verification process (CAPA-001 PA-2 scope) and needs its own approval.
3. Whether "transcribed approval" should be replaced by signed reviews or e-signatures for Class C
   changes (Paper H §6, implication 4).
