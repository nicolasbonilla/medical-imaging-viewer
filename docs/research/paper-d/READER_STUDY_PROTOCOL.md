# Paper D — Reader study protocol (three neuroradiologists)

**Version 1.0 · 2026-10-31 · branch `research/paper-d-dis-fragility`.** Written before any reader
has been invited or has seen a case. Research, not the medical device. To be time-stamped on OSF
before the first read; changes after that go to §14 with date and reason. Power simulations:
`research/paper_d/reader_power.py`, record `records/reader_power_record.json`.

> **Resumen en español sencillo.** Tres neurorradiólogos leen, cada uno por su cuenta y sin ver
> ningún resultado automático, 84 resonancias públicas y anónimas de esclerosis múltiple: dicen en qué
> regiones del cerebro hay lesiones y si se cumple la "diseminación en el espacio"; un mes después
> clasifican lesión por lesión. Con eso sabremos si los casos en los que los programas cambian de
> opinión son también los casos en los que los expertos dudan. Cada lector dedica **unas 8 horas**
> en total, en su casa, sin conexión, con un programa de lectura hecho a partir de MSTool-AI. A cambio
> se les ofrece ser coautores del artículo.

---

## 1. Questions

- **R1 (primary).** Are the scans whose automated brain-DIS decision is *not unanimous* across the
  1,120 plausible pipelines (paper D, RESULTS §3) more often scans on which the three
  neuroradiologists are *not unanimous*?
  - R1a (primary test): unadjusted, one-sided exact Fisher test, α = 0.05.
  - R1b (key secondary): the same association adjusted for log expert lesion count (logistic
    regression, one-sided likelihood-ratio test) — because both kinds of disagreement rise as lesion
    burden falls.
- **R2.** How often do automated decisions differ from the **reader majority**: the device's automated
  default, LST-AI as shipped, the average pipeline, and the device's rule applied to the expert mask
  (which separates segmentation error from rule error)? Compared with how often each reader differs
  from the majority of the other two.
- **R3 (human baseline).** Inter-reader agreement on brain DIS and on the presence of
  periventricular (PV), cortical/juxtacortical (JC) and infratentorial (IT) lesions; intra-reader
  agreement after washout.
- **R4 (lesion level).** Agreement of the device's region rule and of LST-AI's rule with the reader
  majority, per region, on the expert lesions — including infratentorial lesions, lesions the atlas
  places in no zone, and lesions touching the third ventricle.
- **R5.** Sensitivity and specificity of the two stability signals proposed for the app (segmenters
  disagree; thin margin; RESULTS §8) for "device default ≠ reader majority". Same scans as their
  discovery, new reference: a partial validation only.

## 2. Design

Retrospective, multi-reader study on public, de-identified MRI; three readers; two tasks in three
sessions; fully crossed (every reader reads every case). No patient is involved, no clinical decision
is made, and the reading software is a research build, not the medical device.

## 3. Case selection (fixed before any read)

Script: `research/paper_d/select_reader_cases.py` (seed 20261031); output
`data/experiments/paper-d/reader-study/case_manifest.json` (SHA-256
`130fae096b8fd3fa0d5f197306b76de0c8a434c198ff60f394bc0dcf92e8654a`) and `reading_orders.json`, both
**git-ignored and coordinator only**: the manifest links each case code to its stratum, and this
repository is public. Anyone with the public data can regenerate it bit for bit from the script.

| Set | Rule | Scans |
|---|---|---|
| Non-unanimous | every primary-set scan whose decision is not unanimous across the 1,120 automated pipelines (incl. 12 contested, 10–90 % "met") | **48** (38 patients) |
| Unanimous controls | one scan per patient, from the 47 patients without any non-unanimous scan; seeded random sampling stratified by expert lesion-count tertile (cuts 18 / 30) to follow the non-unanimous mix as far as available | **36** |
| **Reading set** | | **84 scans, 74 patients** |
| Repeat reads | 6 non-unanimous + 6 controls (seeded), re-read in session 3 | 12 |
| Training | 4 scans from the 20 FLAMeS-in-sample Ljubljana scans (outside every primary analysis) | 4 |

