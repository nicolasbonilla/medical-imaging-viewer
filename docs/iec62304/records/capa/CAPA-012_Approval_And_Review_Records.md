# CAPA-012 — Approval and Review Records: Approvals Written by the AI Coding Agent, No Formal Review on Any Pull Request

**CAPA ID**: CAPA-012
**Date Opened**: 2026-10-22 (DRAFT — opening, severity and action plan **PENDING owner approval**)
**Source**: Paper H case study (PR #57, branch `research/paper-h-case-study`: `docs/research/paper-h/RESULTS.md` §4 and `research/paper_h/out/results.json` key `rq4_governance`; computed 2026-10-21 from `main` @ `6209131` and a read-only GitHub snapshot retrieved 2026-10-21T20:24:04Z). Re-checked for this record on 2026-10-22 with read-only commands (§7).
**Severity**: **CRITICAL** (proposed; raised from Major on 2026-10-23 after the independent review of PR #62). QP-002 §5: "Critical CAPAs involve patient safety risk or regulatory non-compliance" — this is a regulatory non-compliance (ISO 13485 §4.2.4, §4.2.5, §7.3.5; IEC 62304 §5.1): 56 of 56 pull requests without a formal review; 31 of 31 approval lines in controlled documents written by the AI coding agent. CAPA-001, of the same family (records describing an intended process), is Critical. The first draft proposed Major because no product defect and no patient exposure follows from it directly, the approvals themselves were given by the owner (in chat), and the device is not on the market or in clinical use; QP-002 does not make those conditions part of the definition. The owner confirms the severity (decision D-1, §5).
**Owner**: *(to be assigned: QMS Manager / Project Lead — a person; the AI coding agent cannot own a CAPA)*
**Status**: DRAFT. Nothing is implemented. Every action below is a proposal, **PENDING owner approval**.
**Clauses**: IEC 62304:2006+A1:2015 §5.1 (§5.1.1 plan, §5.1.4 methods and tools), §9 (problem resolution: records, §9.8 test documentation of changes); ISO 13485:2016 §4.2.4 (approval of documents before issue), §4.2.5 (control of records), §7.3 (§7.3.2 planning, §7.3.5 design review records with participants).
**Procedure**: QP-002 (`docs/qms/QP-002_CAPA_Procedure.md`) · SPR-001
**Related**: SDP-001 v1.1 §4.4 control 1 and "Known limitation" (PR #49) · SDP-001 v1.2 DRAFT (this PR) · CAPA-001 (same family: records describing an intended process) · `.github/CODEOWNERS` · CR-SUMMARY-2026-04-12 · REL-001 §2.1 · CLAUDE.md "Pull Request Requirements"

**Merge order**: this PR is based on `feat/flames-in-browser-on-capa011` (PRs #52, #51, #53) and contains PR #49; merge after #52, #51, #53, #59 and #49.

---

## 1. Findings

### Finding 1 — No formal review on any pull request

At the snapshot (2026-10-21T20:24:04Z) the repository had **56 pull requests** (47 merged, 9 open, 8 of them drafts). **Formal GitHub reviews: 0 on all 56.** All 47 merges show the owner's account as merger. All 56 descriptions end with the Claude Code footer.

The project's own documents require a review:

| Document | What it requires |
|---|---|
| `CLAUDE.md` | "At least 1 code review approval" per PR; "Never modify Class C modules without a code review" |
| SDP-001 §3.3 | G2 "Project Lead + Reviewer", G3 "Code review passed" (Reviewer) |
| SDP-001 §7.2 | "3. Code review required before merge" |
| SDP-001 §9 | Reviewer: "Code review, design review, independence from author" |
| REL-001 §2.1 | "Code review completed for all changes — GitHub PR approvals"; "CODEOWNERS approvals obtained for all Class C changes" |
| CR-SUMMARY-2026-04-12 | "All Class C modules require mandatory code review via `.github/CODEOWNERS`" |

What existed instead: adversarial review by separate agent sessions (SDP-001 v1.1 §4.4 control 3), reported in PR descriptions and CAPA records, and the owner's decision given in chat. Neither is a formal review record: the reviewers are agents, not independent of the authoring agent (SDP-001 v1.1 "Known limitation"), and the owner's decision is not recorded by the owner (Finding 2).

### Finding 2 — The 31 approval lines in controlled documents were written by the agent

On `main` @ `6209131`, **31 lines in 19 controlled documents** record the owner's approval, in the form `<owner name> — approved <date> (PR #N)`. `git blame` attributes **all 31** to **five commits**, each carrying the agent's `Co-Authored-By: Claude Opus 5.5 (1M context)` trailer:

| Commit | Date | Subject | Lines |
|---|---|---|---|
| `9102200` | 2026-09-28 | record human approval of REQ-SAFE-010 / RC-010 amendment (PR #42) | 2 |
| `880a065` | 2026-10-17 | record human approval of CAPA-006 / RC-032 / REQ-SAFE-021 (PR #43) | 15 |
| `bae1a7f` | 2026-10-17 | record human approval of CAPA-007 / RC-029 completion (PR #45) | 4 |
| `31940b6` | 2026-10-17 | record human approval of CAPA-008 / RC-033/034/035 (PR #46) | 4 |
| `b39c839` | 2026-10-17 | merge; record human approval of CAPA-009 / RC-036 (PR #47) | 6 |

Each line transcribes an approval that the owner gave in a chat session with the agent. The chat is not part of the repository. Nothing in the repository binds a line to the owner: the agent commits under the owner's git identity and pushes and merges with the owner's GitHub credentials, so the author, committer, PR author and merger are all the owner's account. The only marker is the `Co-Authored-By` trailer, which the agent adds voluntarily. No commit on `main` carries a signature by the owner's own key (§7).

Three merges on `main` were made locally in agent-trailered commits (PR #46, PR #47, and the intermediate merge that recorded the PR #46 approval); the hosting records cannot tell an owner action from an agent action taken with the owner's credentials.

The full list of the 31 lines is in §6.

### Finding 3 — The repository's review controls cannot work as configured (checked 2026-10-22)

1. **`main` is not protected.** `gh api repos/nicolasbonilla/medical-imaging-viewer/branches/main/protection` returns HTTP 404 "Branch not protected"; the repository has no rulesets. SDP-001 §7.1 states "`main` branch protected, all changes via pull requests"; CR-SUMMARY-2026-04-12 lists the CI gates as "Blocks Merge: YES". Without protection, nothing blocks a merge or a direct push.
2. **The code owner is the pull-request author.** `.github/CODEOWNERS` names `@nicolasbonilla` for every Class C module and for `docs/iec62304/`, `docs/qms/`, `docs/clinical/`, and states that Class C changes "must be verified by a person other than the author". The PRs are opened under the same account, and GitHub does not let the author of a pull request approve it. The required review can therefore never be given.
3. **One identity for two actors.** The agent and the owner act under one git identity and one GitHub account. A record made by the owner and one made by the agent look the same, except for the voluntary trailer.

### Finding 4 — What worked: the agent harness refused to write the approval line (2026-10-17 to 2026-10-21)

Paper H RESULTS §4 (data source D8: operator notes, not reproducible from the repository): on two occasions between 2026-10-17 and 2026-10-21 the agent harness's permission classifier refused to let the agent write the owner's approval line into controlled documents — once after a chat message approving "everything", and once on 2026-10-21 after the owner's written authorisation. The agent did not change its permission settings; the owner was asked to merge on GitHub or to authorise explicitly. This was the correct behaviour. Since then, the open records (CAPA-010, CAPA-011, CP-FLAMES-BROWSER-001, CP-SLICE-THICKNESS-001) read "PENDING owner approval".

This is a behaviour of the tool, not a control of the quality system: it is not described in SDP-001, the QMS cannot configure or verify it, and it may change with a tool version. It must not be relied on (PA-12.2).

### Finding 5 — Consequence for the existing records

- The approvals recorded for PRs #42, #43, #45, #46 and #47 (CAPA-006 to CAPA-009; RC-010 amended, RC-029, RC-032 to RC-036; SRS-001 1.1–1.4, RMF-001 1.2–1.6, TM-001 1.1–1.3; and the CAPA-006 versions of SAD, DDS, SOUP, VVP, the Master Compliance Document, AIA-001, CER-001, GSPR-001, IFU-001, UEF-001) are **approvals given by the owner in chat and transcribed by the agent**. They are not invalidated and not rewritten (§6).
- No record of a design or code review with an independent reviewer exists for any Class C change (ISO 13485 §7.3.5 requires review records that name the participants).
- Context, not a causal claim: paper H counts 19 verification failures that reached `main` before detection (median 91 days) and no detection credited to the owner in the records (paper H notes that this does not mean the owner played no part). Independent review is one of the missing barriers; this CAPA does not claim it would have caught them.

## 2. Root Cause (QP-002 §4.3 — 5 Whys)

1. *Why are the approval lines agent-written?* Because the approval practice was built around the chat with the agent: SDP-001 v1.1 control 1 says approval is "recorded in the controlled documents with the PR number" but not **who** writes the record.
2. *Why could nobody tell the difference?* Because the agent works under the owner's git identity and GitHub token; every action is technically the owner's.
3. *Why was there no formal review?* Because the GitHub configuration makes one impossible (no branch protection; the only code owner is the PR author) and no independent reviewer has been appointed (SDP-001 v1.1 "Known limitation").
4. *Why was this not noticed earlier?* Because CR-SUMMARY-2026-04-12 and SDP-001 §7.1 described the intended configuration as if it were in place, and no check could contradict them — the CAPA-001 root cause in another medium ("records authored as descriptions of an intended system").
5. *Why does it matter for a Class C device?* Because the records are the evidence of design review and approval (ISO 13485 §4.2.4, §7.3.5); an approval that cannot be attributed to the approver is not evidence.

## 3. Corrective Actions (proposed — PENDING owner approval; none implemented)

| ID | Action | Status |
|----|--------|--------|
| **CA-12.1** | **Approvals recorded by the owner himself, from now on.** An approval, sign-off or release decision is valid only when its record is created by an action of the owner that the agent cannot perform: **(a)** an *owner-executed sign-off commit* — made by the owner in his own session, without the agent's `Co-Authored-By` trailer and without the Claude Code footer, signed with a key the agent cannot use (hardware security key, or a passphrase-protected key never loaded into the agent's environment) and shown as "Verified" by GitHub; it replaces `PENDING owner approval` by the approval line(s) for the PR it names; or **(b)** an equivalent owner action: a formal GitHub review (state APPROVED) given in the GitHub web interface (with two-factor authentication) from the owner's account on a PR authored by a separate agent identity (CA-12.3). The agent drafts everything else, writes `PENDING owner approval`, and never writes an approval line, an "Approved By" value, a signature or a sign-off date. Draft text: SDP-001 v1.2 §7.4 | PROPOSED |
| **CA-12.2** | **A review record for every PR.** Before merge, each PR has (1) at least one independent adversarial review report — by a reviewer session that did not author the change — giving the scope, findings, verdict (approve / block) and the author's responses, stored as `docs/iec62304/records/code_reviews/CR-PR<N>_<date>.md` (TPL-03 structure) and linked from the PR description; and (2) the owner's decision (approve / approve with conditions / reject) recorded per CA-12.1. For a PR that touches a Class C module, the review record states that the reviewers are not independent of the author in the sense of IEC 62304 / ISO 13485 until CA-12.5 is done | PROPOSED |
| **CA-12.3** | **Make the GitHub controls real** (repository settings, owner decision; no code). (a) A separate GitHub identity for the agent (machine user or GitHub App) with its own token and commit identity, no administrator rights and no right to merge into `main`; the owner's personal token removed from the agent's environment. (b) Protect `main`: pull request required; one approving review; review from code owners on Class C paths and regulatory documents; the CI jobs as required checks; signed commits required; no direct pushes; administrators not exempt. (c) CODEOWNERS keeps the owner, who can then review PRs authored by the agent identity. Until (a) and (b) are in place, only CA-12.1(a) produces a valid approval | PROPOSED — owner decision |
| **CA-12.4** | **Correct documents that describe controls that do not exist.** SDP-001 §7.1 ("`main` branch protected") — corrected in the SDP-001 v1.2 DRAFT of this PR. CR-SUMMARY-2026-04-12 ("Blocks Merge: YES"; "mandatory code review via CODEOWNERS") — an erratum in place, original text kept, stating that `main` was not protected and that the code owner was the PR author (not done in this PR) | PARTIAL (SDP draft only) — PENDING owner approval |
| **CA-12.5** | **An independent human reviewer for Class C changes** (SDP-001 v1.1 "Known limitation"): appoint a qualified reviewer (software, IEC 62304 experience; a neuroradiologist for clinical content) before any regulatory submission, named in SDP-001 §9. Until then, every Class C review record states the limitation | PROPOSED — owner decision |

No code is modified by this CAPA's PR. No Class C module is touched.

## 4. Preventive Actions (proposed — PENDING owner approval; none implemented)

| ID | Action | Status |
|----|--------|--------|
| **PA-12.1** | **CI check that approval lines are not introduced by agent-authored commits** (specification only; implementing it is a code change for a separate PR). A job `approval-records` in `.github/workflows/ci.yml`, on every PR and every push to `main`: for each commit in the range, take the lines it **adds** to a controlled document (`docs/iec62304/`, `docs/qms/`, `docs/mdr/`, `docs/clinical/`, `docs/ai-act/`, `docs/usability/`, including `records/` and `rc_test_manifest.json`); flag a line that records an approval — (i) a cell or field named "Approved By" / "Approval" / "Approved" whose value is not `—`, empty, or a text containing `PENDING`; (ii) the owner's name within 80 characters of "approv" (paper H pattern, either order); (iii) "signed" / "sign-off" followed by a date. **Fail** when a flagged line is added by a commit that carries the agent's `Co-Authored-By` trailer or the Claude Code footer, or — once CA-12.1(a) is in force — by a commit whose signature is not a valid signature by the owner's registered key (`git log --format=%G?`, or GitHub's commit verification). Print file, line and commit. Lines brought in by a merge commit are attributed to the commit that first wrote them. The 31 historical lines (§6) are listed in an explicit allow-list that cites this CAPA; they are not silenced by a pattern. **Its own verification** (negative controls, one at a time): an agent-trailered commit adding an approval line to the RMF → red; the same line in an unsigned owner commit → red (after CA-12.1(a)); a signed owner commit → green; an agent commit adding `PENDING owner approval` → green; a merge bringing an existing approved line → not flagged; a history run over `main` @ `6209131` finds exactly the 31 lines of §6. **Known limitation:** the trailer is voluntary; a commit that omits it passes criteria based on the trailer alone. The signature requirement is the real control; the trailer criterion catches honest mistakes | PROPOSED |
| **PA-12.2** | **Instructions to the agent.** The project instructions (`CLAUDE.md`) state that the agent never writes approval lines, "Approved By" values, signatures or sign-off dates, and writes `PENDING owner approval` instead. The harness refusal (Finding 4) is a second layer and is not relied on | PROPOSED |
| **PA-12.3** | **Retrospective note** on the 31 historical approval lines (§6), referenced from SDP-001 v1.2 §7.4. The owner decides whether to confirm them retrospectively with one owner-executed sign-off record (D-3). History is not rewritten | DRAFTED (this record) — PENDING owner approval |
| **PA-12.4** | **Effectiveness check** (QP-002 §4.6), 30 days after CA-12.1 to CA-12.3 are in force, or after the next 5 merged PRs, whichever is later: 100 % of merged PRs have a `CR-PR<N>` record and an owner decision recorded per CA-12.1; the PA-12.1 history run finds 0 approval lines added by agent-trailered or unsigned commits after the cut-over date; the branch-protection API reports `main` protected | PROPOSED |

## 5. Decisions Required from the Owner

| ID | Decision |
|----|----------|
| D-1 | Confirm the severity (**Critical**, proposed — QP-002 §5 lists regulatory non-compliance under Critical; raised from Major on 2026-10-23 after the independent review of PR #62), or record why another class applies |
| D-2 | Choose the approval mechanism for CA-12.1: signed owner sign-off commits (a), a separate agent identity with formal GitHub reviews (b), or both (recommended: both; (a) works today, (b) needs CA-12.3) |
| D-3 | Whether to confirm the 31 historical approvals retrospectively (§6) by one owner-executed sign-off record listing them, or to leave them as agent-transcribed records |
| D-4 | Whether and when to appoint an independent human reviewer for Class C changes (CA-12.5) |
| D-5 | Approve, amend or reject the SDP-001 v1.2 DRAFT text (§4.4 control 1, §7.1, §7.2, new §7.4) |
| D-6 | Authorise the PA-12.1 CI check as a separate, reviewed code change |

## 6. Retrospective Note on the 31 Historical Approval Lines (PA-12.3)

> The 31 lines listed below were written by the AI coding agent in five commits that carry its `Co-Authored-By` trailer (2026-09-28 and 2026-10-17). Each transcribes an approval that the owner gave in a chat session with the agent, for the pull request named on the line. The chat is not part of the repository. These lines are **not invalidated and not rewritten**: the history stays as it is. They are to be read as *approval given by the owner in chat, transcribed by the AI coding agent*. Retrospective confirmation by the owner: **PENDING owner approval** (D-3).

Line numbers are those on `main` @ `6209131`.

| # | Document | Line | Written by | Date | PR |
|---|---|---:|---|---|---|
| 1 | `docs/ai-act/AIA-001_AI_Act_Compliance.md` | 12 | `880a065` | 2026-10-17 | #43 |
| 2 | `docs/clinical/CER-001_Clinical_Evaluation_Report.md` | 12 | `880a065` | 2026-10-17 | #43 |
| 3 | `docs/iec62304/00_IEC_62304_Master_Compliance_Document.md` | 20 | `880a065` | 2026-10-17 | #43 |
| 4 | `docs/iec62304/02_Software_Requirements_Specification.md` | 19 | `9102200` | 2026-09-28 | #42 |
| 5 | `docs/iec62304/02_Software_Requirements_Specification.md` | 20 | `880a065` | 2026-10-17 | #43 |
| 6 | `docs/iec62304/02_Software_Requirements_Specification.md` | 21 | `31940b6` | 2026-10-17 | #46 |
| 7 | `docs/iec62304/02_Software_Requirements_Specification.md` | 22 | `b39c839` | 2026-10-17 | #47 |
| 8 | `docs/iec62304/03_Risk_Management_File.md` | 42 | `9102200` | 2026-09-28 | #42 |
| 9 | `docs/iec62304/03_Risk_Management_File.md` | 43 | `880a065` | 2026-10-17 | #43 |
| 10 | `docs/iec62304/03_Risk_Management_File.md` | 44 | `bae1a7f` | 2026-10-17 | #45 |
| 11 | `docs/iec62304/03_Risk_Management_File.md` | 45 | `31940b6` | 2026-10-17 | #46 |
| 12 | `docs/iec62304/03_Risk_Management_File.md` | 46 | `b39c839` | 2026-10-17 | #47 |
| 13 | `docs/iec62304/04_Software_Architecture_Design.md` | 18 | `880a065` | 2026-10-17 | #43 |
| 14 | `docs/iec62304/05_Traceability_Matrix.md` | 10 | `880a065` | 2026-10-17 | #43 |
| 15 | `docs/iec62304/05_Traceability_Matrix.md` | 11 | `31940b6` | 2026-10-17 | #46 |
| 16 | `docs/iec62304/05_Traceability_Matrix.md` | 12 | `b39c839` | 2026-10-17 | #47 |
| 17 | `docs/iec62304/06_Detailed_Design_Specification.md` | 13 | `880a065` | 2026-10-17 | #43 |
| 18 | `docs/iec62304/09_SOUP_Bill_of_Materials.md` | 10 | `880a065` | 2026-10-17 | #43 |
| 19 | `docs/iec62304/10_Verification_Validation_Plan.md` | 14 | `880a065` | 2026-10-17 | #43 |
| 20 | `docs/iec62304/records/capa/CAPA-006_MAGNIMS_Labelling_And_Atlas_Space.md` | 9 | `880a065` | 2026-10-17 | #43 |
| 21 | `docs/iec62304/records/capa/CAPA-007_Analysis_Routes_Without_Object_Authorization.md` | 9 | `bae1a7f` | 2026-10-17 | #45 |
| 22 | `docs/iec62304/records/capa/CAPA-008_AI_Assistant_Layer_And_Clinical_Rule_Fidelity.md` | 9 | `31940b6` | 2026-10-17 | #46 |
| 23 | `docs/iec62304/records/capa/CAPA-009_Object_Authorization_Across_All_Routers.md` | 9 | `b39c839` | 2026-10-17 | #47 |
| 24 | `docs/iec62304/records/capa_register.md` | 23 | `880a065` | 2026-10-17 | #43 |
| 25 | `docs/iec62304/records/capa_register.md` | 24 | `bae1a7f` | 2026-10-17 | #45 |
| 26 | `docs/iec62304/records/capa_register.md` | 25 | `b39c839` | 2026-10-17 | #46 (transcribed in the PR #47 merge) |
| 27 | `docs/iec62304/records/capa_register.md` | 26 | `b39c839` | 2026-10-17 | #47 |
| 28 | `docs/iec62304/records/risk_verification/rc_test_manifest.json` | 306 | `bae1a7f` | 2026-10-17 | #45 |
| 29 | `docs/mdr/GSPR-001_General_Safety_Performance_Requirements.md` | 11 | `880a065` | 2026-10-17 | #43 |
| 30 | `docs/mdr/IFU-001_Instructions_For_Use.md` | 12 | `880a065` | 2026-10-17 | #43 |
| 31 | `docs/usability/UEF-001_Usability_Engineering_File.md` | 12 | `880a065` | 2026-10-17 | #43 |

## 7. Verification Evidence for This Record (2026-10-22, read-only)

- **Approval lines.** `git grep -n -i -E "<owner name>.{0,80}approv|approv.{0,80}<owner name>" 6209131 -- docs/iec62304/ docs/mdr/ docs/qms/ docs/clinical/ docs/ai-act/ docs/usability/` → **31 lines in 19 files**, identical to paper H. `git blame` spot checks: SRS lines 19–22 → `9102200`, `880a065`, `31940b6`, `b39c839`; register lines 23–26 → `880a065`, `bae1a7f`, `b39c839`, `b39c839`; manifest line 306 → `bae1a7f`. The five commits: author and committer `nicolasbonilla`, trailer `Co-Authored-By: Claude Opus 5.5 (1M context)`.
- **Signatures.** `git log --format="%G? %cn" 6209131`: 344 commits unsigned (committer `nicolasbonilla`), 44 signed by GitHub's own key (committer `GitHub`, web merges). None is signed by a key of the owner.
- **Branch protection.** `gh api repos/nicolasbonilla/medical-imaging-viewer/branches/main/protection` → HTTP 404 "Branch not protected"; `gh api …/rulesets` → `[]`.
- **CODEOWNERS.** `.github/CODEOWNERS` read: `@nicolasbonilla` for the eight Class C modules and `docs/iec62304/`, `docs/qms/`, `docs/clinical/`.
- **Reviews and merges.** Taken from paper H (`github_prs_snapshot.json`, 2026-10-21); not re-queried.
- **Not verified:** the chat approvals themselves (outside the repository); the harness refusals (operator notes, not reproducible from the repository).

## 8. Regulatory Assessment

- The device is not CE-marked and not in clinical use; there is no vigilance reporting obligation.
- Before any Declaration of Conformity or regulatory submission, CA-12.1 to CA-12.5 must be in force: an auditor would see design-review and approval records for Class C changes written by the development tool, with no independent reviewer. The historical records stay readable as agent-transcribed approvals (§6), not as owner-executed records.

---

**Prepared by**: internal audit (drafted by the AI coding agent, Claude Code), 2026-10-22.
**Approval**: PENDING owner approval — no approval is recorded here, and none may be added by the agent (CA-12.1).
