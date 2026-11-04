# Response to the independent review of Paper A (major revision)

*Manuscript version 2.0, 2026-11-04, branch `research/paper-a-manuscript`. Every new number is
computed offline from the frozen per-candidate cache (SHA-256 2096109e…a6f4ec) and traced in
`NUMBERS_CHECK.md` (219 claims, all PASS against full-precision records; every table regenerated and
identical). The review-stage analyses were logged as protocol entry 11 and pushed before they were run
(commits 75093ec, 2333f05). We thank the reviewer: the report was careful, its re-derivations
reproduced, and it led to substantial changes.*

Section and table numbers refer to manuscript version 2.0.

---

## A. Reproducibility audit (review §3)

**Double rounding (items a–h).** Fixed at the source. `research/paper_a/v03r_fullprecision.py` re-runs
the committed analyses unchanged, with every rounding helper replaced by `float()`, and writes
`*_fullprec.json` records; for each, every committed number equals the full value at the committed
precision (`2026-10-31_paper_a_fullprec_check.json`: 49 918 + 173 + 161 + 1107 numbers compared; the
only differences are one label string corrected by protocol entry 9 and boolean reproduction flags that
compared full precision against the rounded record). Tables, text and figures now render from full
precision and round once (half up). `check_numbers.py` now compares with full precision and fails on any
value that is within half a unit but not the half-up value, so double rounding is caught. All eight items
are corrected (e.g. the abstract's fold-0 Muslim FDR is now 0.051; the > 6.5 mm group 0.119). The
stricter check found **four further slips** of the same kind, also corrected: the post-hoc low-load
subgroup intervals (0.196 [0.119, 0.282] vs 0.050 [0.011, 0.102]), the hierarchical e-value interval
(0.212 [0.187, 0.239]), and fold-0 leave-one-site-out MS3SEG (0.175).

**(i) PediMS median.** §6.6 now gives MS3SEG 108, Muslim 117, PediMS 79, MSLesSeg 68, Ljubljana 20 mm³.

**(j) 22–51 %.** §6.3 now gives both γ: the safe threshold lies above the top false candidate for
58–78 % of first scans at γ = 0.1 and 22–51 % at γ = 0.2 (new record
`2026-10-31_paper_a_revision_extra.json`, protocol entry 11 (i)).

**(k) SUB.** §3.2 and Table 3 state that SUB draws from each calibration patient's first scan.

---

## B. Major issues

### M1 — framing of the central contrast

- **Title** changed to "Thin-slice calibration does not transfer to thick-slice MS FLAIR: a
  protocol-first five-cohort audit of conformal lesion-wise false-discovery control". "Marginal, not
  per-scan", "pre-registered" and "across slice thicknesses" are gone.
- **Abstract** now leads with the pre-registered verdicts (P1 *inconclusive*, P2 *refuted*), gives the
  one-sided upper bounds as inflation factors (1.4α MS3SEG, 1.8α Muslim), reports P1's per-scan
  exceedance (34 % of MS3SEG scans with FDP > 0.1 at α = 0.1) and the FDR among selecting scans (Muslim
  0.188), and is less dense.
- **One-sided bounds for every P1 cell**: new Table 4b (bootstrap with calibration fixed; two-level
  bootstrap; Hoeffding–Bentkus over patients) and §6.2 text.
- **Per-scan exceedance under P1** is reported for every primary cell (Table 4b) and every D3 procedure
  (Table A4); §6.2 states that the contrast is between estimands.
- **"held"** removed from §8.1–8.2 and the conclusions; Appendix B records the withdrawn version-1
  framing.

### M2 — validity conditions and the theoretical anchor

- New §3.1 paragraph "What the guarantees assume, and why none of them strictly holds here":
  matching-dependent labels, within-scan and within-patient clustering, repeated test scans. P1 is
  described as a calibrated procedure whose guarantee assumes conditions the data do not meet (also §9).
- **BH anchor corrected** (§3.2, §6.2): BH gives a bound, α·E[m0/m], with π0 the mean of the per-scan
  shares (scans without candidates count 0; the values 0.034 / 0.037 are these means). The text notes
  that the within-site MS3SEG value (0.041) lies above the bound.
- **Ratio with uncertainty** (§6.2, Table A14): 2.6 (95 % CI 1.3–7.1) and 3.2 (1.2–25.6) at α = 0.1,
  patient-paired bootstrap; across 20 further within-site fold seeds the ratio ranges 2.09–2.82 (MS3SEG)
  and 1.89–4.83 (Muslim); at α = 0.2, 1.6 (1.3–2.2) and 1.4 (0.9–2.6).
- **Simulation** (§6.2, Table A7): conformal BH with the observed candidate counts, a scan random effect
  (ICC 0–0.2) and a shift of the test false scores. Clustering alone kept the realised FDR at
  0.030–0.032 (below α·π0 = 0.034) but 11–12 % of scans still exceeded FDP 0.1; a 0.3-SD shift doubled the
  FDR. The observed inflation is attributed to a shift of the score law, and part of the per-scan
  exceedance is intrinsic to the estimand.

### M3 — weight of the "pre-registration"; the concurrent study

- "Pre-registered" removed from the title; the abstract and §5.1 describe a **protocol-first analysis
  committed to the local git repository 38 minutes before the first results, by AI-agent sessions, not
  publicly time-stamped before the results**. §5.1 states that the analysis script was committed only
  with the results (8a420bc), so nothing shows that it postdates the protocol, and that push times bound
  the addendum's publication, not its computation. "Pre-registered" is kept only for the protocol's fixed
  rules and verdicts, with that qualification.
- **Lesion-detector v3.1** disclosed in §5.1, with its commits (129d2ff 04:14, 0d339b1 04:24, d451fbb
  05:13 CEST), its overlap with our data (same three thick-slice cohorts, same five-fold maps, fold
  disagreement), the fact that its results preceded our first rewording (0731145, 05:30) and every
  manuscript-stage analysis, and that it was agent-run. Also in §9 and the AI statement.
- **Public archive**: owner TODO (Declarations, Appendix D item 3): deposit protocol, addendum, code and
  full-precision records on OSF or Zenodo with a DOI; register future studies there before analysis. We
  cannot do this offline.

### M4 — the estimand rewards abstention

- Every primary cell (Table 4b) and every D3 procedure (Table A4) now reports the share of scans
  selecting, the FDR among selecting scans, the micro-FDR and the share with FDP > 0.1, next to the
  pre-registered estimate (empty = 0). Examples in §6.2: Muslim D3 α = 0.1, 33/51 scans select, FDR among
  them 0.188; D2 18/51, 0.233; MSLesSeg D2 10/115 scans.
- **Abstention flag revisited**: a post-hoc "low power" flag (fewer than half of the scans select, or
  sensitivity < 0.10) complements the pre-registered flag; 6 of the 16 P1 cells carry it.
- **Matched power** (§6.4, Tables A5–A6): validity–power frontiers over α = 0.05–0.3 with intervals; at a
  sensitivity of 0.3 on MS3SEG, P1, B2 and B3 have realised FDR 0.108, 0.109 and 0.113 — the nominal-level
  differences are mostly operating points.
- **k\* = 10** reworded (abstract, §6.8, §8.1, Appendix B): P2 cannot select with fewer than 9
  calibration patients (δ = 0.1) and the next grid value is 10; the comparison power was itself near zero
  (Muslim 0.004); with 10 local patients P2 is valid on average and finds 4.0 % / 0.7 % of lesions
  (2000 draws), as within site; the within-site P2 cells were themselves inconclusive.

### M5 — intervals and decision rule

- **Few clusters**: a one-sided 95 % Hoeffding–Bentkus bound over patients for every primary cell
  (Table 4b), valid for any number of independent patients. With it, 6 of the 16 P1 cells hold, 9 are
  inconclusive and 1 is not estimable; Ljubljana-10 and PediMS cannot be classified (bounds 0.259–0.475).
  Degenerate [0, 0] bootstrap intervals are now classified "not estimable" (Table 4b; Tables 5 and A2 for
  the baselines). The pre-registered classification is kept and reported as such.
- **Conditional vs marginal**: a two-level bootstrap (1000 resamples) for **every** primary cell, with
  its one-sided bound and Monte Carlo SE (Table 4b). MS3SEG P2 γ = 0.1 is 0.20 [0.12, 0.31] (500
  resamples in v0.3 gave a lower bound of 0.10: borderline within Monte Carlo error, stated in §6.3).
- **Margin**: §5.4 states that 0.05 absolute is 50 % of α = 0.1 and 25 % of α = 0.2, that it was fixed
  before outcomes without further justification, and reports inflation factors instead.
- **Multiplicity**: §5.4 states that the cells are strongly correlated (shared test patients and
  thresholds), that the "≈ 0.8 spurious violations" figure assumes independence, that Bonferroni remains
  valid under any dependence, and that secondary/post-hoc results (the 0.196 subgroup, the 13/70 control
  subset) carry no multiplicity control; both are labelled so in the text.
- **Monte Carlo error**: D5 key cells and SUB re-run with 2000 draws (Tables 9 and A8), with MC SE of the
  2000-draw means and of a 200-draw mean. The MS3SEG P2 sensitivity at k = 10 is 4.0 % (2000 draws); the
  200-draw 3.85 % differs by less than one 200-draw SE (0.003).

### M6 — thickness is a cohort contrast

- Title no longer mentions slice thickness. §6.6 is now "Cohort and acquisition contrasts": the
  pre-registered bands are presented as cohort–acquisition groups (G1–G4); the > 6.5 mm group is mostly
  MS3SEG — one Toshiba 1.5 T scanner whose annotation excludes periventricular hyperintensities; the
  3.9 mm group is nine children.
- **"Slice spacing"** is used throughout for the thick cohorts; §4.1 gives thickness and gap (MS3SEG
  4.7–6.9 mm + 0.7–2.1 mm gap; Muslim 3–6 mm thickness, 4.86–8.3 mm spacing; PediMS 3.9 mm spacing, 3 mm
  thickness per its description).
- **Table 7** is now per cohort, labelled by acquisition; it states that lesion counts are not comparable
  across grids.
- **§7** shortened to one paragraph (see D).

---

## C. Minor issues

1. Rounding — see A.
2. PediMS median — see A (i).
3. 22–51 % — see A (j).
4. SUB first scan — see A (k).
5. FLAMeS training data (§4.2): now "668 FLAIR scans … eight datasets (three public, five private) from
   seven sites; 11 sources when the four MSSEG-2016 centres are listed separately"; the 575 vs 408
   inconsistency is stated; the 53 MSSEG-2016 cases are said to include training and test cases of the
   challenge.
6. Thick-slice contamination (§4.2): the fingerprint's absence of any training case with spacing ≥ 3 mm
   (v3.1 protocol) is now used, with the caveat about pre-resampled training data.
7. Ljubljana licence: "the laboratory states both CC BY (database description PDF) and CC BY-NC-ND (web
   page)" (Table 2, Declarations).
