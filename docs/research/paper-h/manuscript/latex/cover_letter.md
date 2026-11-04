# Cover letter — borrador para Empirical Software Engineering (Springer)

Se sube como «Cover letter» en el sistema de envío de Springer.
**Antes de enviar:** rellenar cada `[DUEÑO: …]`, borrar esta cabecera y todas las notas entre corchetes, y firmar.

---

[DUEÑO: fecha del envío]

Dear Editors of *Empirical Software Engineering*,

I submit the manuscript **"Evidence That Can Fail: An AI Coding Agent as Primary Developer of
IEC 62304 Class C Medical-Imaging Software — A Single-Case Study of Verification, Review and
Approval"** for consideration as a research article.

**What the paper contributes.** It is, to my knowledge, the first empirical case study of an AI
coding agent acting as the primary developer of software built under a formal medical-device
lifecycle (IEC 62304 Class C, with ISO 14971 risk management), in which the regulatory records
themselves are the data. Over eleven months of repository history, it quantifies how the agent's
verification evidence failed (33 coded episodes), what detected those failures (mutation-based
negative controls, real-browser checks, independent review sessions), how often approval records
could be attributed to the human approver, and which incidents no verification step could see. All
analysis scripts, coding sheets and a redacted repository snapshot are public, and every number in
the paper is re-derived by a script.

**Why this journal.** The study follows the case-study guidelines common in empirical software
engineering (research questions, units of analysis, data triangulation, threats to validity) and
speaks to the journal's readers who study LLM-based software engineering, testing and process in
regulated domains.

**Statements.**

- The manuscript is original, has not been published, and is not under consideration elsewhere.
  [DUEÑO: confirmar; mencionar cualquier preprint, p. ej. arXiv.]
- I am the sole author [DUEÑO: o la lista de coautores] and I approve the submission.
- **Competing interests.** I own the product studied (MSTool-AI), operated the agent and approved the
  changes studied; I am also affiliated with Daita AI. The agent studied is a commercial product of
  Anthropic. [DUEÑO: completar igual que las declaraciones del artículo cuando confirme lo pendiente:
  rol en Daita AI, participación, patentes, relación con Anthropic.]
- **Ethics.** The study analyses my own engineering records; no other human participant, no patient
  data and no production data are involved (Section 8 of the manuscript). [DUEÑO: confirmar que su
  institución no exige aprobación de un comité de ética.]
- **Use of AI.** The same agent family that is studied wrote most of the product's code and records,
  the analysis scripts and the first draft of this manuscript, under my direction. Springer Nature
  asks that the use of large-language models be documented in the methods section; the manuscript
  documents it in Section 4 (the agent as single coder) and in its Declarations. [DUEÑO: confirmar que
  revisó y asume la responsabilidad de cada frase.]
- **Data and code availability.** Public repository
  https://github.com/nicolasbonilla/medical-imaging-viewer (pinned commits `6209131` and `8805882`;
  folder `research/paper_h/`). [DUEÑO: añadir el DOI del archivo.]

**Suggested reviewers.** [DUEÑO: opcional — 3 a 5 investigadores en estudios empíricos de asistentes de
programación con IA o de procesos de software crítico, sin conflicto de interés.]

Thank you for considering this manuscript.

Sincerely,

Nicolás Bonilla Vargas
Universidad Nacional de Colombia, Bogotá, Colombia; SRH University München, Munich, Germany; Daita AI
ngbonillav@unal.edu.co
[DUEÑO: firma]
