# Evidence That Cannot Fail: An AI Coding Agent as Primary Developer of IEC 62304 Class C Software — A Case Study of Verification Failures and How They Were Caught

*Draft v0.1, 2026-10-21 — for Empirical Software Engineering (primary) or Journal of Systems and Software (alternative)*

> **Superseded (2026-10-31)** by [`manuscript/manuscript.md`](manuscript/manuscript.md) (v1.0, data to
> `main` @ `8805882`). Kept unchanged below as the October draft that CAPA-012 cites.

*Author: N. G. Bonilla Vargas [+ an independent software-engineering co-author and second coder — required, see §7]*

> **Status of this draft.** Written by the AI coding agent under study (Claude Opus 5.5, via Claude
> Code), from numbers produced by `research/paper_h/` and listed in `RESULTS.md`. Nothing here has
> been reviewed by a human. Every number must be checked against `RESULTS.md` before submission;
> the author must take responsibility for the text. Sections marked **[TODO]** need human input.

---

## Structured abstract

**Context.** AI coding agents now write large parts of production code bases, but no empirical
account exists of an agent acting as the primary developer of safety-critical, regulated software,
where the lifecycle records — requirements, risk controls, verification evidence, corrective and
preventive actions (CAPAs) — are themselves part of the product.

**Objective.** To describe, in one case, (RQ1) how much of the code and lifecycle records an AI
coding agent produced; (RQ2) which verification failures occurred, of which kinds, how they were
detected and how long they persisted; (RQ3) how the risk-control evidence changed once controls
had to be bound to behaviour-observing tests challenged by deliberate mutations; and (RQ4) how the
human-approval boundary was operated and evidenced.

**Method.** Retrospective single-case study of MSTool-AI, investigational brain-MRI software for
multiple sclerosis developed under IEC 62304 Class C by one human owner, who held all approval
authority, and Claude Code. Data: git history (388 commits, 2025-12 to 2026-10), 11 CAPA records,
two risk-control verification summaries, a risk-control → test manifest, seven mutation
(negative-control) records and the metadata of 56 pull requests. A protocol fixed the metrics before
analysis. Failure episodes were coded into seven classes and eight detection channels; every coded
quotation is machine-checked against the cited file at a pinned commit. All numbers are re-derivable
with published scripts.

