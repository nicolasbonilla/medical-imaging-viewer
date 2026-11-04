# Paper F — response to the internal review (major revision)

Review: `F_REVIEW.md` (2026-10-31, recommendation: major revision). Manuscript revised on branch
`research/paper-f-manuscript` (worktree `paper-f-ms`), draft v1.1. Every number in the revised text is
re-derived by `numbers_check.py`: **480 of 480 checks pass, 0 numeric tokens without a source**
(`NUMBERS_CHECK.md`). All new analyses are offline, from stored outputs, and labelled *post hoc*; no
cloud compute was used and no pre-registered result changed.

We thank the reviewer. We agree with every major point. On one detail of M1 we report the tally
differently (see below). Section numbers refer to the revised manuscript.

## Major issues

### M1 — "Hypothesis" and "negative result" framing
**Agreed; changed.** The protocol registered two-sided questions and a reading rule; it states no
hypothesis.
- **Title**: "FLAMeS had a higher lesion-wise F1 than three public CPU segmenters on thick-slice FLAIR in
  multiple sclerosis: a pre-registered paired benchmark".
- **Abstract, Highlights, §1, §4.1, §6**: rewritten around the registered tests. "Negative result",
  "hypothesis not supported" and "secondary hypothesis supported" are removed. §1 marks our prior
  expectation as "not part of the protocol". §2.1 states that the protocol "stated no directional
  hypothesis". The keyword "negative result" is removed.
- **One correction to the review's tally.** The review says that five of six primary tests rejected
  the null "all in favour of FLAMeS". Two of the five favour the tools: SAMSEG and WMH-SynthSeg had
  significantly *fewer* false lesions than FLAMeS. §3.2 now gives the tally exactly: five of six
  rejected; the three F1 tests favour FLAMeS and the two false-lesion tests favour SAMSEG and
  WMH-SynthSeg; no tool met the reading rule. The title therefore claims only the F1 result.

### M2 — Between-band ("degradation") contrast over-interpreted; the "1 mm" band is a 1 mm grid
**Agreed; changed.**
- "Lost 0.102 less F1" and "secondary hypothesis supported" are removed from the abstract, the
  highlights, §3.5 and §6. §3.5 now gives MindGlide's paired-set F1: 0.492 on the 125 iso scans paired
  with FLAMeS (0.518 on all 145), against 0.554 on the thick scans. It states that the +0.102 contrast
  is "statistically significant but cannot be read as smaller degradation with slice thickness", and
  cites the 28.4 vs 11.8 mL over-segmentation on MSLesSeg.
- The contrast is called "the contrast registered as the 'degradation contrast'" (§2.6) or the
  "between-band contrast" (Table 3, footnote c).
- **Protocol §6 commitment honoured.** §2.2 and Table 1 report MSLesSeg's native FLAIR, verified in
  the data paper's full text (PMC12126551, Table 2): mean slice thickness 2.61 mm (SD 0.62), registered
  with FLIRT to the 1 mm MNI152 template. "iso" is now defined as the grid the tools received, and 115
  of the 125 FLAMeS comparison scans are stated to come from ~2.6 mm acquisitions. The same point is in
  §4.3 and the Limitations.
- **Iso weighting.** §2.6, §3.5 and §4.3 state that the 10 Ljubljana patients carry half of every iso
  estimate. §3.5 also gives the post hoc per-cohort values: WMH-SynthSeg ΔF1 −0.286 on MSLesSeg and
  −0.440 on Ljubljana; MindGlide −0.227 and −0.318.
- **Figure 4a (per-cohort values).** Figures belong to the figure designer, who was redesigning them
  in parallel. Its new Figure 4a shows every scan as a dot plus the cohort-weighted mean. Per-cohort
  paired differences are now given in Table A3.

### M3 — The exploratory "second-opinion" signal is beaten by a FLAMeS-only baseline
**Agreed; reproduced and reported.** With our own code (`compute_extra_numbers.py`,
`revision.e1_baselines_posthoc`) on the same 179 thick scans:

