# MSSEG-2 data access — procedure, terms, request text and checklist (paper C)

*Research document, not the medical device. Written 2026-10-31. Every procedure step, URL and term
below was read on the official pages on 2026-10-31 (sources in §9). Nothing has been requested yet;
no MSSEG-2 image, mask or derived number has been seen by anyone working on this repository.*

> **Resumen en español sencillo.** Para la parte principal del artículo C hacen falta las imágenes
> públicas del concurso MSSEG-2 (pacientes con esclerosis múltiple escaneados dos veces, de hospitales
> franceses del registro OFSEP). Se piden con una cuenta gratuita en la plataforma Shanoir y aceptando
> un acuerdo de uso de datos. **Lo que tienes que hacer tú está en el §8: rellenar un formulario de
> 4 casillas y enviar un correo ya escrito.** Dos cosas importantes que descubrimos al leer el acuerdo:
> (1) con esa cuenta solo se reciben **40 pacientes** (de ellos unos **11 estables**), no los 28
> estables que decían nuestras notas anteriores: los otros 60 pacientes del concurso no son públicos,
> y el correo pide permiso para usarlos; (2) el acuerdo **prohíbe el uso comercial de los datos y de
> cualquier producto derivado**, así que ningún número calculado con MSSEG-2 podrá ir dentro de la
> aplicación sin un permiso aparte de OFSEP. El correo lo dice abiertamente.

---

## 1. What MSSEG-2 is (verified facts)

From the official challenge pages and the official dataset/challenge paper (Masson et al., *Sci Rep*
2026, doi:10.1038/s41598-026-52150-1, PMC13402319):