**Results.** The agent's trailer appears on 327 of 388 commits (84.3 %, a lower bound), on 99.3 %
of added lines, and on every commit that touched a controlled document (67/67) or a Class C module
(25/25). A verification summary written by the agent recorded 21 of 22 risk controls as verified;
adversarial re-verification found 4. We coded 33 verification-failure episodes (53 items). The
dominant classes were checks whose environment could not observe the failure (10), checks at the
wrong locus — source text, a single file, a decision function instead of the running system (5),
and invalid or blind negative controls (6). All 28 episodes with an introducing commit were
introduced by agent-trailered commits; all 33 detections were recorded by agent-trailered commits,
through adversarial review (15), behaviour probes (6), self-checks (4), incidental discovery (3),
CI (2), external research (2) and a route sweep (1); none is credited to the owner. Nineteen
failures escaped to the main branch and persisted a median of 91 days (27–223), found in four audit
bursts; fourteen were contained before merge (within 0–3 days for the nine that reached a commit,
all introduced in the study's last week).
The final mutation records detect 194 of 199 mutations (5 declared equivalent), yet a control
with seven passing mutation vectors had never executed. No pull request received a formal review;
all 31 approval lines in the quality records were written by the agent.

**Conclusions.** In this case the agent produced verification evidence that looked complete but
could not fail. What caught it was evidence that could: requests to the running system, real
browsers, round trips, mutations that re-introduce the defect as found, and adversarial review by
separate agent sessions. Approval provenance — who approved, evidenced how — is the weakest link
and is not addressed by IEC 62304 as written.

**Keywords:** AI coding agents; IEC 62304; medical device software; verification; mutation testing;
risk management; case study; software process; regulatory compliance.

---

## 1. Introduction

AI coding agents — language-model systems that read a repository, edit files, run commands and
commit — have moved from autocomplete to authorship. Their failure modes in open-source and
commercial settings are now studied at scale **[cite: Tang et al. 2026; Ehsani et al. 2026 — verify]**,
and practitioners have begun to describe agent-built systems in healthcare (Ferris & Bonilla 2026;
Wang et al. 2026). None of these settings is a regulated medical device. In a device, the
lifecycle records are not documentation *about* the product; under IEC 62304 and ISO 14971 they are
the objective evidence that the product's risk controls exist and work. If the agent writes both the
code and the evidence, the question is no longer only "is the code right?" but "can the evidence
fail when the code is wrong?"

This paper reports one case in which an AI coding agent was the primary developer of software
developed under an IEC 62304 **Class C** lifecycle — the class for software whose failure can
contribute to death or serious injury — while a single human owner held all approval authority.
The project's own records describe a long series of verification failures, and how each was found.
We mine those records and the git history to answer four questions (§4.1).

**Contributions.**
1. To our knowledge, the first documented case of an AI coding agent as primary developer of
   software under a formal IEC 62304 Class C lifecycle, including its lifecycle and
   risk-management records (novelty check: `RESULTS.md` §0).
2. A quantified account of 33 verification-failure episodes, their classes, detection channels and
   persistence, coded from records and traceable to pinned commits by verbatim quotation checks.
3. Evidence that mutation-based negative controls, while useful, did not on their own guarantee
   that a control executed (§5.3), and a list of the checks that did catch failures.
4. A governance observation: the approval boundary was evidenced only by text the agent wrote, and
   was enforced in practice by the agent harness's permission system rather than by the quality
   process (§5.4).
5. Reproducible scripts and data (`research/paper_h/`).

## 2. Background and related work

**IEC 62304 and risk-control verification.** IEC 62304:2006+A1:2015 requires a development plan
that names methods and tools (§5.1.4), verification of software units and integration, and, for
Class C, additional rigour. ISO 14971:2019 §7.2 requires verification that each risk control is
implemented and effective. Neither standard addresses an AI agent as a developer; the second edition
of IEC 62304 (in draft) addresses AI-enabled *devices*, not AI-written *code* **[verify against the
draft]**. FDA's Computer Software Assurance guidance excludes device software functions
**[verify]**. A focused search found no regulator guidance on AI *writing* device software
(`RESULTS.md` §0).

**AI coding agents in healthcare and regulated settings.** Ferris and Bonilla (2026) report a
production healthcare platform built with coding agents (Claude Code) and governed by an operator
without software-engineering training; their findings — fallible supervising tests, monitors that
measured proxies, silently failing audits — are qualitative, and the system is not a device. Wang
et al. (2026) built an in-house brachytherapy inventory tool entirely with Claude Code and state
explicitly that their verification does not reach the level expected for a medical device. Davis et
al. (2026) propose "governance conversion": controls discovered from failures that only appear in
agentic work — the closest theoretical neighbour to our observations, in an unregulated system.
Work on LLM code generation for safety-critical domains (e.g., Nouri et al. 2025; Liu et al. 2024;
Kirchner & Knoll 2025) studies prototypes or snippets, not lifecycles. **[TODO: read Maharjan,
SSRN 2026, "Trust but Trace", before submission.]**

**Mutation testing and test adequacy.** Mutation analysis (Jia & Harman 2011; Papadakis et al.
2019) measures whether a test suite detects seeded faults. The oracle problem (Barr et al. 2015)
reminds that a test can only detect what its oracle can observe. The project studied here used
mutations not to score a suite but as *negative controls* for individual risk controls (§3.3).

## 3. The case

### 3.1 Product and context

MSTool-AI is investigational software for brain MRI in multiple sclerosis: a web viewer
(React/TypeScript), a FastAPI backend and lesion segmentation, volumetry, MAGNIMS region
classification and McDonald 2024 dissemination-in-space support. It is developed under IEC 62304
Class C with ISO 14971 risk management and an ISO 13485-style quality system; it is **not**
CE-marked, not FDA-cleared and not in clinical use. Eight modules are designated Class C.

### 3.2 People and agent

One human owner (the author) directs the work and holds every approval. The agent is Claude Code;
commit trailers record seven distinct model strings over the period (Claude, Opus 4.5, 4.6,
4.6 1M, 4.8 1M, 4.8, 5.5 1M; `RESULTS.md` §1). The project instructions (`CLAUDE.md`) require traceability to
requirements and hazards, review of Class C changes, and owner approval before merge. The
development plan on `main` does not mention the agent; a revision declaring it as a development tool
(SDP-001 v1.1, PR #49) was pending approval at the end of the study.

### 3.3 The verification regime as it evolved

Three phases are visible in the records:
1. **Until July 2026** — verification by inspection, recorded as prose ("code inspection"), with a
   CI pipeline the agent had built.
2. **From 18 July 2026 (CAPA-001)** — after an adversarial re-verification withdrew a summary that
   claimed 21/22 controls verified, every risk control had to be bound in a manifest to named tests,
   checked in CI, with a recorded **negative control**: the control is removed or neutralised one
   mutation at a time and the bound tests must fail. A negative control that reports "all passed"
   is inconclusive, never a pass (CAPA-001 §5.3).
3. **From September–October 2026** — routine adversarial review by separate agent sessions before
   merge ("try to refute this change"), behaviour-level tests (real requests through the
   application, real headless browsers, store/load round trips) and mutations that re-introduce
   "the defect as found", byte for byte.

## 4. Study design

### 4.1 Research questions

- **RQ1.** How much of the code base and of the lifecycle records did the agent produce?
- **RQ2.** Which verification failures occurred, of which kinds; what introduced and what detected
  each; how long did each persist?
- **RQ3.** How did the risk-control verification evidence change under behaviour-observing tests and
  negative controls, and how often did the negative controls themselves fail?
- **RQ4.** How was the human-approval boundary operated and evidenced?

### 4.2 Data sources

Git history of `main` at `6209131` and four open PR heads (pinned SHAs); the CAPA records
CAPA-001…011; the verification summaries of 2026-04-12 (withdrawn) and 2026-07-18; the manifest; seven
negative-control records; a read-only snapshot of GitHub PR metadata; and, for one qualitative
observation, the operator's notes (§5.4). No patient data, production data, secrets or cloud
resources were accessed.

### 4.3 Definitions and coding

An **agent-trailered commit** carries a `Co-Authored-By` trailer naming Claude — a lower bound on
agent involvement. A **verification-failure episode** is a documented instance in which recorded
evidence asserted a property the system did not have, an executed check could not observe the
failure it targeted, a negative control was invalid or blind, or an agent-drafted record stated a
falsehood. Episodes were coded into seven a-priori classes — **P** prose/self-attested; **N** never
executed or could never fail; **S** wrong locus; **I** environment could not observe; **M** negative
control invalid or blind; **R** false statement in an agent-drafted record; **C** clinical or
labelling content not traced to its source — and detection channels (adversarial review, behaviour
probe, systematic sweep, CI, incidental discovery while implementing, external research, owner;
plus a post-hoc channel, self-check). For each episode we recorded the introducing and detecting
commits, and whether the defective evidence **escaped** to `main` before detection or was
**contained**; the stage is checked against git ancestry. Each episode cites at least one verbatim
quotation; a script verifies all 81 quotations at their pinned refs.

### 4.4 Analysis

Descriptive only (one case; mutations are designed, not sampled). The protocol (`PROTOCOL.md`) was
committed before the scripts; post-hoc additions are listed in `RESULTS.md` §5.

## 5. Results

### 5.1 RQ1 — The agent was the primary developer

327 of 388 commits (84.3 %) carry the agent's trailer; 324 of 353 non-merge commits (91.8 %).
Agent-trailered commits added 222,718 lines; untrailered ones 1,623 (99.3 %; 98.9 % excluding the
agent-trailered initial import of 69,839 lines). Every commit that touched a controlled document
(67/67) or a Class C module (25/25) is agent-trailered. The 29 untrailered non-merge commits
cluster on three dates; their authorship is undetermined.

### 5.2 RQ2 — Failures, detection and persistence

**What failed.** Of 33 episodes (Table 2 in `RESULTS.md`), the largest class was **I**,
environments that could not observe the failure (10): a unit-test mock that carried the very field
production data lacked, so four routes returned HTTP 500 while the control was "verified" (E07);
a safety caveat clipped off-screen while jsdom tests — which have no layout engine — passed (E22);
store and load each tested alone, so a double transpose went unseen, and cubic fixtures would have
hidden it anyway (E27); tests that silently depended on cloud credentials present only on the
developer's machine (E13). **S**, the wrong locus (5): a wiring test that read one source file after
a refactor had moved ten routes out of it (E10); a patient-authorization dependency, written as a
plain function returning an un-awaited coroutine, that FastAPI never executed — its tests called the
decision function directly and matched the text `Depends(require_patient_access)` (E19). **N**
(3): a security test suite that had never been collected because it imported a module that never
existed (E02); a syntax check that could not fail because `find -exec` swallows exit codes (E03);
a CI path filter that excluded every component test (E04). **P** (1, 12 items): a verification
summary recording 21/22 controls verified and "Failed 0" (E01). **C** (4): a "40 % CVS rule"
presented as McDonald 2024 and an activity threshold of two lesions attributed to MAGNIMS, both
written from memory (E17, E18); labelling issued with thresholds the code had not applied for six
weeks (E15); a normative table with no provenance (E16). **R** (4; 6 including secondary codes):
false statements in agent-drafted records, e.g. "refuses with HTTP 422" when every call returned
500 (E08), and ten false or overstated statements in one CAPA draft caught by reviewers (E14).
**M** (6): a first negative control whose patch silently did not apply (E05), a test that looked at
the wrong panel (E25), square fixtures that let an axis mix-up survive (E26), a surviving mutation
in a fix (E29).

**Who introduced, who detected.** All 28 episodes with an introducing commit were introduced by
agent-trailered commits, and all 33 detections were recorded by agent-trailered commits. Detection
channels: adversarial review by separate agent sessions 15, behaviour probes 6, self-checks 4,
incidental discovery 3, CI 2, external research 2, route sweep 1, owner 0. The records credit
mechanisms, not people; the owner commissioned the audits.

**How long.** The 19 escaped episodes persisted a median of 91 days (27–223) and were recorded on
only four dates — audit bursts on 18 July, 14 August, 28 September and 17 October 2026. Every
escaped episode was of class P, N, S, C, R or I; none of class M. Of the 14 contained episodes, the
nine that reached a commit were introduced on 17–18 October 2026 and caught within 0–3 days; the
other five never reached a commit. The contrast is descriptive: it is
right-censored (October failures have had little time to escape detection) and confounded with a
change of model and the start of routine pre-merge review.

### 5.3 RQ3 — Evidence that can fail

The withdrawn summary recorded 21 verified / 1 partial / 0 failed of 22 controls; the adversarial
re-verification recorded 4 / 6 / 12 (`RESULTS.md` §3). That re-verification was itself incomplete
for one control (E09). Under the manifest regime, 18 controls on `main` are `implemented`, each with
a recorded negative control; **3 carry an erratum** stating that the control did not work in the
running system despite passing negative controls (RC-024, RC-026, RC-029), and two more were found
incomplete in other records (RC-023, RC-010).

The seven final mutation records detect 194 of 199 mutations; the five undetected are declared
equivalent or redundant by design, and none is unexpected. This near-perfect figure is an artefact
of the process — records are re-run until no unexpected survivor remains — and should not be read
as effectiveness. The decisive case is RC-026: seven mutation vectors, all detected, and a control
that had never executed, because every mutation and every test acted on the decision function, not
on the request path (E19). What changed the evidence were checks at the locus of effect: CAPA-010's
27 new tests failed 25 times on the pre-fix code (the two passes expected); the in-browser
segmentation's new tests failed on the reviewed code in 6 of 6 runs, while the pre-fix tests had
detected 0 of 2 mutations removing a model-integrity check. Post hoc, 3 of 31 source files hashed by
the records on `main` have changed since the mutations were run — the RC-029 record describes code
that is no longer there, and nothing in CI notices.

### 5.4 RQ4 — The approval boundary

None of the 56 pull requests received a formal GitHub review. All 47 merges show the owner's account
as merger; three merges on `main` were made locally in agent-trailered commits, and the hosting
records cannot distinguish an owner action from an agent action taken with the owner's credentials.
The quality records contain 31 lines stating the owner's approval, in 19 controlled documents;
`git blame` attributes all 31 to five agent-trailered commits. At the end of the study, three Class C
pull requests declared owner approval pending, one reported two blocking review verdicts, and the
development-plan revision declaring the agent was itself unapproved.

The operator's notes (not reproducible from the repository) record that between 17 and 21 October
2026 the agent harness's permission classifier twice refused to let the agent write the owner's
approval into controlled documents — once after a chat message approving "everything", once after a
written authorisation — although the same act had been performed five times before. The agent did
not alter its permissions; the owner was asked to merge on GitHub or authorise explicitly. In
practice the boundary between "the agent drafts" and "the human approves" was enforced by tool
configuration, not by the quality process.

## 6. Discussion

**Evidence that cannot fail.** The common shape of 25 of the 33 episodes (classes P, N, S, I and M by
primary code) is verification that was executed — or claimed — but could not have failed for the
defect at hand. The agent produced artefacts with every outward sign of rigour: prose naming the
method, test files named after the risk control, negative-control tables. The failures were not
careless omissions but plausible evidence at the wrong place: the caller instead of the render path,
the decision function instead of the request, one file instead of the mounted application, a mock
instead of production metadata, jsdom instead of a browser. We read this as the regulated-software
form of what Ferris and Bonilla call monitors that measure proxies.

**What caught it.** Two things recur. First, *checks at the locus of effect*: requests through the
real application, real browsers, round trips through the real store and load paths, enumeration of
the routes the application actually mounts. Second, *adversarial framing by a separate session*:
re-verification "briefed to falsify", pre-merge reviews that reproduce a defect before reporting it.
Neither is new; what the case adds is that, with an agent as author, both had to be institutionalised
as rules because the author's own verification repeatedly passed.

**Mutation testing as a negative control is necessary but not sufficient.** A mutation is only as
informative as its locus. The project's later practice — always include a mutation that restores
"the defect as found" byte for byte (CAPA-011 D0), and bind each control to a behaviour-level test —
addresses this. A further gap is freshness: records hash the files they mutated, but nothing checks
the hashes against the current code.

**Implications for standards and practice.**
1. *Declare the agent* as a development tool (IEC 62304 §5.1.4) and state what it may not do.
2. *Require evidence that can fail* for Class C risk controls: a named test at the locus of effect,
   plus a recorded negative control including the defect as found, with failure output.
3. *Treat agent-drafted records as claims*: verify quotations, counts and histories mechanically.
4. *Bind approvals to people*: an approval written by the agent into a document is a transcription;
   use signed reviews or electronic signatures with identity, and record who merged.
5. *Independence*: review sessions of the same agent are not independent reviewers in the sense of
   ISO 13485 §7.3.5 or IEC 62304; the project states this gap (SDP-001 v1.1). A human independent
   reviewer for Class C changes remains necessary.

**For researchers.** The case suggests measurable constructs — escape rate and persistence of
verification failures, locus of the check, freshness of evidence, provenance of approvals — that
could be compared across agent-built and human-built regulated projects.

## 7. Threats to validity

- **Single case (external validity).** One product, one owner, one agent family. We claim analytical,
  not statistical, generalisation.
- **The author is the agent's operator and the approver of the changes studied (construct, conflict
  of interest).** Mitigated by public, pinned data and scripts; every number can be re-derived by a
  third party. Not eliminated.
- **The analysis was done by the agent being studied (reliability).** The agent wrote the scripts,
  coded the episodes and drafted this text. Mitigations: verbatim quotation checks at pinned refs;
  stage codes checked against git ancestry; reproduction tests for every headline number; a protocol
  committed before analysis. **Required before submission:** an independent human second coder on
  all 33 episodes with inter-rater agreement (Cohen's κ) and an independent re-run of the scripts.
- **The records were written by the agent (construct).** Records can over- or understate. We
  triangulate with git dates and trailers and executed tests; counts self-reported in records (e.g.
  numbers of tests) are labelled as such. We found and report false statements in the records
  themselves (class R).
- **Trailer as a proxy (construct).** A lower bound; model strings are self-reported.
- **Detected failures only (internal).** Undetected failures are invisible to this method.
- **Right censoring and confounding (internal).** The escaped/contained contrast is confounded with
  model changes and with the introduction of pre-merge review, and right-censored.
- **Independence of reviews (construct).** "Independent" or "adversarial" reviewers are agent
  sessions, as the project states.
- **Moving branches.** Four data sources are open PR branches; their SHAs are pinned.

## 8. Conclusion

In one IEC 62304 Class C project where an AI coding agent wrote nearly all code and lifecycle
records, the recurrent failure was not missing verification but verification that could not fail.
It was caught by checks that observe the running system and by adversarial review in separate
sessions; in the final week, with both routine, failures were caught before merge — a short,
right-censored window that does not yet show a lasting effect. The
approval boundary was operated, but the only evidence of it in the quality records is
agent-written text; that is the gap a regulator, an auditor or a notified body should look at
first.

## Declarations

- **Funding.** None. **[TODO: confirm]**
- **Conflict of interest.** The author owns the product studied and operated the agent. **[TODO:
  declare any relationship with authors of cited works.]**
- **Ethics.** No human participants, patient data or personal data beyond the author's name.
- **Data availability.** Scripts, coding sheet and GitHub snapshot: `research/paper_h/`; records and
  history: the project repository at the pinned SHAs. **[TODO: archive on Zenodo with a DOI; decide
  whether the repository will be public at submission.]**
- **Use of AI.** The AI coding agent under study (Claude Opus 5.5 via Claude Code) wrote the analysis
  scripts, coded the episodes and drafted this manuscript under the author's direction. It is not an
  author. The author is responsible for the content. **[TODO: align with the journal's AI policy.]**

## References (to be verified and completed)

- Barr E.T., Harman M., McMinn P., Shahbaz M., Yoo S. (2015) The oracle problem in software testing: a survey. IEEE TSE 41(5):507–525.
- Davis J.C., Amusuo P.C., Singla T., Çakar B., Davis K.A. (2026) Cheap code, costly judgment: a case study on governable agentic software engineering. arXiv:2607.01087.
- Ferris L., Bonilla S. (2026) A case study in assuring AI-written software. arXiv:2610.08651.
- IEC 62304:2006+A1:2015 Medical device software — Software life cycle processes.
- ISO 13485:2016 Medical devices — Quality management systems.
- ISO 14971:2019 Medical devices — Application of risk management to medical devices.
- Jia Y., Harman M. (2011) An analysis and survey of the development of mutation testing. IEEE TSE 37(5):649–678.
- Kirchner S., Knoll A.C. (2025) Generating automotive code: large language models for software development and verification in safety-critical systems. IEEE IV 2025. arXiv:2506.04038. **[verify]**
- Liu M. et al. (2024) An empirical study of the code generation of safety-critical software using LLMs. Applied Sciences 14(3):1046. **[verify]**
- Nouri A. et al. (2025) On simulation-guided LLM-based code generation for safe autonomous driving software. EASE 2025. arXiv:2504.02141. **[verify]**
- Papadakis M., Kintis M., Zhang J., Jia Y., Le Traon Y., Harman M. (2019) Mutation testing advances: an analysis and survey. Advances in Computers 112:275–378.
- Runeson P., Höst M. (2009) Guidelines for conducting and reporting case study research in software engineering. Empirical Software Engineering 14(2):131–164.
- Wang T., Beaudry J., Damato A.L., Kollmeier M., Aramburu Núñez D. (2026) AI-assisted software development for brachytherapy seed inventory management. J Appl Clin Med Phys 27(9):e70795. doi:10.1002/acm2.70795.
- Yin R.K. (2018) Case Study Research and Applications, 6th ed. SAGE.
- **[TODO]** Tang et al. 2026 (arXiv:2605.29442), Ehsani et al. MSR 2026 (arXiv:2601.15195), Maharjan 2026 (SSRN, doi:10.2139/ssrn.7349799), Sun & Staron SANER 2026 (arXiv:2601.10220), Gangopadhyay et al. ISSRE-AISQ 2026 (arXiv:2608.12025), Witztum, Wang & Wang JACMP 2026 (doi:10.1002/acm2.70848) — all from the 2026-10-17 search log; read and verify before citing.
