# Cover letter — borrador para NeuroImage: Clinical (Elsevier)

Se sube como «Cover letter» en el sistema de envío de Elsevier.
**Antes de enviar:** rellenar cada `[DUEÑO: …]`, borrar esta cabecera y todas las notas entre corchetes, y firmar.

---

[DUEÑO: fecha del envío]

Dear Editor,

I am pleased to submit the research article **"FLAMeS had a higher lesion-wise F1 than three public CPU
segmenters on thick-slice FLAIR in multiple sclerosis: a pre-registered paired benchmark"** for
consideration in *NeuroImage: Clinical*.

**Why it matters for the journal's readers.** Clinical archives still hold many 2D FLAIR scans with 4–8 mm
slices, and public CPU tools designed for heterogeneous resolution are a natural choice for them. In a
benchmark registered in a public repository before any tool output existed, on five public cohorts with
expert masks (179 thick-slice and 145 1 mm scans), none of MindGlide, WMH-SynthSeg and SAMSEG had a higher
lesion-wise F1 than the FLAIR-only FLAMeS ensemble on thick-slice FLAIR, and the conservative tools'
fewer false lesions came at a large cost in sensitivity. We report this negative result, with every number
traced to committed files, so that clinical groups can choose tools for archive data on evidence.

**Statements.**

- The manuscript is original, has not been published, and is not under consideration elsewhere.
  [DUEÑO: confirmar; mencionar cualquier preprint.] Related manuscripts from the same research programme
  use some of the same public cohorts but ask different questions. [DUEÑO: decir si alguno está en revisión.]
- All authors approved the submission. [DUEÑO: lista de autores definitiva.]
- **Competing interests.** Nicolás Bonilla Vargas develops MSTool-AI, investigational MRI software for
  multiple sclerosis whose research pipeline uses FLAMeS, and is affiliated with Daita AI; the manuscript's
  conflict-of-interest statement gives the details. [DUEÑO: completar igual que esa declaración cuando
  confirme lo pendiente, y rellenar el formulario de intereses de Elsevier.]
- **Generative AI.** An AI coding agent (Claude Opus 5.5, Anthropic) was used as described in Methods,
  Section 2.1, and in the declaration placed immediately above the references, following Elsevier's policy.
  [DUEÑO: confirmar que revisó y asume la responsabilidad de todo el texto.]
- **Data and code.** All cohorts are public; per-scan metrics, analysis code and the pre-registration are in
  https://github.com/nicolasbonilla/medical-imaging-viewer. [DUEÑO: añadir el DOI del archivo.]
- **Ethics.** Secondary analysis of public, de-identified data; no new data were collected.
- **Open access.** I understand that the journal is fully open access and that an article publishing charge
  applies if the manuscript is accepted. [DUEÑO: confirmar antes de enviar; ver el coste en la lista de
  comprobación.]

**Suggested reviewers.** [DUEÑO: opcional — 3 a 5 especialistas en segmentación de lesiones de EM sin
conflicto de interés.]

Thank you for considering this manuscript.

Sincerely,

Nicolás Bonilla Vargas
Universidad Nacional de Colombia, Bogotá, Colombia; SRH University München, Munich, Germany; Daita AI
ngbonillav@unal.edu.co
[DUEÑO: firma]
