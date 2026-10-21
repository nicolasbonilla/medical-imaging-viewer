# Paper H — Study Protocol

**An AI coding agent as primary developer of IEC 62304 Class C software: a single-case study of verification failures and how they were caught**

| | |
|---|---|
| Protocol version | 1.0 (2026-10-21) |
| Study type | Exploratory, retrospective, single-case case study (Runeson & Höst 2009; Yin 2018), mining the project's own repository and records |
| Target venues | Empirical Software Engineering (EMSE), primary; Journal of Systems and Software (JSS), alternative |
| Case | MSTool-AI (`nicolasbonilla/medical-imaging-viewer`), investigational brain-MRI software for multiple sclerosis, developed under IEC 62304:2006+A1:2015 **Class C** |
| Owner / author | N. G. Bonilla Vargas (holds every approval authority; the agent holds none, SDP-001 v1.1 §4.4) |
| Analysis code | `research/paper_h/` (written by the agent; see Threats) |
| Branch | `research/paper-h-case-study` (from `origin/main` `6209131`) |

## 0. Status of this protocol (honest disclosure)

This protocol is committed **before** the analysis scripts and before any number in
`RESULTS.md` is produced, and the metrics below are fixed here. It is **not** a blind
pre-registration: before writing it, the agent read the CAPA records, the verification
summaries, the negative-control records and PR descriptions, and ran exploratory `git log`
counts (for example, the 327 / 388 trailer count already stated in SDP-001 v1.1, PR #49).
Any metric added after this commit will be labelled **post hoc** in `RESULTS.md`.

## 1. Claim under study

Narrow, defensible claim to be tested against the evidence and the literature:

> To our knowledge, this is the first documented case of an AI coding agent acting as the
> **primary developer** of software under a formal **IEC 62304 Class C** lifecycle — code,
> tests, lifecycle documents, risk-management and CAPA records — under a single human owner
> who holds all approval authority, with **quantified** verification failures and an account of
> how each was caught.

Not claimed: that the device is safe, that the process is compliant, that the agent is
better or worse than human developers, or that the findings generalise.

## 2. Research questions

- **RQ1 — Extent.** How much of the code base and of the lifecycle records was produced by
  the agent?
- **RQ2 — Failures.** Which verification failures occurred, of which kinds; which commits
  introduced the defective evidence; what detected each failure (which channel, which actor);
  and how long did each persist?
- **RQ3 — Evidence.** How did the risk-control verification evidence change once controls
  had to be bound to behaviour-observing tests challenged by deliberate mutations (negative
  controls)? How often did those negative controls themselves fail?
- **RQ4 — Governance.** How was the human-approval boundary operated, and what evidence of
  it exists in the repository and on GitHub?

## 3. Data sources (all read-only)

| ID | Source | Pinned at |
|---|---|---|
| D1 | Git history of `origin/main` | `6209131f5b8b20f77a12bf5799f43dc73dad3ece` (2026-10-17) |
| D2 | Open PR branches holding later records | CAPA-010, PR #52: `8b839fd0518bb56b69d41344fa83b508680b893c`; CAPA-011, PR #51: `86f19f2e1744c39774d2f7960d07c5e1dd657f3d`; in-browser FLAMeS, PR #53: `7cce845960c91d7f5da8c2301081c4e87a451aaa`; SDP-001 v1.1, PR #49: `4dcf1ff528373287439b17766ea2ac0f8c5484ba` |
| D3 | CAPA records CAPA-001 … CAPA-011, the CAPA register | `docs/iec62304/records/capa/`, at D1/D2 |
| D4 | Risk-control verification summaries (withdrawn 2026-04-12; 2026-07-18) | `docs/iec62304/records/risk_verification/` |
| D5 | Risk-control → test manifest | `rc_test_manifest.json` at D1/D2 |
| D6 | Negative-control (mutation) records | `*_negative_controls_*.json` at D1/D2 |
| D7 | GitHub PR metadata (state, draft flag, formal reviews, merger, body flags) | read-only `gh` snapshot, committed to `research/paper_h/data/` with its retrieval date |
| D8 | Operator notes on the permission boundary | the agent's persistent memory notes (not in the repository) — **qualitative only**, reported as such |

Not used: patient data, production data stores, production logs, cloud consoles, secrets.
No cloud command is run. Personal data: the owner's name only; no e-mail addresses appear in
any output.

## 4. Operational definitions

- **Agent-trailered commit**: a commit whose message carries a `Co-Authored-By:` trailer
  whose value names Claude (`noreply@anthropic.com`). This is a **lower bound** on agent
  involvement (a commit without the trailer is not evidence of human authorship), and the
  model string in the trailer is self-reported.
- **Controlled document**: any file under `docs/iec62304/`, `docs/mdr/`, `docs/qms/`,
  `docs/clinical/`, `docs/ai-act/`, `docs/usability/`.
- **Class C module**: the eight files listed in `CLAUDE.md`.
- **Verification-failure episode (unit of RQ2)**: a documented instance in which
  (a) recorded verification evidence asserted or implied a property the system did not have,
  or (b) an executed check could not observe the failure it was meant to detect, or
  (c) a negative control (a check of a check) was itself invalid or missed a mutation, or
  (d) an agent-drafted record contained a false statement of fact about the system or its
  history. Each episode must be traceable to a quoted passage in a record (D3–D6) or a
  commit message.
- **Failure classes** (a priori, from the records' own root-cause statements):
  - **P** prose / self-attested verification, never executed;
  - **N** test or check that never executed or could never fail;
  - **S** check at the wrong locus — source text, call site, definition site, a single file,
    or the decision function instead of the running system;
  - **I** check whose environment could not observe the failure — mocks, jsdom (no layout),
    symmetric fixtures (square or cubic), halves of a round trip tested alone, local
    credentials absent in CI;
  - **M** negative control invalid or blind (mutation not applied, test looking at the wrong
    object, mutation surviving);
  - **R** false or overstated statement in an agent-drafted record;
  - **C** clinical or labelling content not traced to its source (written from memory or not
    bound to the code).
- **Detection channel**: AR adversarial review by separate agent sessions (pre-merge review,
  re-verification); BP behaviour probe written during another task (request probe,
  real-browser probe, round-trip test); SA static analysis sweep; CI continuous integration
  run; IM noticed while implementing a related action; EX external research
  (publication or literature work); OW the human owner.
- **Time to detection**: calendar days from the author date of the introducing commit to the
  author date of the commit that first records the failure.
- **Negative control detected**: at least one bound test failed (or errored) with the mutation
  applied, and the record states the mutation was applied. Mutations declared in the record
  as equivalent or redundant by design are reported separately, not as detected.

## 5. Metrics

**RQ1**
1. Commits on D1 with / without the trailer: all commits, non-merge commits, per calendar
   month (author date).
2. Distribution of trailer model strings.
3. Lines added and deleted (`git log --numstat`, non-merge, text files) by trailer status.
4. Commits touching controlled documents; commits touching Class C modules; trailer share of
   each.
5. Authorship (trailer) of the withdrawn verification summary RCV-SUMMARY-2026-04-12.

**RQ2**
6. Number of episodes by class and by detection channel.
7. Share of episodes whose introducing commit is agent-trailered; share whose detecting
   commit is agent-trailered; number detected by the owner.
8. Time to detection: per episode, median and range (only where both commits are known).

**RQ3**
9. Risk-control verification headline before and after adversarial re-verification
   (RCV-SUMMARY 2026-04-12 vs 2026-07-18).
10. Manifest status distribution at D1 and at each D2 head; number of controls recorded
    `implemented` whose note carries an **ERRATUM** (verified, then found ineffective).
11. Negative controls per record and pooled: mutations, detected, declared
    equivalent/redundant, unexpected undetected, restored suite green.
12. Tests written after a defect, run against the pre-fix code (where recorded): failures /
    total. Pre-fix tests run against post-fix mutations (where recorded): detections / total.

**RQ4**
13. Formal GitHub reviews per PR (all PRs); merger account; merge commits made through
    GitHub vs locally (committer identity, without e-mail).
14. Commits that record a human approval in controlled documents, and their trailer status.
15. Open PRs whose description states that owner approval is pending.
16. Qualitative: harness permission decisions at the approval boundary (D8).

No inferential statistics: there is one case, and the mutations are designed, not sampled,
so confidence intervals would suggest a population that does not exist. Counts and
proportions are reported with their denominators.

## 6. Procedure

1. Scripts in `research/paper_h/` compute every metric from D1–D7 and write
   `research/paper_h/out/results.json`. Each number in `RESULTS.md` names the command that
   produces it.
2. RQ2 coding is a manual coding sheet (`research/paper_h/data/failure_coding.json`):
   for each episode, the class, the channel, the introducing and detecting commits, and at
   least one verbatim quote with its file and git ref. A script checks that **every quote
   occurs verbatim** (whitespace-normalised) in the cited file at the cited ref and that every
   cited commit exists; the test suite fails otherwise.
3. Unit tests (`research/paper_h/tests/`) cover the parsers on synthetic inputs, and a
   reproduction test re-derives the headline numbers from the pinned refs.
4. The manuscript draft cites only numbers present in `RESULTS.md`.

## 7. Threats to validity (planned mitigations)

- **Single case** — no generalisation claimed; analytical, not statistical, generalisation.
- **The author is the agent's operator** and the approver of the changes studied — conflict of
  interest declared; every number is re-derivable by a third party from public data.
- **The analysis and the coding were done by the agent being studied** — mitigated by verbatim
  quote checks, pinned refs and tests; an independent second coder (human) is required before
  submission (inter-rater agreement to be reported).
- **The records were written by the agent** — they may overstate or understate; triangulated
  with git history (dates, trailers) and executed tests; self-reported counts in records are
  labelled as such.
- **Trailer as proxy** — a lower bound; model strings self-reported.
- **Model versions changed over time** (several Claude model strings) — reported, not
  controlled.
- **"Independent" reviewers are agent sessions** (SDP-001 v1.1 §4.4 states the limitation) —
  stated wherever a review is counted.
- **Branch records may change** (open PRs) — SHAs pinned; GitHub keeps `refs/pull/N/head`.

## 8. Novelty re-check

A focused literature search is re-run and logged in `RESULTS.md` §0 before the manuscript is
drafted. Known neighbours to position against: Ferris & Bonilla, arXiv 2610.08651 (Claude
Code, healthcare platform, not a device); Wang et al., JACMP 2026 (Claude Code, clinical
in-house tool, not a device). Conflict-of-interest checks concerning cited authors are handled by
the owner outside this public document (amendment 1).

## Amendments

1. 2026-10-21, after the analysis: one sentence of §8 about a conflict-of-interest check concerning a
   cited author was removed from this public document; the check is handled privately by the owner.
   No research question, data source, definition or metric changed.

## 9. Ethics

No human-subject data, no patient data, no production data, no secrets; the only personal
datum is the owner's name as author. The study uses the project's own engineering records.