Facts of the reading set (from the manifest): all 6 scans whose expert-mask reference is "DIS not
met" are in it; all 4 device-default errors are in it; 2,455 expert lesions in total. **Known
imbalance:** controls are heavier in lesion burden (tertiles low / middle / high: non-unanimous
28 / 16 / 4, controls 8 / 11 / 17 — only 8 low-burden unanimous scans exist among eligible
patients); hence R1b and the stratified reporting.

**Sample size justification.** The size is bounded by the data (48 non-unanimous scans exist) and by
reader time (§9). Power of R1, 48 non-unanimous versus 36 control scans, Monte Carlo
(`research/paper_d/reader_power.py`, seed 20261031, record `records/reader_power_record.json`):

| R1a — exact Fisher (4,000 runs) | Power |
|---|---|
| reader non-unanimity 20 % vs 5 % | 0.56 |
| 25 % vs 5 % | 0.77 |
| 30 % vs 8 % | 0.77 |
| 35 % vs 10 % | 0.82 |

| R1b — adjusted for log lesion count (1,500 runs; real lesion counts; burden effect odds ratio 0.6–1.0 per SD) | Resulting rates | Power R1b | Power R1a, same runs |
|---|---|---|---|
| stratum odds ratio 3 | 16–20 % vs 5–6 % | 0.40–0.41 | 0.31–0.58 |
| stratum odds ratio 4 | 21–25 % vs 5–6 % | 0.57–0.60 | 0.51–0.78 |
| stratum odds ratio 6 | 28–33 % vs 5–6 % | 0.80 | 0.81–0.94 |

Plausibility (our calculation): with Fleiss κ ≈ 0.6 for DIS (Mahmoudi et al. 2026) and 70 % "met",
pairwise agreement is ≈ 0.83 and about 25 % of scans would show a three-reader split; our non-unanimous scans (low burden, 88 % "met" by the reference)
should be near that, our high-burden controls far below it. The study is therefore adequately
powered (≥ 0.8) for R1a only if the difference is about 30 % vs 5 % or larger; a smaller true effect
may be missed, and R1b is under-powered. This is stated in the paper. R2 precision: a 5 % flip rate
on 84 scans has a 95 % interval of roughly ±5 points.

## 4. Data and case package

- Images per case: FLAIR, T1 and T2 as distributed (MNI152 1 mm, skull-stripped; MSLesSeg CC-BY-4.0,
  Ljubljana CC-BY — redistribution to readers allowed with attribution; an `ATTRIBUTION.txt` is
  included). No clinical data, no file names from the source datasets: each case is a neutral code
  `RS-001 … RS-084` (`TR-1 … TR-4` for training).