8. FLAMeS weights licence: CC BY 4.0 on Zenodo vs CC BY-NC 4.0 on the Hugging Face card (changed
   2026-08-13); the article is non-commercial; consequences for commercial use stated (Table 2,
   Declarations, Appendix D). The Hugging Face fact is the reviewer's web finding; we could not re-check it
   offline (marked "external" in NUMBERS_CHECK).
9. SibBMS: cited as MELBA 2025:046 (doi 10.59275/j.melba.2025-f798) with seven authors; data availability
   now says "openly downloadable".
10. PediMS: "distributed both raw (defaced) and skull-stripped; we used the stripped images"; spacing
    3.9 mm, thickness 3 mm per the dataset description (Appendix D: owner to confirm the 3 mm).
11. Muslim: 60 patients from about 20 centres (most from Baghdad); the 51 axial scans used, 6 coronal and
    3 sagittal not used; per-scan pixel estimate 0.41–0.97 mm; the ±5 % accuracy comes from the head-size
    recipe's 4.6 % coefficient of variation on 15 MS3SEG adults of known pixel size (§4.1).
12. AUROC comparison: §6.1 states that the two figures compare different candidate sets; new paired
    comparison on the same (ensemble) candidates (§6.7, Table A9): single folds 0.51–0.64 vs ensemble
    0.78–0.82, ensemble minus best fold +0.16 to +0.21, with the caveat that conditioning on the
    ensemble's candidates favours the ensemble.