| Item | Fact |
|---|---|
| Patients | 100 MS patients, one pair of 3D FLAIR scans each (two time points, 70–1,187 days apart, mean 395) |
| Origin | OFSEP (French MS registry), 15 scanners of 3 vendors (Siemens, Philips, GE), 10 centres; 7 scanners at 1.5 T, 8 at 3 T; voxel sizes 0.5–1.2 mm |
| Delivered as | NIfTI; both time points registered to a middle space; no names, ages or dates in files |
| Ground truth | **new lesions only** — growing lesions were deliberately omitted; four neuroradiologists delineated, a senior neuroradiologist adjudicated lesions found by fewer than three; lesions < 3 mm discarded |
| Split | **40 training patients — the only part distributed** (study "MSSeg2" on Shanoir); 60 test patients **not distributed** (the paper's data-availability statement covers the training data only; a 2026 paper states "The 60-subject test partition lacks public ground-truth labels") |
| Patients without new lesions | 36 of 100 overall (36 + 17 with one + 47 with more than one = 100); 25 of the 60 test patients (revised ground truth). Hence **11 of the 40 training patients** by subtraction (the post-challenge revision concerned the test set only) — an inference, to be confirmed from the downloaded truth masks before any analysis |
| Test-set ground truth | revised after the challenge (81 lesions added after review of 395 method-detected candidates) |
| Case-wise test results | published on Zenodo (record 5552675) for the challenge methods and the four experts |

**Consequence for paper C.** The pilot notes (`RESULTS.md` §7, `APP-FEATURE.md` §5) planned on "28
stable patients" — that is the test set under the original ground truth, which is not distributed.
With the public training set the study has **≈ 11 stable and ≈ 29 active patients**. The
pre-registration (`PREREGISTRATION_C.md`) is therefore written for two scenarios fixed in advance:
S1 = training set only (default), S2 = training + test set (only if OFSEP/Inria grant the test set
with its revised ground truth). The request in §6 asks for the test set.

## 2. Current access procedure (official, read 2026-10-31)

Official page: <https://portal.fli-iam.irisa.fr/msseg-2/data/>

1. **Request a Shanoir account for the challenge** at <https://shanoir.irisa.fr/shanoir-ng/challenge-request>
   ("select the MSSEG-2 challenge and fill in your details in the form to send your account
   request"). The form (Shanoir-NG source code, `account-request` component, read 2026-10-31) asks
   for: **first name, last name, e-mail, institution / employer** (≤ 200 characters) and the
   **study** (MSSEG-2). There is no free-text field for a motivation — hence the separate e-mail
   in §6.
2. An administrator validates the request; Shanoir sends an e-mail when the account is active
   (Shanoir-NG front-end text: "An email has been sent to the administrator who will validate your
   request. You will receive an email once your account activated.").
3. Log in and **accept the data usage agreement (DUA)** in Shanoir before the training set opens.
   The DUA is published as a PDF:
   <https://portal.fli-iam.irisa.fr/files/2021/03/OFSEP_MRI_Data_Access_Agreement_MICCAI_2021.pdf>
   ("Access to OFSEP MRI used for the MICCAI 2021 challenge", March 2021, 3 pages).
4. **Download** the training set as one zip file (about 6 GB; the page warns the download can take
   from 5 minutes to several hours to start). The zip contains a `README.md` describing the data.
5. Questions: **challenges-iam@inria.fr** (challenge platform). OFSEP contacts named in the DUA:
   **projects@ofsep.org** (projects, commercial-use questions, extensions) and
   **publications@ofsep.org** (notification of publications).

Documents needed: none to upload. What is needed is a **professional e-mail address** in the
requester's own name (DUA clause 6) and the **institution** to register (it may be cited on the
OFSEP website).

## 3. The terms (DUA clauses, verbatim where short)

By accepting, the requester "become[s] the data controller (as defined under the European GDPR)" of
the data accessed. The clauses:

1. Comply with the rules of one's institution and government; the DUA never overrides applicable
   data-protection law.
2. No attempt to identify participants or link the data to other databases; never request the
   pseudonymisation key; accept no additional information about individual participants.
3. **No redistribution and no shared access**, "unless they have independently applied and been
   granted access … This includes individuals in my institution."
4. Secondary or derivative data (statistical maps, learnt models, templates) may be shared only "on a
   group level, and information from individual participants cannot be deduced."
5. Reference the data source in every paper or presentation (acknowledgement and citations below);
   providers are not liable for results.
6. Register the institution; **register with a professional e-mail address**.
7. Right of use for **3 years** from the grant date; extension on request (projects@ofsep.org),
   otherwise delete the data.
8. **"I will not use this data or a derivative product of it for a commercial use"** — if looking
   for commercial use "or unsure, please contact OFSEP (projects@ofsep.org)."
9. Inform OFSEP of each publication (publications@ofsep.org).
10. Agree to be contacted by OFSEP about the progress of the work.
11. Breach ends access.

**Terms of use — text to put in the paper** (verbatim from the DUA):

- *Methods:* "Data were generated by participating neurologists in the framework of Observatoire
  Français de la Sclérose en Plaques (OFSEP), the French MS registry (Vukusic et al. 2020). They
  collect clinical data prospectively in the European Database for Multiple Sclerosis (EDMUS) software
  (Confavreux et al. 1992). MRI of patients were provided as part of a care protocol. Nominative data
  are deleted from MRI before transfer and storage on the Shanoir platform (Sharing NeurOImaging
  Resources, shanoir.org)."
- *Acknowledgements:* "This work was carried out in collaboration with The Observatoire Français de la
  Sclérose en Plaques (OFSEP), who is supported by a grant provided by the French State and handled by
  the "Agence Nationale de la Recherche," within the framework of the "Investments for the Future"
  program, under the reference ANR-10-COHO-002, by the Eugène Devic EDMUS Foundation against multiple
  sclerosis and by the ARSEP Foundation."
- *Citations:* Vukusic et al., *Mult Scler* 2020;26(1):118–122 (doi:10.1177/1352458518815602);
  Confavreux et al., *J Neurol Neurosurg Psychiatry* 1992;55:671–676 (doi:10.1136/jnnp.55.8.671);
  the challenge dataset paper (Masson et al., *Sci Rep* 2026, doi:10.1038/s41598-026-52150-1) and the
  challenge proceedings (Commowick et al., MSSEG-2 challenge proceedings, MICCAI 2021).

## 4. How this study complies (binding on everyone working on paper C)

| DUA clause | What we do |
|---|---|
| 1, GDPR controller | The owner is the controller. Data stay on the owner's encrypted machine and, only if the FLAMeS step needs the cloud, in a bucket of the research project `mstool-research` readable only by the owner's account, deleted after the run. Never in the production project, never in git. |
| 2 | No linkage, no request for any per-patient information; no attempt to obtain scanner or date per patient. |
| 3 | No redistribution. Readers, co-authors or helpers who need the images apply for their own access. The AI coding agent only runs scripts on the owner's machine and sees their **group-level printouts** — no image, mask or per-patient table is printed, committed or uploaded. |
| 4 | Only group-level results are committed or published (counts, rates, intervals, thresholds as summary statistics). Per-patient caches live in the git-ignored `research/paper_c/.cache/` and are deleted with the data. |
| 5 | Methods text, acknowledgement and citations of §3 go into the manuscript (already in `manuscript/manuscript.md`). |
| 6 | Professional e-mail in the owner's name; institution as in §5. |
| 7 | Calendar reminder at 2 years 9 months; delete or request an extension. |
| **8** | **No commercial use of the data or of anything derived from it.** In particular, no threshold, calibration table, model or figure computed on MSSEG-2 enters the MSTool-AI software. The app feature (`APP_FEATURE_SPEC.md`) must be calibrated on data whose licence allows it (e.g. a customer's own data under their agreement), unless OFSEP grants a separate written permission. The e-mail in §6 says this and asks OFSEP to confirm. |
| 9, 10 | Preprint and paper references sent to publications@ofsep.org; answer OFSEP follow-up. |

## 5. Form values to paste (Shanoir challenge request)

| Field | Value |
|---|---|
| First name | Nicolás *(as in your identity documents)* |
| Last name | Bonilla Vargas |
| E-mail | **your professional address in your own name** (e.g. `nombre@mstool-ai.com`) — not Gmail and not the shared `contact@mstool-ai.com` (clause 6 asks for *your* professional address) |
| Institution / Employer | `MSTool-AI (independent research and software development)` — if MSTool-AI is a registered company, write its exact legal name instead |
| Study | MSSEG-2 (shown as "MSSeg2" in Shanoir) |

## 6. E-mail to send the same day (one message, English; French version below)

**To:** projects@ofsep.org · **Cc:** challenges-iam@inria.fr
**Subject:** MSSEG-2 data access request (Shanoir) — research-only use; disclosure of a commercial affiliation; question about the test set

> Dear OFSEP team, dear MSSEG-2 organisers,
>
> I have just requested a Shanoir account for the MSSEG-2 challenge data. Before accepting the data
> usage agreement I would like to be fully transparent about who I am and what I intend to do, and
> to ask two questions.
>
> **Who I am.** I am Nicolás G. Bonilla Vargas. I develop MSTool-AI, a software tool for MS MRI
> analysis that is intended to become a commercial medical device; it is not in clinical use. I also
> carry out methodological research that I publish openly. I am not affiliated with a university.
>
> **What I would do with the data (research only).** A methodological study, pre-registered on OSF
> before I see any image: can an automated follow-up analysis state a finite-sample,
> distribution-free bound on how often it calls a *new lesion* in a patient who has none? We would
> run a published open segmentation model (FLAMeS) on both time points, apply a simple rule for new
> lesions, and calibrate a threshold with conformal prediction, using the MSSEG-2 ground truth to
> measure the false-activity rate in the patients without new lesions. A pilot on other public data
> is complete. All results would be published (open access where possible), with the Methods text,
> acknowledgement and citations required by the terms of use, and OFSEP informed of each publication.
>
> **What I would not do.** I would not use the data, or anything derived from them (thresholds,
> calibration tables, trained models, figures computed on them), in MSTool-AI or any other product or
> service, and I would not redistribute or share the data. Only group-level results would be
> published. If OFSEP considers that the commercial nature of my main activity makes this request
> fall outside the "non-commercial use" of clause 8, please tell me — I would rather ask now than
> assume. If a separate agreement for any commercial use were ever wanted, I would contact you first.
>
> **Two questions.**
> 1. Is the planned use compatible with the data usage agreement, given the disclosure above?
> 2. Would it be possible to access the **60 test patients with the revised ground truth** for this
>    research-only study, under the same agreement (or to have the analysis run on your platform)?
>    The 11 or so training patients without new lesions are too few for the question we study; the
>    25 test patients without new lesions would make the result much more reliable. If this is not
>    possible, we will use the training set only, as pre-registered.
>
> Thank you for building and sharing this dataset.
>
> Kind regards,
> Nicolás G. Bonilla Vargas
> MSTool-AI — [professional e-mail] — [city, country]

**Version française (même contenu)**

> Objet : Demande d'accès aux données MSSEG-2 (Shanoir) — usage de recherche uniquement ; déclaration
> d'une activité commerciale ; question sur le jeu de test
>
> Madame, Monsieur, chère équipe OFSEP, chers organisateurs de MSSEG-2,
>
> Je viens de demander un compte Shanoir pour les données du challenge MSSEG-2. Avant d'accepter
> l'accord d'utilisation des données, je souhaite être entièrement transparent sur ma situation et
> sur mon projet, et vous poser deux questions.
>
> **Qui je suis.** Je m'appelle Nicolás G. Bonilla Vargas. Je développe MSTool-AI, un logiciel
> d'analyse d'IRM dans la sclérose en plaques destiné à devenir un dispositif médical commercial ; il
> n'est pas utilisé en clinique. Je mène aussi des travaux de recherche méthodologique publiés
> ouvertement. Je ne suis pas rattaché à une université.
>
> **Ce que je ferais des données (recherche uniquement).** Une étude méthodologique, pré-enregistrée
> sur OSF avant de voir la moindre image : une analyse automatique du suivi peut-elle garantir, avec
> une borne valable en échantillon fini et sans hypothèse de distribution, la fréquence à laquelle
> elle annonce une *nouvelle lésion* chez un patient qui n'en a pas ? Nous appliquerions un modèle de
> segmentation publié et ouvert (FLAMeS) aux deux examens, une règle simple pour les nouvelles
> lésions, puis un seuil calibré par prédiction conforme, la vérité terrain de MSSEG-2 servant à
> mesurer le taux de fausse activité chez les patients sans nouvelle lésion. Un pilote sur d'autres
> données publiques est terminé. Tous les résultats seraient publiés (en accès ouvert si possible),
> avec le texte de Méthodes, les remerciements et les citations demandés, et l'OFSEP serait informé
> de chaque publication.
>
> **Ce que je ne ferais pas.** Je n'utiliserais ni les données ni aucun produit dérivé (seuils, tables
> de calibration, modèles entraînés, chiffres calculés sur ces données) dans MSTool-AI ni dans aucun
> autre produit ou service, et je ne redistribuerais ni ne partagerais les données. Seuls des
> résultats agrégés seraient publiés. Si l'OFSEP estime que la nature commerciale de mon activité
> principale place cette demande hors de « l'usage non commercial » de la clause 8, merci de me le
> dire : je préfère poser la question maintenant. Si un usage commercial était un jour envisagé, je
> vous contacterais d'abord pour un accord séparé.
>
> **Deux questions.**
> 1. L'usage prévu est-il compatible avec l'accord d'utilisation des données, compte tenu de ce qui
>    précède ?
> 2. Serait-il possible d'accéder aux **60 patients du jeu de test avec la vérité terrain révisée**
>    pour cette étude de recherche uniquement, sous le même accord (ou de faire tourner l'analyse sur
>    votre plateforme) ? La onzaine de patients d'entraînement sans nouvelle lésion est trop peu
>    nombreuse pour notre question ; les 25 patients de test sans nouvelle lésion rendraient le
>    résultat bien plus fiable. Si ce n'est pas possible, nous utiliserons uniquement le jeu
>    d'entraînement, comme pré-enregistré.
>
> Merci d'avoir constitué et partagé ce jeu de données.
>
> Bien cordialement,
> Nicolás G. Bonilla Vargas
> MSTool-AI — [adresse e-mail professionnelle] — [ville, pays]

*Why both languages:* OFSEP and Inria are French institutions; the English text is the reference,
the French copy is a courtesy. Send one e-mail with the English text first and the French text
below it.

## 7. What happens after access (agent work, no owner action)

1. Post `PREREGISTRATION_C.md` on OSF **before** downloading (or, at the latest, before unzipping);
   record the OSF timestamp in the repository.
2. Download; verify the README; run the truth-only inventory (number of patients with and without
   new lesions) — the only look at the data before the detector runs, exactly as in the pilot.
3. Preprocessing with the organisers' published script, FLAMeS 5-fold on both time points (local CPU
   or the `mstool-research` project only), candidate extraction, pre-registered analysis.
4. Group-level results committed; per-patient caches stay git-ignored and are deleted with the data.

## 8. Lista de pasos para el dueño (español sencillo)

1. **Ten a mano un correo profesional a tu nombre** (por ejemplo `tunombre@mstool-ai.com`). El acuerdo
   pide un correo profesional propio; no sirve Gmail ni el buzón compartido `contact@`.
2. **Abre** <https://shanoir.irisa.fr/shanoir-ng/challenge-request>, elige **MSSEG-2** y rellena las
   cuatro casillas con los valores del §5 (nombre, apellidos, correo profesional, institución).
   Pulsa "Request Account".
3. **El mismo día envía el correo del §6** (copiar y pegar; pon tu correo profesional y tu ciudad al
   final) a `projects@ofsep.org` con copia a `challenges-iam@inria.fr`. Ese correo dice la verdad:
   que desarrollas un producto comercial, que los datos solo se usarán para investigar y que nada
   calculado con ellos irá a la aplicación. También pide los 60 pacientes de prueba.
4. **Espera dos correos**: el de Shanoir activando la cuenta y la respuesta de OFSEP. **No aceptes
   el acuerdo en Shanoir hasta tener la respuesta de OFSEP** si en ella te ponen alguna condición.
   Si OFSEP dice que no por el carácter comercial, para aquí y avísame: buscaremos otro camino
   (no hay que insistir ni reformular la petición para esquivarlo).
5. Cuando esté todo bien, **acepta el acuerdo en Shanoir y avísame**. A partir de ahí lo hago yo:
   publicar el pre-registro en OSF antes de abrir los datos, descargar, analizar.
6. **Pon un recordatorio a 2 años y 9 meses** desde la fecha de acceso: el permiso dura 3 años;
   antes de que venza hay que borrar los datos o pedir una prórroga a `projects@ofsep.org`.

Lo que **no** debes hacer: pasar los datos a nadie (ni siquiera a un colaborador: cada uno pide su
propio acceso), subirlos a GitHub o a la nube de producción, ni usar ningún número calculado con
ellos dentro de la aplicación.

## 9. Sources (all read 2026-10-31)

- MSSEG-2 data page: <https://portal.fli-iam.irisa.fr/msseg-2/data/> (steps, form link, DUA link,
  6 GB zip, contact).
