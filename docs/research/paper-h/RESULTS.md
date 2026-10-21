# Paper H — Results

Every number below is produced by the scripts in `research/paper_h/` from pinned commits
(`research/paper_h/config.py`) and the committed GitHub snapshot. Protocol: `PROTOCOL.md`
(committed first, `08e952e`). Results computed 2026-10-21.

## How to reproduce

```bash
# from the repository root; needs git with the pinned commits (all on origin; PR heads also at refs/pull/N/head)
python research/paper_h/run_all.py --check      # ≈ 1 min; writes research/paper_h/out/results.json, exit 1 on any coding problem
python research/paper_h/report.py               # renders the tables below from results.json
python -m pytest research/paper_h/tests -q      # 27 tests (≈ 2 min): parsers on synthetic data + re-derivation of the headline numbers
python research/paper_h/snapshot_github.py      # optional: refresh the read-only GitHub snapshot (needs `gh`)
```

Each result cites its key in `results.json` as `⟨key.path⟩`. Per-module commands also exist:
`python research/paper_h/contribution.py` (RQ1), `failures.py` (RQ2), `verification.py` (RQ3),
`governance.py` (RQ4).

---

## 0. Novelty re-check (2026-10-21)

**Question.** Is there a published or preprinted empirical study in which an AI coding agent is the
primary developer of software under a formal IEC 62304 (Class C) lifecycle, with lifecycle and
risk-management records, quantified verification failures and how they were caught?

**Search log (this session, 2026-10-21).** Web search, extended mode, 9 queries: "Claude Code" /
"coding agent" / "LLM agent" × "IEC 62304" / "Class C" / "medical device" / "ISO 13485" /
"regulated software" / "mutation testing" / "negative controls" / "human approval"; JACMP 2026 +
agentic coding; the SSRN title "Trust but Trace". Direct reads: arXiv 2610.08651 (abstract and HTML
full text), arXiv 2607.01087 (abstract), PMC13556308 (full text). SSRN returned 403. This
complements the earlier, broader search of 2026-10-17 (`research_notes/Comprobaciones de
novedad/verificaciones_2026-10-17.md`, Q4, outside this repository; ~25 web searches, arXiv API,
Europe PMC, Crossref, OpenAlex). IEEE Xplore, ACM DL, Scopus and Google Scholar were **not**
searched directly.

**Closest works.**

| Work | What it is | Device / standard | Quantified verification failures | Difference from this case |
|---|---|---|---|---|
| Ferris L., Bonilla S. "A Case Study in Assuring AI-Written Software." arXiv:2610.08651, 6 Oct 2026 (cs.SE; prepared for the workshop "Managing Agents that Manage Agents") | Production healthcare platform built with coding agents (Claude models via Claude Code; also Gemini/GPT in a review council), operator without SE training; 2 interviews + 6 months of records | Not a device; US health-privacy context; "we do not assess compliance"; no IEC 62304 / ISO 14971 | One count (69/84 security-guidance items covered by pre-existing checks); failures reported qualitatively (proxy monitors, silent audits, vanishing checks) | No regulated lifecycle; no risk-control verification records; no per-failure detection data |
| Wang T., Beaudry J., Damato A.L., Kollmeier M., Aramburu Núñez D. "AI-assisted software development for brachytherapy seed inventory management." J Appl Clin Med Phys 2026;27(9):e70795, doi:10.1002/acm2.70795 | In-house desktop tool written entirely by Claude Code (Sonnet 4.6), ~13 h, ~115 prompts | Explicitly not device-level: "these do not constitute the level of verification expected for software classified as a medical device"; manual testing only, no automated test suite, no third-party code review | None | Low-risk operational tool; no lifecycle; no verification records |
| Davis J.C. et al. "Cheap Code, Costly Judgment: A Case Study on Governable Agentic Software Engineering." arXiv:2607.01087 | 12-week first-person case, one engineer + frontier coding agents, 420 KLOC; theory of "governance conversion" (controls discovered from failures) | Not regulated | No failure counts in the abstract | Closest in *theme* (controls learned from agent failures); no safety class, no regulatory records |
| Neighbours listed in the 2026-10-17 search: Nouri et al. EASE 2025 (LLM code generation, automotive, prototype); Liu et al. 2024 (GPT-4 on safety-critical snippets); Kirchner & Knoll IEEE IV 2025; Sun & Staron SANER 2026 (interviews); Gangopadhyay et al. ISSRE-AISQ 2026 (LLM for medical-device safety documentation, framework); Witztum, Wang, Wang JACMP 2026 (debate: QA of AI-coded RT software); Maharjan, SSRN 2026, doi:10.2139/ssrn.7349799 ("Trust but Trace", **unread**) | — | none is an agent-as-primary-developer case under IEC 62304 | — | — |