| Score (post hoc) | AUROC | 95% CI | Cohort-stratified |
|---|---|---|---|
| MindGlide–FLAMeS disagreement (E1) | 0.779 | 0.597–0.925 | 0.819 |
| Fewer lesions predicted by FLAMeS | 0.932 | 0.861–0.987 | 0.956 |
| Smaller FLAMeS lesion volume | 0.840 | — | 0.890 |
| Cohort = Muslim et al. | 0.733 | — | — |
| Rank sum (lesion count + disagreement) | 0.884 | — | — |

The review gives 0.886 for the rank sum; our 0.884 differs only through tie handling in the ranks.
Three of the four poor MS3SEG scans have 1–4 reference lesions (confirmed).
- **Manuscript.** §3.7 reports the baseline. §4.4 is retitled "The exploratory disagreement signal
  does not survive a simple baseline" and states that no second-opinion flag is proposed. The claim
  is removed from the abstract, the highlights and the conclusion. The sentence "specific to a tool
  that segments as much as FLAMeS does" is deleted.
- **`docs/research/paper-f/APP-FEATURE.md`.** New section 5b ("Final reading"): the second-opinion
  flag is **not supported** and no such flag is proposed. A FLAMeS-only "few lesions" rule is named as
  a better candidate that would need its own pre-specified validation. The interim "criterion met"
  reading is marked as superseded.

### M4 — Conflict of interest
**Agreed; rewritten.** The author is now Nicolás Bonilla Vargas (Universidad Nacional de Colombia; SRH
University München; Daita AI), who develops MSTool-AI.
- The new Conflict of interest statement says that MSTool-AI already uses FLAMeS, so the result
  **favours the author's commercial interest**.
- It discloses the two product features that `APP-FEATURE.md` pre-specified on these numbers: the
  thick-slice reliability notice and the second-opinion flag, which is now withdrawn.
- It states that the reference model was chosen by the author, who designed, ran and analysed every
  arm with an AI agent, and that no independent statistician audited the analysis.
- The Funding section points to it. The Limitations repeat the point and leave a TODO to consider an
  independent co-author or statistical audit.

### M5 — WMH-SynthSeg resampling: sensitivity analysis
**Done, offline, post hoc.** The native 1 mm outputs were not kept. The run did keep, on the FLAMeS
grid, the footprint mean of WMH-SynthSeg's own lesion probability. Four variants were fixed in
`wmh_resampling_posthoc.py` before any of them was computed:
- the pre-registered mask, which reproduces `per_scan.csv` exactly (the script asserts this);
- three thresholds on the footprint-mean probability: 0.50, 0.25 and 0.10 (the last is the closest
  available proxy for footprint-max).

Results (thick band, 179 scans; Table A4):
- F1 was 0.341 / 0.315 / 0.413 / 0.469 for the four variants.
- Predicted volume rose from 4.55 to 13.48 mL, and detection of 14–50 mm³ lesions from 0.050 to 0.104.
- Even the most permissive variant stayed far below FLAMeS: ΔF1 −0.256 (−0.309 to −0.208), with 5.69
  fewer false lesions.

The rule therefore explains part of the volume deficit but not the F1 deficit. This is reported in
§2.4 (the rule is named as the only resampling), §3.4, §4.2, the Limitations and Table A4.

### M6 — Licences
**Agreed; corrected.**
- **Ljubljana.** Table 7 now gives CC BY-NC-ND according to the laboratory's page (registry commit
  71a52ad), and notes that the GitHub mirror states CC BY in its README and has no licence file. We
  follow the stricter licence: academic use only, no derived Ljubljana masks deposited (ND), and no use
  for product calibration, thresholds or marketing (NC). Data availability and the deposit TODO
  exclude Ljubljana. Table 1 is updated.