- **Package 1** (sessions 1 and 3): images only.
- **Package 2** (session 2 only): for each case a lesion-label image of the expert mask (18-connected
  components ≥ 3 mm³, the grid's own labelling, ids as in the manifest), restricted to the lesions
  of Task 2. Package 2 is released only after the reader has locked Task 1, so the expert mask is
  never seen during the scan-level read.
- Each file's SHA-256 is embedded in the reading build and checked at load.

## 5. Reading platform — MSTool-AI research reading build (offline, local)

**Status: specified here, to be built and accepted before session 1 (agent work, ~2–3 days).**

- *What it is.* A separate single-page build of the MSTool-AI viewer component (niivue WebGL
  renderer), produced from a tagged commit and shipped as one self-contained HTML file plus the case
  packages. It contains **no** AI, atlas, region map, lesion count, DIS computation, login or backend.
  Title bar and every screen: "Research reading build — not a medical device — not for clinical use".
- *Offline.* Opened from the local disk in Chrome or Edge (Windows/macOS); case folder chosen with the
  browser's folder picker; Content-Security-Policy `connect-src 'none'` so no data can leave the
  machine; works with the network disabled.
- *Viewer.* Axial / coronal / sagittal, linked cross-hair, zoom/pan, window/level with FLAIR / T1 / T2
  presets, sequence switching, radiological-convention labels (R/L) on every view.
- *Task 1 screen.* The form of §6.1, a "lock case" button (answers become read-only), active reading
  time recorded per case, case order taken from `reading_orders.json` for that reader and session.
- *Task 2 screen.* One expert lesion at a time, outlined on FLAIR and centred in all three views,
  keyboard choice (§6.2), previous/next, progress bar.
- *Answers.* Autosaved locally after every answer (browser storage) and exported as one JSON file per
  session (`reader_<X>_session<N>.json`, schema in Appendix A); the reader e-mails the file to the
  coordinator or uploads it to a link the coordinator gives.
- **Acceptance tests (all must pass before session 1):** (1) all 88 cases load offline with the network
  disabled and no request in the browser's network log; (2) answers survive closing and reopening the
  browser; (3) exported files validate against the schema; (4) Task 2 lesion ids equal the manifest
  ids for every case (script check); (5) left/right and orientation correct on a test case with a
  known marker (the device had an orientation defect in one viewer, PRB-004 — this build must be
  checked against it); (6) a full dry run of one session by the coordinator, timed.
- *Fallback, only if acceptance fails:* ITK-SNAP (free, offline) with the same packages and an
  electronic form. Reported in the paper if used.

## 6. Reading instructions (given to readers verbatim, with the 4 training cases)

General: you see brain MRI of people with multiple sclerosis, already aligned to a standard brain
template and skull-stripped. There is no clinical information. Read as you would for the brain part
of the McDonald 2017/2024 dissemination-in-space criteria (Thompson et al. 2018; Montalban et al.
2025), using the lesion definitions of the MAGNIMS practical guidelines (Filippi et al. 2019): a
lesion is a focal T2/FLAIR hyperintensity, generally ≥ 3 mm in long axis; **periventricular** = in
contact with the **lateral** ventricles without intervening white matter (corpus callosum included;
not lesions in deep grey matter such as caudate or thalamus; lesions touching only the third or fourth
ventricle or the aqueduct do not count); **juxtacortical/cortical** = touching the cortex without
intervening white matter, or within the cortex, in any lobe or the cerebellum; **infratentorial** =
brainstem, cerebellar peduncles or cerebellum. Spinal cord and optic nerve are not available — judge
the brain only. Do not look for patterns between cases; read each case on its own.

### 6.1 Task 1 — scan-level read (sessions 1 and 3)
For each case: image quality (adequate / limited / non-diagnostic); periventricular lesions
(0 / 1 / 2 / ≥ 3); juxtacortical or cortical lesions (0 / 1 / ≥ 2); infratentorial lesions (0 / 1 /
≥ 2); **brain DIS met** (≥ 1 lesion in ≥ 2 of the three regions): yes / no; confidence in the DIS
answer (1 = guess … 5 = certain); optional comment (e.g. lesions you consider not typical of MS).
Lock the case to continue. Target ≈ 3 minutes per case; there is no time limit.

### 6.2 Task 2 — per-lesion region labels (session 2, ≥ 4 weeks after session 1)
For each outlined lesion choose every region that applies: **P** periventricular, **J**
juxtacortical/cortical, **I** infratentorial; or **D** none of these (deep or other white matter);
or **X** not a lesion / cannot judge. Optional flags: touches third or fourth ventricle; in deep grey
matter. A lesion may be J and I (cerebellar juxtacortical). Target ≈ 7 seconds per lesion.

## 7. Blinding and washout

- Readers do not see: any automated segmentation or decision, the atlas, the expert mask in Task 1,
  which case belongs to which stratum, the other readers' answers, or any interim result. Readers may
  know the overall design (this protocol is sent with the consent form and is public); knowing that
  the sample is enriched with difficult scans does not tell them which scans those are. The OSF
  registration may be public; the manifest is never published before all reads are locked.
- Order: an independent random order per reader and per session (`reading_orders.json`).
- **Washout ≥ 4 weeks** between session 1 (Task 1, all cases) and session 2 (Task 2); session 3
  (12 repeat Task 1 reads, interleaved in a new order) on the same day as session 2 or later, also
  ≥ 4 weeks after session 1. Memory effects in reader studies can be small (Hardesty et al. 2005);
  four weeks is the conventional minimum and is kept here because the repeat reads measure
  intra-reader agreement.
- Answers are locked per case; a reader cannot reopen a locked case. All files are frozen (SHA-256)
  before the coordinator links them to the strata (unblinding).

## 8. Reference standard and analysis

- **Reader reference:** majority (≥ 2 of 3) for brain DIS and for each region's presence (presence =
  count category ≥ 1). For lesions: per region, a lesion "counts as R" for the majority if ≥ 2
  readers ticked R. Scans rated non-diagnostic by ≥ 2 readers are excluded and listed. No consensus
  meeting is used for the primary reference.