**Verdict.** *Narrowed, not refuted.* No study found matches the narrow claim: an AI coding agent as
**primary developer** of software under a formal **IEC 62304 Class C** lifecycle, including the
lifecycle and risk-management records, with **quantified** verification failures and their
detection channels. The broad claim "nobody has studied coding agents in healthcare / regulated
settings" is **not** safe (Ferris & Bonilla; Wang et al.). Residual risks: Maharjan (SSRN) is
unread; the field moves weekly (the closest preprint was 15 days old at the time of this check);
the ICSE-SEIP / FSE / RE / SAFECOMP 2026 industry tracks were not searched directly. **Re-run the
search before submission.**

**Conflicts of interest with cited authors** are to be declared by the owner before submission;
that check is handled outside this public document.

---

## 1. RQ1 — Extent of the agent's contribution

**Commits** `⟨rq1_contribution.commits⟩` on `main` @ `6209131` (2025-12-07 → 2026-10-17):

- **327 of 388 commits (84.3 %)** carry the agent's `Co-Authored-By` trailer — the figure stated in
  SDP-001 v1.1 (PR #49) is reproduced exactly. Non-merge commits: **324 / 353 (91.8 %)**.
  Merges: 3 of 35 carry the trailer (§4).
- 35 commits also carry the "Generated with Claude Code" footer (the tool's default footer).
- The trailer is a **lower bound**: the 29 untrailered non-merge commits cluster on three dates
  (Dec 2025 deployment fixes, 17–18 Apr 2026 UI/docs work, 17 Aug 2026 research launches); their
  authorship cannot be determined from the repository.

<!-- RQ1 tables: python research/paper_h/report.py -->
| Month | Commits | Agent-trailered | Share |
|---|---:|---:|---:|
| 2025-12 | 33 | 26 | 78.8 % |
| 2026-01 | 11 | 11 | 100.0 % |
| 2026-02 | 10 | 10 | 100.0 % |
| 2026-03 | 2 | 2 | 100.0 % |
| 2026-04 | 75 | 56 | 74.7 % |
| 2026-07 | 55 | 51 | 92.7 % |
| 2026-08 | 169 | 142 | 84.0 % |
| 2026-09 | 16 | 15 | 93.8 % |
| 2026-10 | 17 | 14 | 82.4 % |
| **All** | **388** | **327** | **84.3 %** |

(No commits in May–June 2026.)

| Trailer model string (self-reported) | Commits | First | Last |
|---|---:|---|---|
| Claude Opus 4.8 | 170 | 2026-07-18 | 2026-09-11 |
| Claude Opus 4.6 (1M context) | 56 | 2026-04-02 | 2026-04-21 |
| Claude Opus 4.8 (1M context) | 27 | 2026-07-10 | 2026-07-12 |
| Claude | 26 | 2025-12-07 | 2025-12-10 |
| Claude Opus 5.5 (1M context) | 25 | 2026-09-27 | 2026-10-17 |
| Claude Opus 4.6 | 12 | 2026-02-08 | 2026-03-14 |
| Claude Opus 4.5 | 11 | 2026-01-10 | 2026-01-18 |

**Lines** `⟨rq1_contribution.lines⟩` (non-merge, text files): agent-trailered commits added
**222,718** lines and deleted 54,779; untrailered commits added **1,623** and deleted 5,274
(agent share of added lines **99.3 %**). The initial import `d62cc37` (agent-trailered; 265 files,
69,839 lines) dominates; excluding it, the agent share is **98.9 %** (152,879 vs 1,623).

**Controlled documents and Class C modules.**
- **67 of 67** non-merge commits that touch a controlled document (`docs/iec62304/`, `docs/mdr/`,
  `docs/qms/`, `docs/clinical/`, `docs/ai-act/`, `docs/usability/`) carry the trailer
  `⟨rq1_contribution.controlled_documents⟩`.
- **25 of 25** commits that touch one of the eight Class C modules carry it
  `⟨rq1_contribution.class_c_modules_any⟩`.

**The withdrawn verification record** `⟨rq1_contribution.withdrawn_verification_record⟩`:
RCV-SUMMARY-2026-04-12 ("Verified 21 (95.5 %) … Failed 0", signed "Development Team (code
inspection)") was created by `b6be6e7` (2026-04-12), an agent-trailered commit (*Claude Opus 4.6
(1M context)*). It was withdrawn in place by `213efdf` (2026-07-18), also agent-trailered
(*Claude Opus 4.8*).

---

## 2. RQ2 — Verification failures, their detection and their persistence

**Coding.** 33 episodes, coded by the agent from 11 CAPA records, the two verification summaries,
the manifest, the negative-control records, commit messages and PR review responses
(`research/paper_h/data/failure_coding.json`). Every one of the **81 quoted passages** (65 for
the episodes, 16 for the CAPA sources and the verified-then-ineffective controls) was found verbatim
at its cited ref, every cited commit exists, and every stage code agrees with git ancestry
`⟨rq2_failures.coding_problems⟩ = []`. Two episodes are multi-item (E01: 12 overstated controls;
E14: 10 false or overstated statements), so 33 episodes cover **53 items**; two episodes overlap
others (E08 ⊂ E07's defect; E16 ⊂ E01's rows), leaving 31 without overlap.

<!-- RQ2 tables: python research/paper_h/report.py -->
| ID | Class | Channel | Stage | Introduced | Detected | Days | CAPA |
|---|---|---|---|---|---|---:|---|
| E01 | P+S | AR | escaped | `b6be6e7` 2026-04-12 | `213efdf` 2026-07-18 | 97 | CAPA-001 |
| E02 | N | IM | escaped | `d62cc37` 2025-12-07 | `80da053` 2026-07-18 | 223 | CAPA-003 |
| E03 | N | IM | escaped | `b8a7065` 2026-04-03 | `80da053` 2026-07-18 | 106 | CAPA-001 |
| E04 | N | IM | escaped | `bc79f1b` 2026-04-13 | `6947213` 2026-07-18 | 96 | CAPA-004 |
| E05 | M | SC | contained | — (never committed) | `ccc8d70` 2026-07-18 | — | CAPA-001 |
| E06 | M+N | SC | contained | — (never committed) | `80da053` 2026-07-18 | — | CAPA-001 |
| E07 | I+S | BP | escaped | `e39cdaa` 2026-07-18 | `8006e7b` 2026-08-14 | 27 | CAPA-001, CAPA-006 |
| E08 | R | BP | escaped | `e39cdaa` 2026-07-18 | `4347d73` 2026-09-28 | 72 | CAPA-001, CAPA-006 |
| E09 | S+R | AR | escaped | `213efdf` 2026-07-18 | `bcc8761` 2026-09-28 | 72 | CAPA-001 |
| E10 | S | AR | escaped | `cba3962` 2026-07-24 | `4347d73` 2026-09-28 | 66 | CAPA-006, CAPA-007 |
| E11 | I | AR | escaped | `f208149` 2026-08-22 | `4347d73` 2026-09-28 | 37 | CAPA-006 |
| E12 | M | SC | contained | — (never committed) | `aad36c9` 2026-10-17 | — | CAPA-006 |
| E13 | I | CI | contained | `aad36c9` 2026-10-17 | `004f7f5` 2026-10-17 | 0 | CAPA-006 |
| E14 | R | AR | contained | — (never committed) | `4347d73` 2026-09-28 | — | CAPA-006 |
| E15 | C+R | AR | escaped | `9ac536d` 2026-04-12 | `4347d73` 2026-09-28 | 169 | CAPA-006 |
| E16 | C+P | AR | escaped | `236d80e` 2026-02-08 | `213efdf` 2026-07-18 | 160 | CAPA-005 |
| E17 | C | EX | escaped | `a637cdf` 2026-03-14 | `4d7b9a0` 2026-10-17 | 217 | CAPA-008 |
| E18 | C | EX | escaped | `8ffa4fd` 2026-08-21 | `4d7b9a0` 2026-10-17 | 57 | CAPA-008 |
| E19 | S+M | BP | escaped | `7567411` 2026-07-24 | `bbbaa6d` 2026-10-17 | 85 | CAPA-009 |
| E20 | R+S | SA | escaped | `cba3962` 2026-07-24 | `bbbaa6d` 2026-10-17 | 85 | CAPA-002, CAPA-009 |
| E21 | I | CI | contained | `bbbaa6d` 2026-10-17 | `521bf5d` 2026-10-17 | 0 | CAPA-009 |
| E22 | I | BP | escaped | `6947213` 2026-07-18 | `c15a959` 2026-10-17 | 91 | CAPA-010 |
| E23 | S | BP | escaped | `6947213` 2026-07-18 | `c15a959` 2026-10-17 | 91 | CAPA-010 |
| E24 | S | BP | escaped | `e39cdaa` 2026-07-18 | `c15a959` 2026-10-17 | 91 | CAPA-010 |
| E25 | M | SC | contained | — (never committed) | `c15a959` 2026-10-17 | — | CAPA-010 |
| E26 | M+I | AR | contained | `c15a959` 2026-10-17 | `db4f1af` 2026-10-18 | 1 | CAPA-010 |
| E27 | I | AR | escaped | `7fcf1cd` 2026-08-19 | `21c8d6b` 2026-10-17 | 59 | CAPA-011 |
| E28 | I | AR | contained | `21c8d6b` 2026-10-17 | `86f19f2` 2026-10-18 | 1 | CAPA-011 |
| E29 | M | AR | contained | `21c8d6b` 2026-10-17 | `86f19f2` 2026-10-18 | 1 | CAPA-011 |
| E30 | I | AR | contained | `d81cb78` 2026-10-17 | `c838bb1` 2026-10-18 | 1 | CP-FLAMES-BROWSER-001 |
| E31 | I+M | AR | contained | `d81cb78` 2026-10-17 | `c838bb1` 2026-10-18 | 1 | CP-FLAMES-BROWSER-001 |
| E32 | R | AR | contained | `c838bb1` 2026-10-18 | `7cce845` 2026-10-21 | 3 | CP-FLAMES-BROWSER-001 |
| E33 | I | AR | contained | `c838bb1` 2026-10-18 | `7cce845` 2026-10-21 | 3 | CP-FLAMES-BROWSER-001 |

Episode titles and verbatim evidence are in the coding sheet. Examples named in the brief:
- **E19** — the FastAPI patient check was a plain `def` returning an un-awaited coroutine; it never
  ran. RC-026 was recorded VERIFIED with 4 + 3 negative-control vectors, all of which operated on
  the decision function or on source text. A request probe found that "the authorization function
  ran **0 times**" (CAPA-009).
- **E22/E23** and CAPA-010 — the "laterality not labelled" caveat was off-screen (visible fraction
  0.00 at three window sizes) while its jsdom tests passed; 3D drew orientation letters through a
  library default. The ruler read "20.0 mm" for 10 mm at zoom ×2 (CAPA-010 Finding 3) — a product
  defect with **no** test at all, therefore not an episode under the protocol definition.
- **E27** — clinical-tool masks transposed twice (store, then load); "No round trip was tested",
  and "Cubic test volumes hide it" (CAPA-011).

| Class | Primary | Incl. secondary | Escaped | Contained |
|---|---:|---:|---:|---:|
| P — prose / self-attested | 1 | 2 | 1 | 0 |
| N — never executed / could never fail | 3 | 4 | 3 | 0 |
| S — wrong locus | 5 | 8 | 5 | 0 |
| I — environment could not observe | 10 | 11 | 4 | 6 |
| M — negative control invalid or blind | 6 | 8 | 0 | 6 |
| R — false statement in an agent-drafted record | 4 | 6 | 2 | 2 |
| C — clinical/labelling content not traced | 4 | 4 | 4 | 0 |

| Channel | Episodes | Escaped | Contained |
|---|---:|---:|---:|
| AR — adversarial review (agent sessions) | 15 | 7 | 8 |
| BP — behaviour probe | 6 | 6 | 0 |
| SA — systematic sweep | 1 | 1 | 0 |
| CI — CI run | 2 | 0 | 2 |
| IM — while implementing a related action | 3 | 3 | 0 |
| EX — external research | 2 | 2 | 0 |
| OW — owner | 0 | 0 | 0 |
| SC — self-check in the authoring session (post hoc) | 4 | 0 | 4 |

**Who introduced, who detected** `⟨rq2_failures.summary⟩`:
- All **28** episodes with an introducing commit were introduced by agent-trailered commits.
- All **33** detections are recorded in agent-trailered commits. **No** record attributes a
  detection to the owner (channel OW = 0). This does not mean the owner played no part: the owner
  commissioned the audits and reviews; the records simply credit the mechanism (review, probe,
  sweep), not a person.
- Model strings: in 18 of the 28 episodes with an introducing commit, the detecting commit names a
  later model string than the introducing one (Opus 4.8 → Opus 5.5: 11), and in 10 the same string
  (Opus 5.5 → 5.5: 9; 4.8 → 4.8: 1)
  `⟨rq2_failures.episodes[*].introduced_model / detected_model⟩`. Model and process changed
  together; this study cannot separate them.

**Persistence** `⟨rq2_failures.summary.days_to_detection_by_stage⟩`:

| Stage | Episodes | With intro commit | Median days to detection | Range | Introduced between | Detected on |
|---|---:|---:|---:|---|---|---|
| **Escaped** (landed on `main` first) | 19 | 19 | **91** | 27–223 | 2025-12-07 … 2026-08-22 | 4 dates: 07-18 (5), 08-14 (1), 09-28 (5), 10-17 (8) |
| **Contained** (caught before landing) | 14 | 9 | **1** | 0–3 | 2026-10-17 … 2026-10-18 | 07-18 (2), 09-28 (1), 10-17 (4), 10-18 (5), 10-21 (2) |

Escaped failures were recorded on **four dates only** (audit bursts), not continuously. Wrong-locus (S),
never-executed (N), prose (P) and clinical-content (C) failures **all escaped**; every negative-
control failure (M) was contained. **Caution — right censoring:** failures introduced in October
have had at most four days to escape detection; the contrast between stages is descriptive and
confounded with the model change and with the start of routine pre-merge adversarial review.

**CAPAs** (context): 11 CAPAs (10 Critical, 1 Major), all opened in agent-trailered commits,
between 2026-07-18 and 2026-10-17. Opening channel: AR 6, IM 2, BP 2, EX 1
`⟨rq2_failures.capas_summary⟩`.

| CAPA | Severity | Opened (commit, date) | Channel |
|---|---|---|---|
| CAPA-001 | Critical | `ccc8d70` 2026-07-18 | AR |
| CAPA-002 | Critical | `ef7c7c5` 2026-07-18 | IM |
| CAPA-003 | Major | `80da053` 2026-07-18 | IM |
| CAPA-004 | Critical | `213efdf` 2026-07-18 | AR |
| CAPA-005 | Critical | `213efdf` 2026-07-18 | AR |
| CAPA-006 | Critical | `4347d73` 2026-09-28 | AR |
| CAPA-007 | Critical | `b6a3edd` 2026-10-17 | AR |
| CAPA-008 | Critical | `4d7b9a0` 2026-10-17 | EX |
| CAPA-009 | Critical | `bbbaa6d` 2026-10-17 | BP |
| CAPA-010 | Critical | `c15a959` 2026-10-17 | BP |
| CAPA-011 | Critical | `21c8d6b` 2026-10-17 | AR |

(CAPA-001's record gives 2026-07-16 as "Date Opened"; the table uses the commit that first records
it. CAPA-010 and CAPA-011 exist only on open PR branches.)

---

## 3. RQ3 — Risk-control verification evidence

**Before and after adversarial re-verification** `⟨rq3_verification.rcv_headline⟩`
(RCV-SUMMARY-2026-07-18 §1, 22 controls):

| | 2026-04-12 record | 2026-07-18 re-verification |
|---|---:|---:|
| Verified | **21** | **4** |
| Partial | 1 | 6 |
| Overstated / not implemented | 0 | 12 |

The re-verification itself was later found incomplete for one control (E09: RC-010 examined on one
of three paths).

**Manifest** `⟨rq3_verification.manifest⟩` — risk control → test binding created under CAPA-001
PA-1 and enforced by a test in CI:

| Manifest at | Controls | implemented | not_implemented | unverified | implemented with ERRATUM |
|---|---:|---:|---:|---:|---|
| main (`6209131`) | 35 | 18 | 10 | 7 | RC-024, RC-026, RC-029 |
| capa010 (`8b839fd`) | 37 | 20 | 10 | 7 | RC-024, RC-026, RC-029 |
| capa011 (`86f19f2`) | 38 | 21 | 10 | 7 | RC-024, RC-026, RC-029 |
| flames (`7cce845`) | 49 | 30 | 12 | 7 | RC-024, RC-026, RC-029 |

Every `implemented` control names a negative-control result. **3 of 18** implemented controls on
`main` carry an ERRATUM — each was recorded with passing negative controls and later found not to
work in the running system (protocol metric 10). Adding two cases documented elsewhere (post hoc:
RC-023, "the viewport side held in 2D only", CAPA-010; RC-010's 2026-07-18 entry, superseded),
**5** controls were verified, then found ineffective or incomplete
`⟨rq2_failures.verified_then_ineffective⟩`.

**Negative controls (mutations)** `⟨rq3_verification.negative_controls⟩`:

| Record | Ref | Mutations | Detected | Declared equivalent/redundant | Unexpected undetected | Restored green |
|---|---|---:|---:|---:|---:|---|
| RC-032 (CAPA-006) | `6209131` | 45 | 42 | 3 | 0 | True |
| RC-029 (CAPA-007) | `6209131` | 11 | 11 | 0 | 0 | True |
| CAPA-008 | `6209131` | 17 | 17 | 0 | 0 | True |
| CAPA-009 | `6209131` | 32 | 32 | 0 | 0 | True |
| CAPA-010 | `8b839fd` | 26 | 25 | 1 | 0 | True |
| CAPA-011 | `86f19f2` | 22 | 22 | 0 | 0 | True |
| CP-FLAMES-BROWSER-001 | `7cce845` | 46 | 45 | 1 | 0 | True |
| **Pooled** | | **199** | **194** | **5** | **0** | True |

- **194 / 199 (97.5 %)** mutations detected; all 5 undetected are declared in their record as
  equivalent or redundant by design; **0 unexpected** survivors in the final records.
- These are **final** records: they were re-run after reviews until no unexpected survivor
  remained. The informative signal is in the six M-class episodes (E05, E06, E12, E25, E26, E29),
  where a first run was invalid or a mutation survived, and in E19, where a control with seven
  passing mutation vectors had never executed.
- **Tests written after a defect, run on the pre-fix code:** CAPA-010's 27 new tests on the `main`
  sources: **25 failed, 2 passed** (both expected to pass) `⟨rq3_verification.capa010_new_tests_on_main_sources⟩`.
  In-browser FLAMeS: the new tests fail on the reviewed code in **6/6** runs; the reviewed (pre-fix)
  tests detect **0/2** mutations that remove the model SHA-256 check.
- **Evidence freshness (post hoc)** `⟨rq3_verification.evidence_freshness_post_hoc⟩`: the records
  store the SHA-256 of every file they mutated. On `main`, **3 of 31** hashed files no longer match:
  both source files of the RC-029 record (executed 2026-10-17 13:54, then changed the same day by
  CAPA-008/009 before merge) and `README.md` in the RC-032 record. The RC-029 negative controls
  therefore describe code that is no longer on `main`; nothing in CI notices. The two branch
  records that store hashes match their own heads (CAPA-010 6/6, CAPA-011 2/2); the in-browser
  FLAMeS record stores none.

---

## 4. RQ4 — The human-approval boundary

`⟨rq4_governance⟩`, GitHub snapshot retrieved 2026-10-21T20:24:04Z:

- **56 PRs** (47 merged, 9 open, 8 of them drafts). **Formal GitHub reviews: 0** on all 56.
  All 47 merges show the owner's account as merger. All 56 descriptions end with the Claude Code
  footer.
- **Merges on `main`:** 35; 32 made through GitHub (committer "GitHub"), 3 made locally in
  agent-trailered commits (PR #46, PR #47 and the intermediate merge that recorded the PR #46
  approval). The hosting records cannot tell an owner action from an agent action taken with the
  owner's credentials.
- **Recorded approvals:** 31 lines in 19 controlled documents record the owner's approval
  ("N. G. Bonilla Vargas — approved …"). `git blame` attributes **all 31** to **5 commits, all
  agent-trailered** (`9102200`, `880a065`, `bae1a7f`, `31940b6`, `b39c839`; 2026-09-28 and
  2026-10-17). The approval evidence in the quality records is therefore text written by the agent
  on the owner's instruction; nothing in the repository binds it cryptographically to the owner.
- **Pending approval:** PRs #51, #52, #53 state that owner approval is pending; #53 reports two
  blocking review verdicts ("do not approve yet", "do not merge yet"). SDP-001 v1.1 — the
  declaration of the agent as a development tool (IEC 62304 §5.1.4) — is in open PR #49; on `main`
  the plan does not mention the agent.
- **Permission boundary (qualitative, data source D8; not reproducible from the repository).** The
  operator's notes record that between 2026-10-17 and 2026-10-21 the agent harness's permission
  classifier refused, on two occasions, to let the agent write "approved by N. G. Bonilla Vargas" into controlled
  documents: once after a chat message approving "everything", and once on 2026-10-21 after the
  owner's written authorisation. The agent did not change its permission settings; the owner was
  asked to merge on GitHub or to authorise explicitly. The same act (agent writes the approval
  line) had been performed five times before (above).

---

## 5. Deviations from the protocol (post hoc)

1. **Channel SC** (self-check within the authoring session) — 4 episodes did not fit the seven
   a-priori channels.
2. **Stage** (escaped vs contained), with a git-ancestry check — added after seeing the latency
   distribution.
3. **Verified-then-ineffective**: RC-023 and RC-010 added to the 3 manifest errata from other records.
4. **Approval-line authorship via `git blame`**, distinct detection dates, and model-string pairs —
   added during RQ4/RQ2 analysis.
5. **Evidence freshness** (recorded source hashes vs the files at the ref) — added during RQ3.

Everything else follows PROTOCOL.md §5.

## 6. What these numbers do not show

- Whether the device is safe, or whether a human team would have done better or worse.
- Failures that were never detected — by construction, the episodes are the detected ones.
- Inter-rater reliability: one coder (the agent). A human second coder is required before submission.
- Effort or cost: session logs and prompts were not analysed.