13. Unreported pre-registered results now in the appendix: D5 for PediMS and Ljubljana-10 (Table A13),
    α = 0.3 (Table A11), P2 γ = 0.2 size bins (Table A12).
14. Strict matching, S_cons and PediMS-without-P9: full table (Table A10).
15. Controls (§6.9): the exchangeability premise of P1 (patient nulls mix matching fragments and
    protocol-excluded hyperintensities) and the weaker P2 premise (a control's safe threshold always lies
    above its top candidate; for patients only 58–78 % at γ = 0.1) are stated; the 30 earlier controls are
    the first 40 subject IDs minus sub-021…030, whose August outputs were lost (compute-ledger record); the
    median volume is given for all 263 false candidates (27 mm³) and for the periventricular ones (61 mm³).
16. Figure 1: a dark-edged "holds" marker now flags cells that hold with an estimate above nominal (key
    and caption updated; drawn with the shared style module after the figure redesign was complete).
17. HAZ-001 added next to HAZ-015 (§7).
18. "Independent" re-implementations: disclosed as agent sessions (§5.7, §9, AI statement); a human
    re-derivation and the archive of the patient re-implementation are owner items (Appendix D item 2).
19. Abstract density reduced (see M1).
20. Bibliography — see E.

---

## D. MSTool-AI claims (review §6)