- **Weights.** Population estimates for the 124-scan primary set (R2) weight non-unanimous scans by
  48/48 and controls by 76/36 (inverse sampling fraction); R1 is a within-sample comparison
  (unweighted).
- **Statistics.** R1a exact one-sided Fisher (α = 0.05); R1b logistic regression with log expert lesion
  count, one-sided likelihood-ratio test; patient-cluster bootstrap 95 % intervals (B = 2,000, seed
  20261031) for risk differences and odds ratios. R2 flip rates versus the majority with bootstrap
  intervals; leave-one-reader-out comparison (each reader versus the majority of the other two).
  R3: Fleiss κ (Fleiss 1971) with Gwet's AC1 and raw agreement, because κ is unstable when one answer
  dominates (Feinstein & Cicchetti 1990; Gwet 2008) — here about 90 % "met"; pairwise Cohen κ;
  intra-reader Cohen κ on the 12 repeats. R4: per-region Cohen κ and confusion tables (device rule,
  LST-AI rule, both at G0) against the majority, with bootstrap intervals clustered by scan. R5:
  sensitivity, specificity and predictive values with exact intervals. Reporting follows GRRAS
  (Kottner et al. 2011).
- **Secondary.** All analyses with the MAGNIMS 2016 periventricular rule (≥ 3 lesions; Filippi et al.
  2016) using the PV count category; by lesion-count tertile; contested scans only.
- No interim analysis. All pre-specified outcomes are reported.

## 9. Time per reader (estimate)

From the selected cases (`select_reader_cases.py`, planning assumptions 3 min per scan and 7 s per
lesion — to be re-measured on the training cases):

| Part | Content | Hours |
|---|---|---|
| Set-up and training | install, 4 training cases, questions | 0.75 |
| Session 1 — Task 1 | 84 scans × ≈ 3 min | 4.2 |
| Session 2 — Task 2 | 1,181 lesions × ≈ 7 s | 2.3 |
| Session 3 — repeats | 12 scans × ≈ 3 min | 0.6 |
| **Total** | | **≈ 7.8 (plausible range 6–10)** |

Session 1 may be split into two or three sittings within two weeks. If the training cases project
more than 10 hours, a pre-specified reduction applies before session 1: Task 2 limited to 5 lesions
per control scan and 25 per non-unanimous scan (seeded). Calendar: about 8 weeks from session 1 to
the end of session 3.

## 10. Ethics, data protection and regulatory status

- **Patient data.** Public, irreversibly anonymised data released for research under CC-BY licences
  (MSLesSeg: collected with the approval of Comitato Etico Catania 2, prot. 810/C.E., patients
  consented to publication of the anonymised data; Guarnera et al. 2025. Ljubljana: CC-BY, Lesjak
  et al. 2018). No data can be linked to a person.
- **Germany — professional duty of physicians.** The physicians' professional codes require a
  consultation by an ethics committee before taking part in research "bei dem in die psychische oder
  körperliche Integrität eines Menschen eingegriffen oder Körpermaterialien oder Daten verwendet
  werden, die sich einem bestimmten Menschen zuordnen lassen" (Berufsordnung für die Ärzte Bayerns
  § 15 Abs. 1, consolidated text read 2026-10-31; the 2026 amendment of the model code changed only
  the Helsinki reference of § 15). Anonymous public images are not data attributable to a person, and
  the readers' own answers are professional judgements, not health data about them. **Our reading:**
  no formal ethics vote is required. **But** practice in German neuroradiology is to obtain a written
  statement from an ethics committee, and journals often ask for one. **Recommendation:** each reader
  (the duty is the physician's) asks their own institution's ethics committee, or the lead reader asks
  once, using the short inquiry in Appendix B; committees typically confirm in a few weeks, sometimes
  for a small fee. This runs in parallel with building the reading software and does not delay
  session 1 if started at acceptance.
- **EU data protection (GDPR).** Reader identities linked to their ratings are personal data:
  pseudonyms (Reader A/B/C) in all files; written consent of each reader to the processing (Appendix
  C); names appear in the paper only as authors or in the acknowledgements, with consent; ratings are
  published only if all three agree.
- **Medical-device regulation.** No patient is involved and no clinical decision is taken; the
  reading build is a research tool, not the device. To be confirmed in the device's quality system
  (the owner), not assumed here.

## 11. Authorship and acknowledgement

- Readers who (1) do the reads and contribute to the interpretation, (2) review the manuscript
  critically, (3) approve the final version and (4) agree to be accountable meet the four ICMJE
  criteria and are **co-authors** (ICMJE Recommendations, updated April 2025). CRediT roles:
  Investigation; Writing – review & editing (and others if applicable).
- A reader who does the reads but does not wish to, or cannot, meet criteria 2–4 is named in the
  acknowledgements, with consent.
- Author order: to be agreed in writing before session 1. No payment is offered (the study has no
  funding); this is stated in the invitation.

## 12. Data management

Answer files are stored by the coordinator in the research project's private storage (never in the
production system), hashed on receipt, merged by a script, and frozen before unblinding. Case
packages are deleted by readers after session 3.