- **HD-BET.** The parameters are CC BY-NC 4.0, verified in the Zenodo API (record 14445620, "HD-BET v1.5
  parameters") and in HD-BET's `HD_BET/paths.py`, which downloads them; new reference
  `hdbet2024params`. They were used for 151 of the 179 thick scans. The implications are stated in
  §2.2, Table 7, Data availability and the Limitations: the thick-band results rest on non-commercial
  parameters, so they should not be used commercially without a licence or another skull stripper.
  `APP-FEATURE.md` 5b blocks the product reliability notice until this is resolved.

### M7 — Precision of the pre-registration record
- **(a)** "Before any full-run output was **examined**" is now used in §2.6, §2.10 and Table 6. Table 6
  adds that the MindGlide full-run machines had started at 22:32–22:34 UTC. All Table 6 times are UTC
  (raw arm: 2026-10-21 22:43 UTC).
- **(b)** §2.9 now states that the structural check also computes per-scan Dice, lesion-wise F1 and
  volume, and that `RESULTS.md` quotes medians from it. It ran at 00:01:59 UTC, 21 s after 7a9a24e was
  pushed and nine minutes before the final analysis, with the evidence in the agent session log
  outside the repository. Table 6 has a row for it.
  - We did **not** add a `created_utc` field to the frozen result files. Changing committed result
    files after the analysis would weaken the record.
  - We also could not copy the session-log excerpt into the repository: the environment refused it as
    sensitive-source content. Archiving that excerpt is an owner TODO.
- **(c)** §2.10 and Table 6 now say that the interim included the E1 AUROC of 0.78 and that
  `APP-FEATURE.md` read it as meeting its criterion.
- **(d)** §2.1 states the limitation and adds the owner TODO to archive the protocol at 65a95e3 on OSF
  or Zenodo with a DOI, cited as a retrospective archive.
- **m16** is handled in §2.1: "first tool container started (21:39 UTC; the first virtual machine had
  been created at 21:31 UTC)".

### M8 — AI use, authorship and approvals
**Agreed; changed.**
- **Methods §2.1** has a new paragraph, "Roles in the research process, including an AI coding agent".
  It says that the agent drafted the protocol and runbook, wrote all code and tests, ran the analyses,
  took run-time decisions as run coordinator (the `--crop` deviation and the budget rule), verified the
  references and wrote the first draft.
- The claim that the author reviewed or approved the protocol is **removed**. It is replaced by
  "[Owner to confirm …] The repository holds no record of these approvals, and this manuscript does
  not assert them."
- **"Declaration of generative AI and AI-assisted technologies in the writing process"** is now placed
  immediately above the References, following Elsevier policy. The standard sentence "the author
  reviewed and edited the content … takes full responsibility" is marked **[Owner to confirm]**; it
  must be true and confirmed by the author himself.
- The false sentence is corrected to: "No generative AI system created or altered any image or mask:
  all masks were produced by the named segmentation tools, which are themselves AI models, and all
  measurements by the committed scripts."
- CRediT now lists only proposed human roles, marked [owner to confirm], and states that CRediT roles
  apply to human authors only.

## Coordinator item 9
- "(p = 1)" in Table 3 is replaced by "not run". Footnote b explains the Holm convention and that it
  changed one conclusion (0.086 vs 0.034), cross-referencing protocol §4.4 ("never imputed").
- "MS3SEG (released 2026)" is corrected to "MS3SEG data October 2025, article 2026". DataCite
  (verified): DOI issued and registered 2025-10-19.
- **Costs.** 12.55 USD incremental (abstract, highlights, §2.8) and **19.84 USD and 101.97
  machine-hours including the reused FLAMeS, HD-BET and LST-AI runs** (§2.8; Table 5 has a new total
  row). List prices are noted as not yet reconciled with billing.

## Minor issues
- **m1.** §2.6 states the Monte Carlo SE (about 0.008 for p near 0.45). Non-bound p-values are given to
  two significant figures (Table 3: 0.45, 0.99, 1.0).
- **m2.** Done (item 9).
- **m3.** The abstract now says that "existing LST-AI maps were added on the 1 mm grid" and no longer
  says that LST-AI ran on the identical input.