- §7 reduced to one paragraph that states the exact status: the requirement and risk documents record
  CP-SLICE-THICKNESS-001 as approved by the owner on 2026-10-23 (document versions still marked draft);
  the card was released behind a flag that is off by default and has not been enabled; its evidence file
  still says "DRAFT - PENDING owner approval" (a record inconsistency, Appendix D item 7); the figures are
  not re-derived for the deployed segmenter; the wording is not reviewed with radiologists. Hazards
  HAZ-015 and HAZ-001; the 3D FLAIR recommendation cites MAGNIMS–CMSC–NAIMS 2021.
- DIS on healthy brains: the problem-report identifier (PRB-003, CAPA-016) and the fact that the atlas
  is applied without registration on template-space images ("the software's most favourable case") are
  in §6.9.
- Competing interests: Nicolás Bonilla Vargas develops MSTool-AI and is affiliated with Daita AI (further
  items owner TODO).
- Licences: see C.7–C.9 and the Declarations.
- Data sharing: the Declarations state that the per-candidate data of the four CC BY cohorts (and SibBMS
  under CC BY-NC-SA) can be released, Ljubljana cannot; the release is planned with the public archive
  (owner item).
- AI statement: model and version (Claude Opus 5.5, Anthropic, via Claude Code), the 38-minute
  protocol-to-results timing, and the agent-run v3.1 study are added.
- Author block: Nicolás Bonilla Vargas, ngbonillav@unal.edu.co; Universidad Nacional de Colombia; SRH
  University München; Daita AI.

---

## E. Bibliography (review §7)

**Corrected or completed from the review's web check** (tagged `[V-review]` in `references.bib`):
MSLesSeg now `guarnera2025mslesseg` (Guarnera, Rondinella, … Battiato; DOI 10.1038/s41597-025-05250-y);
SibBMS → MELBA 2025:046 with seven authors and DOI; FLAMeS weights → creator F. La Rosa, record title,
concept DOI; Adhikary et al. → given names, cited as a preprint, internal note removed; Commowick →
article 13650, issue 1, DOI; Montalban → DOI and published correction; IEC 62304:2006+AMD1:2015 (Edition
1.1); Barber et al. → pages 816–845 and DOI; Gazin et al. → pages 1504–1512; Lambert et al. → LNCS 15010,
pages 633–643, DOI and full names; Jin & Candès and HD-BET → OWNER-CHECK closed, HD-BET DOI added; PediMS →
ș / Ș with comma below.

**Not done offline (owner checklist, Appendix D item 5)** — our rules forbid web access, and we do not add
bibliographic details from memory:
- given names for Farinhas et al., Mossina & Friedrich, Hulsman et al.; full author lists for Lesjak et al.
  (7), Molchanova et al. (10), Malinin et al. (18) and the initials of Guarnera et al.'s co-authors;
- DOIs for genovese2006exceedance, bates2021rcps, wang2022false, wiltgen2024lstai, lesjak2018novel,
  carass2017longitudinal, thompson2018diagnosis, wattjes2021magnims, nosek2018preregistration,
  kapoor2023leakage, varoquaux2022machine;
- creators of the four dataset records.

---

## F. What did not change

- The pre-registered estimand, classification rule and verdicts (Q1: P1 inconclusive, P2 refuted; Q3
  "helps on power, but with new violated cells"; Q4 as defined). New quantities are added beside them and
  labelled post hoc.
- No pre-registered number changed; only their printing (rounding).

## G. Files

- `manuscript.md` (version 2.0), `NUMBERS_CHECK.md`, `references.bib`, `figures/` (Figure 1 marker; all
  figures from full-precision records), `export/manuscript.{docx,pdf}`, `RESUMEN_PARA_EL_DUEÑO.md`.
- Scripts: `research/paper_a/v03r_fullprecision.py`, `v03r_revision.py`, `v03r_revision_extra.py`;
  `tools/make_tables.py` and `tools/check_numbers.py` (full precision).
- Records: `docs/research/records/2026-10-31_paper_a_*_fullprec.json`, `2026-10-31_paper_a_fullprec_check.json`,
  `2026-10-31_paper_a_revision.json`, `2026-10-31_paper_a_revision_extra.json`.
- Protocol: `PROTOCOL-v0.3.md` §13 entry 11 and 11 (i).