## 13. Timeline

Invitations → acceptance (≤ 2 weeks) → reading build + ethics inquiry (≤ 4 weeks) → OSF time stamp →
session 1 (2 weeks) → washout (≥ 4 weeks) → sessions 2–3 (2 weeks) → analysis (1 week) → manuscript
to readers (2 weeks).

## 14. Changes after time-stamping

*(empty)*

---

## Appendix A — answer file schema (summary)

`{reader, session, build_commit, started_at, cases: [{code, locked_at, active_seconds, quality,
pv: "0|1|2|3+", jc: "0|1|2+", it: "0|1|2+", dis: true|false, confidence: 1..5, comment,
lesions: [{id, regions: ["P","J","I"] | ["D"] | ["X"], flags: ["third_fourth_ventricle",
"deep_grey"]}]}]}`

## Appendix B — Anfrage an die Ethik-Kommission (Vorlage, Deutsch)

> Betreff: Anfrage zur Beratungspflicht nach § 15 Berufsordnung — retrospektive Readerstudie an
> öffentlich verfügbaren, anonymisierten MRT-Daten
>
> Sehr geehrte Damen und Herren,
>
> ich beabsichtige, als Neuroradiologin/Neuroradiologe an einer Readerstudie teilzunehmen. Drei
> Neuroradiologen beurteilen 84 öffentlich verfügbare, irreversibel anonymisierte MRT-Untersuchungen
> von Patientinnen und Patienten mit Multipler Sklerose (Datensätze MSLesSeg und Ljubljana 3D MS
> Database, beide unter CC-BY-Lizenz veröffentlicht; ursprüngliche Ethikvoten der Datengeber liegen
> vor) hinsichtlich der räumlichen Dissemination nach den McDonald-Kriterien. Es werden keine
> Patientinnen oder Patienten einbezogen, keine personenbezogenen Gesundheitsdaten verarbeitet und
> keine klinischen Entscheidungen getroffen. Die Ergebnisse der Reader werden pseudonymisiert
> ausgewertet; die Reader willigen schriftlich ein. Das Studienprotokoll liegt bei.
>
> Ich bitte um Mitteilung, ob für dieses Vorhaben eine Beratung nach § 15 der Berufsordnung
> erforderlich ist, bzw. um eine kurze schriftliche Bestätigung, dass keine Beratungspflicht besteht.
>
> Mit freundlichen Grüßen
> [Name, Institution]

## Appendix C — reader consent (short; EN, DE version supplied with the invitation pack)

I agree to take part as a reader in the paper D reader study; I understand that my ratings are
stored under a pseudonym, analysed by the study team, and published only with the agreement of all
readers; that my name appears only as an author or in the acknowledgements, as I choose; and that I
can withdraw before the analysis without giving a reason. — Name, date, signature.

## References

Feinstein & Cicchetti 1990; Filippi et al. 2016, 2019; Fleiss 1971; Guarnera et al. 2025; Gwet
2008; Hardesty et al. 2005; Kottner et al. 2011; Lesjak et al. 2018; Mahmoudi et al. 2026; Montalban
et al. 2025; Thompson et al. 2018 — full entries with DOIs in `manuscript/manuscript.md`. ICMJE:
<https://www.icmje.org/icmje-recommendations.pdf> (updated April 2025). Berufsordnung für die Ärzte
Bayerns § 15: consolidated text via <https://www.ethikkommission.fau.de/files/2016/09/Berufsordnung_5_2016.pdf>;
2026 model-code amendment: Bundesärztekammer synopsis of the 130th Deutscher Ärztetag (Stand
13.05.2026).