- **m4.** Done (item 9).
- **m5.** Table 4 notes that rows are on different scan sets. Paired tier-C precision (FLAMeS 0.743 vs
  SAMSEG 0.837) is in the Table 4 notes and §3.3. Figure 4a's caption belongs to the figure designer;
  it already states which Ljubljana scans FLAMeS uses.
- **m6.** Voxel Dice added to Table 4.
- **m7.** Scan-pooled (micro) lesion-wise F1 added (§3.4, post hoc): ΔF1 −0.173 (−0.202 to −0.148)
  MindGlide, −0.285 (−0.352 to −0.216) SAMSEG, −0.429 (−0.465 to −0.391) WMH-SynthSeg. 4 thick scans
  have fewer than 5 reference lesions and 3 have 2 or fewer (confirmed).
- **m8.** §4.1 discusses any-overlap matching across thick slices and cites the MSSEG-2016 criteria
  (minimum overlap; limit on how far a detecting component extends beyond the lesion). These were
  verified in the full text (PMC6135867). S3 is used as the illustration.
- **m9.** §2.6 states that the protocol did not justify the margins and gives their scale: 0.05 is
  6.9% of FLAMeS's thick-band F1, and one false lesion is 14% of its 6.9 per scan.
- **m10.** Table A3 gives every per-cohort paired difference with 95% CI; §3.2 reports the ranges.
  Every thick-cohort interval excludes zero. A per-cohort forest *figure* was not added, because
  figures are the designer's.
- **m11.** Done. The released `dataset_fingerprint.json` (109,486 bytes, read by HTTP range requests;
  `fingerprint_check.py`) has 668 entries and **no voxel dimension above 1.25 mm**, so no thick-slice
  scan was a training case at its own geometry; a resampled copy cannot be excluded. The Paper A
  MSLesSeg check (0 of 115 scans match any of 319 1 mm entries) is snapshotted in `data/`. Details are
  in Appendix B.
- **m12.** Not done. Completing SAMSEG needs new cloud compute, which this revision did not use. It is
  listed in the Limitations as an option.
- **m13.** §3.8 reports the machine type next to each runtime, adds the raw-arm MindGlide medians
  (253–286 s on e2-standard-4, peak 13.3 GB), and notes the processor families.
- **m14.** §2.3 states that test-time mirroring (nnU-Net's default) was off and is unlikely to have
  favoured FLAMeS. The nnU-Net version stays an owner TODO: it is in the job's lock file in the
  research bucket, and no cloud access was used.
- **m15.**
  - The FLAMeS correction (J Neuroimaging 35(5):e70093) was added and cited; verified in Crossref.
  - Crossref gives no LNCS volume for the ICPR chapter, so none was added (noted in `references.bib`).
  - The Holm issue number is confirmed only by a secondary source, so it was not added.
  - Shifts 2.0 is kept as the arXiv preprint.
- **m17.** The repository licence and CLAIM checklist remain owner TODOs in the text.
- **m18.** The untracked `figures/mstool.mplstyle` and `figures/mstool_figstyle.py` belong to the figure
  designer working in parallel. They are not committed by this revision.

## Files changed or added
- **Changed:**
  - `manuscript.md`;
  - `references.bib` (two entries and the revision notes);
  - `compute_extra_numbers.py` and `data/extra_numbers.json` (the `revision` block and total costs);
  - `numbers_check.py` and `NUMBERS_CHECK.md`;
  - `docs/research/paper-f/APP-FEATURE.md` (section 5b);
  - `docs/research/paper-f/PROTOCOL.md` (one dated section 12 row).
- **New:**
  - `wmh_resampling_posthoc.py` and `data/wmh_resampling_posthoc.json`;
  - `fingerprint_check.py` and `data/flames_fingerprint_check.json`;
  - `data/mslesseg_flames_overlap_check_87e998d.json`;
  - this file.
- **Not touched:** figure files and figure captions (the figure designer's), and `latex/` (the
  template agent's).