- DUA PDF: <https://portal.fli-iam.irisa.fr/files/2021/03/OFSEP_MRI_Data_Access_Agreement_MICCAI_2021.pdf>
  (all clauses and terms of use quoted above).
- Shanoir-NG source code, account-request form fields and confirmation text:
  <https://github.com/fli-iam/shanoir-ng> (`shanoir-ng-front/src/app/users/account-request/`,
  `…/account-request-info/`), read through the GitHub API.
- Masson A, Combès B, Kerbrat A, et al. Performances of experts and automated methods on new
  multiple sclerosis lesions detection: insights from the MSSeg2 challenge. *Sci Rep* 2026;16.
  doi:10.1038/s41598-026-52150-1 (PMC13402319): dataset composition, ground-truth protocol, split,
  36 / 25 patients without new lesions, data-availability statement (training data on Shanoir,
  study "MSSeg2"; case-wise test results on Zenodo 5552675).
- Akhavan Aghdam M, et al. FORESEE-MS. arXiv:2610.36428 (2026), §3.1: "The 60-subject test partition
  lacks public ground-truth labels; therefore, we used only the 40 labeled training subjects."
- Schmidt-Mengin M, et al. *Front Neurosci* 2022;16:1004050 (doi:10.3389/fnins.2022.1004050): test
  patients "not available to the challengers"; 28 test patients without new lesions under the
  original ground truth.
- The count "11 training patients without new lesions" is an inference (36 − 25, both from Masson
  2026); a web search did not find an independent statement of it. It is confirmed or corrected by
  the truth-only inventory right after download (PREREGISTRATION_C.md §4).
