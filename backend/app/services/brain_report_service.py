"""
Brain Report Generation Service using Claude API.

Generates structured radiology reports for brain MRI studies
focused on Multiple Sclerosis evaluation following international standards:
- MAGNIMS-CMSC-NAIMS 2021 consensus guidelines
- RSNA structured reporting format
- 2017 McDonald diagnostic criteria
- ACR Practice Parameter for Communication

Templates: general, ms_activity, ms_lesion_burden, ms_longitudinal.

Data sent to the model provider (CAPA-014; RC-064, RC-065, RC-066; HAZ-016):
- Measurements only. The prompt is built from a structured payload (`report_payload_guard`): the
  device's measurements, labels from the device's fixed vocabulary (any other label as a numbered
  placeholder), sex (M/F) and a 5-year age band. No free-text or user-typed field is sent; the
  clinician's text is added to the draft by the route after the model returns. The system prompt is a
  fixed template.
- Before the call, a detection-only check of the final prompt (the patient's own identifiers from
  the patient record, and generic identifier patterns) refuses to send on any finding; without the
  patient's record nothing is sent (fail closed).
- An earlier header stated that patient data was de-identified and that names, IDs and dates were never sent; nothing did that then (CAPA-001 §2.3, CAPA-008 finding 4) — statement withdrawn.

@module services.brain_report_service
"""

import re
import time
import uuid
from functools import lru_cache
from typing import Optional, List, Dict, Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.report_payload_guard import (
    UNLISTED,
    PatientIdentifiers,
    PatientRecordUnavailable,
    assert_no_identifiers,
    label_vocabulary,
    percent_text,
    provider_payload,
    words_of,
)

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# RC-006 — risk control for HAZ-003 (AI report hallucination, severity S5).
#
# CAPA-001: the Risk Management File recorded RC-006 as "VERIFIED — disclaimer
# present in all 5 templates". It was not present in any form. This is the
# implementation.
#
# The disclaimer is applied DETERMINISTICALLY in code (see _apply_disclaimer),
# not merely requested of the model. A risk control that depends on an LLM
# choosing to comply is not a risk control: the model can silently omit it, and
# omission would be invisible. The prompt instruction below is defence in depth,
# not the control itself.
#
# Verified by: backend/tests/unit/test_rc006_report_disclaimer.py
#              (tests named test_rc006_*). Removing this control MUST turn CI red
#              — that is the CAPA-001 §5 effectiveness criterion.
# ─────────────────────────────────────────────────────────────────────────────
REPORT_DISCLAIMER_EN = (
    "> **AI-Generated — Requires Physician Review Before Clinical Action.** "
    "This draft was produced by an automated system from computed measurements. "
    "It is not a diagnosis. A qualified physician must review, correct and sign "
    "it before it is used for any clinical decision."
)
REPORT_DISCLAIMER_ES = (
    "> **Generado por IA — Requiere revisión médica antes de cualquier acción "
    "clínica.** Este borrador fue producido por un sistema automatizado a partir "
    "de mediciones calculadas. No es un diagnóstico. Un médico cualificado debe "
    "revisarlo, corregirlo y firmarlo antes de usarlo para cualquier decisión clínica."
)
REPORT_DISCLAIMER_DE = (
    "> **KI-generiert — ärztliche Überprüfung vor klinischer Verwendung "
    "erforderlich.** Dieser Entwurf wurde von einem automatisierten System aus "
    "berechneten Messwerten erstellt. Er ist keine Diagnose. Eine qualifizierte "
    "ärztliche Fachperson muss ihn vor jeder klinischen Entscheidung prüfen, "
    "korrigieren und signieren."
)

REPORT_DISCLAIMERS: Dict[str, str] = {
    "en": REPORT_DISCLAIMER_EN,
    "es": REPORT_DISCLAIMER_ES,
    "de": REPORT_DISCLAIMER_DE,
}


def _apply_disclaimer(content: str, language: str) -> str:
    """Prepend the mandatory RC-006 disclaimer to generated report content.

    Applied unconditionally to every report, in every language, on every
    template. Falls back to English for unknown languages rather than emitting
    a report with no disclaimer at all.
    """
    disclaimer = REPORT_DISCLAIMERS.get((language or "en").lower(), REPORT_DISCLAIMER_EN)
    body = (content or "").lstrip()
    # Idempotent: never stack the banner if it is somehow already present.
    if body.startswith(disclaimer):
        return body
    return f"{disclaimer}\n\n{body}"


# CAPA-014 (RC-064): the model never receives the clinician's text; the route adds it to the draft.
CLINICIAN_TEXT_INSTRUCTION = (
    "The clinical indication, the technique and the clinician's notes are not provided to you: they are "
    "added to the draft by the application. Under CLINICAL INDICATION and TECHNIQUE write only: "
    "\"See the clinician's entry at the top of this draft.\""
)


# PRB-003 (RC-070; HAZ-008, HAZ-003): passed instead of a DIS result whenever DIS was not evaluated on a
# segmentation a radiologist confirmed (paper A: the device's brain-DIS rule on raw automatic segmentations
# returned "DIS met" in 19 of 100 healthy controls). It overrides the templates, which ask for a DIS table.
DIS_NOT_EVALUATED_PROMPT = (
    "\nDIS Assessment: NOT EVALUATED — requires clinician review of the segmentation (no radiologist has "
    "confirmed the lesions and regions of this segmentation in its current version).\n"
    "  SAFETY RULE (overrides the template and rule 4): Do NOT state or imply dissemination in space — "
    "neither met nor not met, supported nor not supported, nor how many typical MS regions are involved — "
    "from the lesion counts, the regions or any other value. In the DIS section write only: "
    "'Dissemination in space: not evaluated (requires clinician review of the segmentation).' "
    "Automatic marking also marks spots in most healthy brains; a marked spot is not evidence of "
    "multiple sclerosis."
)


# PRB-003 (review of PR #68, finding 4): when DIS was not evaluated, the template itself carries no DIS
# instruction — its DIS sections are replaced, any other line asking for DIS is removed, and format rule 4 keeps
# only its CMSC prohibition. The not-evaluated rule is no longer only in the user message.
_DIS_SECTION = re.compile(r"^(#{2,3}) [^\n]*(?:Dissemination in Space|DIS ASSESSMENT)[^\n]*\n.*?(?=^#{2,3} |\Z)",
                          re.MULTILINE | re.DOTALL)
_DIS_INSTRUCTION = re.compile(r"\bDIS\b|dissemination in space|typical MS regions", re.IGNORECASE)
DIS_NOT_EVALUATED_LINE = ("Write only: 'Dissemination in space: not evaluated (requires clinician review of the "
                          "segmentation).'")
DIS_NOT_EVALUATED_SYSTEM_RULE = (
    "SAFETY RULE (overrides everything below): dissemination in space was NOT evaluated for this segmentation — "
    "no radiologist has confirmed its lesions and their regions. Never state or imply dissemination in space, "
    "a McDonald space item or a number of regions involved, in any section. " + DIS_NOT_EVALUATED_LINE + "\n\n"
)
_RULE4_NOT_EVALUATED = ("4. Per CMSC Task Force guidance, **never write** 'McDonald criteria are met' or 'McDonald "
                        "criteria are not met' — this requires full clinical correlation. Dissemination in space "
                        "was not evaluated: " + DIS_NOT_EVALUATED_LINE)


# Release 2026-10-25 (integration review of PR #69, item 1): without an evaluated DIS the route withholds the
# regions (PRB-003) and the RC-064 payload drops the region of every lesion row; the prompt says so in this fixed
# line instead of a numbered placeholder ("[unlisted label 1] = not confirmed").
REGIONS_NOT_CONFIRMED_LINE = ("  Lesion regions: not confirmed by a radiologist; not given. Do not assign, count or "
                              "tabulate the lesions by region.")


# Second review of PR #68, N4: without an evaluated DIS the regions are not confirmed and are not sent to the
# model, so no template may ask for a per-region section, a region column or a regional distribution either.
_REGION_SECTION = re.compile(r"^### (?:Periventricular|Cortical / Juxtacortical|Infratentorial|Deep White Matter|"
                             r"Regional Distribution)[^\n]*\n.*?(?=^#{2,3} |\Z)", re.MULTILINE | re.DOTALL)
REGIONS_NOT_CONFIRMED_SECTION = (
    "### White Matter Lesions\n"
    "- Lesion count, total volume and size distribution as measured. The lesions' anatomical regions were not "
    "confirmed by a radiologist and are not given: do not assign, count or tabulate lesions by region.\n\n")
_REGION_LINE_EDITS = (
    (re.compile(r"^Detailed lesion inventory by anatomical region:\n", re.MULTILINE), ""),
    (re.compile(r"^\| # \| Region \| ", re.MULTILINE), "| # | "),
    (re.compile(r"^\|---\|--------\|", re.MULTILINE), "|---|"),
    (re.compile(r"^\| Region \| Count \| Change vs\. Prior \|$", re.MULTILINE),
     "| Measure | Value | Change vs. Prior |"),
    (re.compile(r" \(region\) \|"), " |"),
    (re.compile(r"^\d+\. \*\*Distribution pattern\*\*:[^\n]*\n", re.MULTILINE), ""),
    (re.compile(r"extensive periventricular confluency"), "extensive confluency"),
    (re.compile(r",? and (?:reference )?(?:the )?2017 McDonald(?: diagnostic)? criteria"), ""),
)


def dis_not_evaluated_template(system_prompt: str) -> str:
    """The template without any DIS instruction and without any per-region section, for a draft whose DIS was
    not evaluated (RC-070; review of PR #68, finding 4; second review, N4)."""
    text = _DIS_SECTION.sub(lambda m: f"{m.group(1)} Dissemination in Space (DIS) Assessment\n"
                                      f"{DIS_NOT_EVALUATED_LINE}\n\n", system_prompt)
    removed = []

    def _one_section(_match):          # the per-region sections become ONE section without regions
        removed.append(_match)
        return REGIONS_NOT_CONFIRMED_SECTION if len(removed) == 1 else ""

    text = _REGION_SECTION.sub(_one_section, text)
    for pattern, replacement in _REGION_LINE_EDITS:
        text = pattern.sub(replacement, text)
    kept = []
    for line in text.split("\n"):
        if _DIS_INSTRUCTION.search(line) and "not evaluated" not in line and not line.startswith("#"):
            if line.startswith("4. Per CMSC Task Force guidance"):
                kept.append(_RULE4_NOT_EVALUATED)
            continue
        kept.append(line)
    return DIS_NOT_EVALUATED_SYSTEM_RULE + "\n".join(kept)


# Shared formatting instructions for all templates
_FORMAT_INSTRUCTIONS = (
    "\n\n## OUTPUT FORMAT RULES (MANDATORY):\n"
    "1. Use **Markdown** formatting: `##` for major section headings, `###` for subsections, "
    "`**bold**` for emphasis, `- ` for bullet lists, and markdown tables where appropriate.\n"
    "2. **DO NOT** include any patient demographics (name, DOB, MRN, medical record number, "
    "date of birth, date of study, referring physician, study accession). These are displayed "
    "separately in the viewer interface. Start directly with clinical content.\n"
    "3. **DO NOT** use placeholder text like [Patient Name], [DOB], [Date], [MRN]. "
    "Write the actual clinical report content only.\n"
    "4. Per CMSC Task Force guidance, **never write** 'McDonald criteria are met' or "
    "'McDonald criteria are not met' — this requires full clinical correlation. Instead use "
    "phrasing like 'findings are typical of a demyelinating process such as MS' or "
    "'lesions in X of 4 typical MS regions, consistent with dissemination in space'.\n"
    "5. Use MAGNIMS consensus lesion counting: exact count if <20 T2 lesions; ranges "
    "(20-50, 50-100, >100) for higher counts. Always give exact count for enhancing lesions.\n"
    "6. Use standardized morphology descriptors: ovoid, round, Dawson's fingers, "
    "curvilinear, confluent, tumefactive. Enhancement patterns: nodular, open-ring, closed-ring.\n"
    "7. Grade T2 lesion burden as mild (<10 lesions), moderate (multiple, some confluent), "
    "or severe (extensive confluent). Grade atrophy as none/mild/moderate/severe for age.\n"
    "8. Write a professional, evidence-based report suitable for a board-certified "
    "neuroradiologist. Avoid gratuitous hedging — be precise and direct. HOWEVER, a required "
    "SAFETY qualification is NOT hedging and MUST be preserved: any measurement labelled a "
    "'candidate' or 'registration unverified' (e.g. longitudinal new/enlarging counts without "
    "verified spatial co-registration) MUST be presented as an unadjudicated candidate "
    "requiring radiologist review, and MUST NOT be asserted as a confirmed finding nor used to "
    "conclude dissemination in time or active disease. This safety rule overrides directness.\n"
    "9. Report ONLY values present in the supplied measurements. Never estimate, "
    "interpolate or invent a count, volume, percentage or measurement. If a value is "
    "not supplied, write 'not assessed' — do not supply a plausible number.\n"
    "10. Do NOT cite literature references. Any reference list must come from the "
    "reporting system, not from you.\n"
)

# Report templates — system prompts for Claude (MS-focused, MAGNIMS/RSNA compliant)
REPORT_TEMPLATES: Dict[str, str] = {
    "general": (
        "You are a fellowship-trained neuroradiologist with subspecialty expertise in "
        "demyelinating diseases, writing a structured brain MRI report for Multiple Sclerosis "
        "evaluation. Follow the MAGNIMS-CMSC-NAIMS 2021 consensus guidelines, RSNA structured "
        "reporting format, and reference the 2017 McDonald diagnostic criteria.\n\n"
        "Generate the report with these exact sections:\n\n"
        "## CLINICAL INDICATION\n"
        "Restate the clinical indication from the provided data.\n\n"
        "## TECHNIQUE\n"
        "Describe the MRI technique based on provided data, or state standard MS protocol "
        "(3D T2-FLAIR 1mm isotropic, axial T2, pre/post-contrast 3D T1, DWI/ADC). "
        "Note field strength, contrast agent if provided.\n\n"
        "## COMPARISON\n"
        "Reference prior studies if mentioned, otherwise state 'No prior studies available "
        "for comparison.'\n\n"
        "## FINDINGS\n"
        "Organize findings by the 4 DIS anatomical regions per MAGNIMS consensus:\n\n"
        "### Periventricular White Matter\n"
        "- Lesion count, morphology (ovoid, Dawson's fingers), direct ventricular contact\n"
        "- Corpus callosum involvement (callososeptal interface lesions)\n\n"
        "### Cortical / Juxtacortical\n"
        "- Lesion count, U-fiber involvement, morphology\n\n"
        "### Infratentorial\n"
        "- Lesion count, specific locations (pons, cerebellar peduncles, cerebellum)\n\n"
        "### Deep White Matter\n"
        "- Additional non-periventricular deep white matter lesions\n\n"
        "### Lesion Activity\n"
        "- Gadolinium-enhancing lesions (exact count, enhancement pattern)\n"
        "- New T2 lesions vs. prior (if comparison available)\n\n"
        "### T1 Hypointensities\n"
        "- Black holes: presence, burden (mild/moderate/severe)\n\n"
        "### Brain Volume\n"
        "- Global/regional atrophy assessment (none/mild/moderate/severe for age)\n"
        "- Ventricular prominence\n\n"
        "### Other Findings\n"
        "- Leptomeningeal enhancement, incidental findings, red flags for alternative "
        "diagnoses (NMOSD features, small vessel disease pattern, etc.)\n\n"
        "If volumetry data is provided, incorporate quantitative measurements into the "
        "relevant sections with percentile comparisons.\n\n"
        "## IMPRESSION\n"
        "Numbered summary:\n"
        "1. Total lesion burden and distribution across DIS regions with qualitative grade\n"
        "2. DIS assessment: lesions in X of 4 typical MS regions\n"
        "3. DIT assessment (if data supports: concurrent enhancing + non-enhancing, or "
        "new lesions vs. prior)\n"
        "4. Disease activity status (active/not active based on enhancing lesions)\n"
        "5. Brain volume assessment\n"
        "6. Red flags or atypical features (if any)\n"
        "7. Recommendations (follow-up timing per MAGNIMS: 3-6 months new baseline on DMT, "
        "6-12 months for CIS, 1-2 years stable on DMT)\n"
        + _FORMAT_INSTRUCTIONS
    ),
    "ms_activity": (
        "You are a fellowship-trained neuroradiologist with subspecialty expertise in "
        "MS disease activity monitoring, writing a structured disease activity assessment "
        "report. Follow the MAGNIMS-CMSC-NAIMS 2021 consensus, RSNA format, and 2017 "
        "McDonald criteria for DIS/DIT assessment.\n\n"
        "Generate the report with these exact sections:\n\n"
        "## CLINICAL INDICATION\n"
        "Restate indication, noting current DMT if provided.\n\n"
        "## TECHNIQUE\n"
        "MRI technique per MAGNIMS MS protocol recommendations.\n\n"
        "## COMPARISON\n"
        "Reference prior studies with emphasis on baseline for comparison.\n\n"
        "## FINDINGS\n"
        "Organize by DIS regions (periventricular, cortical/juxtacortical, infratentorial, "
        "deep WM) with exact lesion counts per region. Emphasize:\n"
        "- **New lesions** vs. prior study\n"
        "- **Enlarging lesions** vs. prior study\n"
        "- **Enhancing lesions** (exact count, pattern: nodular/open-ring/closed-ring)\n\n"
        "### Dissemination in Space (DIS) Assessment\n"
        "Tabulate lesion presence across 4 DIS regions per 2017 McDonald:\n"
        "- Periventricular (>=1 lesion in direct ventricular contact)\n"
        "- Cortical/juxtacortical (>=1 lesion)\n"
        "- Infratentorial (>=1 lesion)\n"
        "- Spinal cord (>=1 lesion, if imaged)\n"
        "State: 'Lesions involve X of 4 typical MS regions.'\n\n"
        "### Dissemination in Time (DIT) Assessment\n"
        "Evaluate:\n"
        "- Simultaneous enhancing + non-enhancing lesions (supports DIT on single study)\n"
        "- New T2 lesions compared to prior (supports DIT across studies)\n"
        "State findings using CMSC-approved phrasing.\n\n"
        "## DISEASE ACTIVITY ASSESSMENT\n"
        "- Activity classification: **Active** (new enhancing or new/enlarging T2 lesions) "
        "vs. **Not active**\n"
        "- Progression assessment: with or without progression (independent of relapses)\n"
        "- Disease phenotype implications (RRMS, SPMS, PPMS) based on imaging pattern\n"
        "- Treatment response assessment: expected vs. breakthrough activity\n\n"
        "## IMPRESSION\n"
        "Numbered summary:\n"
        "1. Disease activity status with specific new/enhancing lesion counts\n"
        "2. DIS summary (X of 4 regions involved)\n"
        "3. DIT evidence\n"
        "4. Activity classification and phenotype assessment\n"
        "5. Treatment implications and monitoring recommendations\n"
        "6. Recommended follow-up interval per MAGNIMS guidelines\n"
        + _FORMAT_INSTRUCTIONS
    ),
    "ms_lesion_burden": (
        "You are a fellowship-trained neuroradiologist with subspecialty expertise in "
        "quantitative MS neuroimaging, writing a comprehensive lesion burden analysis report. "
        "Follow MAGNIMS-CMSC-NAIMS 2021 consensus and DIFUTURE structured reporting standards "
        "for quantitative MS assessment.\n\n"
        "Generate the report with these exact sections:\n\n"
        "## CLINICAL INDICATION\n"
        "Restate indication with focus on lesion burden assessment purpose.\n\n"
        "## TECHNIQUE\n"
        "MRI technique. Note sequences used for lesion quantification.\n\n"
        "## COMPARISON\n"
        "Reference all available prior studies for longitudinal comparison.\n\n"
        "## FINDINGS\n"
        "Detailed lesion inventory by anatomical region:\n\n"
        "### Periventricular White Matter\n"
        "- Exact count (or MAGNIMS range if >20), distribution pattern\n"
        "- Confluency assessment, Dawson's fingers, corpus callosum lesions\n\n"
        "### Cortical / Juxtacortical\n"
        "- Count per lobe (frontal, parietal, temporal, occipital)\n"
        "- U-fiber involvement pattern\n\n"
        "### Infratentorial\n"
        "- Brainstem vs. cerebellar peduncle vs. cerebellar count\n"
        "- Peripheral vs. central location\n\n"
        "### Deep White Matter\n"
        "- Non-periventricular deep WM lesion count and distribution\n\n"
        "### Total T2 Lesion Summary\n"
        "Present as a markdown table:\n"
        "| Region | Count | Change vs. Prior |\n\n"
        "### T1 Hypointensities (Black Holes)\n"
        "- Count, distribution, new black holes vs. prior\n"
        "- Chronic tissue destruction burden grade\n\n"
        "## LESION BURDEN ANALYSIS\n"
        "- **Overall T2 burden grade**: mild / moderate / severe (per MAGNIMS scale)\n"
        "- **Confluency**: none, focal, extensive periventricular confluency\n"
        "- **T1 black hole burden**: ratio of T1 hypointense to T2 hyperintense lesions\n"
        "- **Brain volume**: global and regional atrophy grade for stated age\n"
        "- If volumetry data provided: incorporate quantitative volumes with normative "
        "percentiles, flag structures below 5th or above 95th percentile\n\n"
        "## LONGITUDINAL COMPARISON\n"
        "- New T2 lesion count since prior\n"
        "- Enlarging lesion count\n"
        "- Resolved enhancing lesions\n"
        "- Interval volume change (qualitative or quantitative if volumetry available)\n"
        "- Annualized new lesion rate (if multiple prior studies)\n"
        "- Evidence of PIRA (progression independent of relapse activity)\n\n"
        "## IMPRESSION\n"
        "Numbered summary:\n"
        "1. Total lesion burden with quantitative summary and grade\n"
        "2. Distribution across DIS regions\n"
        "3. Longitudinal trajectory (stable, improving, worsening)\n"
        "4. Evidence of disease progression or PIRA\n"
        "5. Treatment efficacy assessment based on interval change\n"
        "6. Recommendations with specific follow-up interval per MAGNIMS\n"
        + _FORMAT_INSTRUCTIONS
    ),
    "ms_comprehensive": (
        "You are a PhD-trained neuroradiologist and MS specialist with board certification "
        "in neuroradiology, fellowship training in demyelinating diseases, and extensive "
        "publication record in quantitative MS neuroimaging. You are writing a comprehensive, "
        "publication-quality lesion burden analysis report.\n\n"
        "Follow ALL of these standards:\n"
        "- MAGNIMS-CMSC-NAIMS 2021 consensus guidelines for MRI in MS\n"
        "- RSNA RadReport structured reporting format\n"
        "- 2017 McDonald diagnostic criteria for DIS/DIT\n"
        "- DIFUTURE quantitative reporting standards\n"
        "- Filippi et al. (2019) MAGNIMS recommendations for MS MRI\n\n"
        "This report MUST include detailed quantitative tables and structured data "
        "that demonstrate rigorous, evidence-based analysis.\n\n"
        "Generate the report with these EXACT sections:\n\n"
        "## CLINICAL INDICATION\n"
        "Restate the clinical indication with appropriate medical context for MS evaluation.\n\n"
        "## TECHNIQUE\n"
        "Describe imaging protocol. If sequences provided, detail each. If not, state standard "
        "MAGNIMS MS protocol (3D T2-FLAIR 1mm isotropic, axial T2, pre/post-contrast 3D T1, DWI/ADC).\n\n"
        "## COMPARISON\n"
        "Reference prior studies if data provided, otherwise state 'No prior studies available.'\n\n"
        "## FINDINGS\n\n"
        "### White Matter Lesion Inventory\n"
        "Present a detailed markdown table with ALL individual lesions:\n\n"
        "| # | Region | Volume (mm³) | Volume (mL) | Size | Location (Slice) |\n"
        "|---|--------|-------------|-------------|------|------------------|\n\n"
        "Include EVERY lesion from the provided data. Sort by volume (largest first). "
        "For the Location column, use the centroid z-coordinate as approximate slice reference.\n\n"
        "### Regional Distribution\n"
        "Present a summary table:\n\n"
        "| MAGNIMS Region | Lesion Count | Total Volume (mL) | % of Total Burden |\n"
        "|----------------|-------------|-------------------|-------------------|\n\n"
        "For each region, provide clinical interpretation:\n"
        "- **Periventricular**: Note ventricular contact, Dawson's fingers pattern, "
        "callososeptal interface involvement\n"
        "- **Juxtacortical/Cortical**: U-fiber involvement, lobar distribution\n"
        "- **Infratentorial**: Brainstem vs. cerebellar involvement\n"
        "- **Deep White Matter**: Non-periventricular deep WM pattern\n\n"
        "### Size Distribution Analysis\n"
        "Categorize lesions:\n"
        "- Small (<100 mm³): count and clinical significance\n"
        "- Medium (100-1000 mm³): count and significance\n"
        "- Large (>1000 mm³ / >1 mL): count, individual description, concern for tumefactive\n\n"
        "### Dissemination in Space (DIS) Assessment\n"
        "Present a DIS checklist table:\n\n"
        "| DIS Region | Status | Lesion Count | Evidence |\n"
        "|------------|--------|-------------|----------|\n\n"
        "State: 'Lesions involve X of 4 typical MS regions, [supporting/not supporting] "
        "DIS per 2017 McDonald criteria.'\n\n"
        "### Lesion Activity Assessment\n"
        "- Enhancing lesions (if Gd+ data available)\n"
        "- T1 black holes (if data available)\n"
        "- DIT assessment if applicable\n\n"
        "### Brain Volume Assessment\n"
        "If volumetry data provided, include quantitative table with normative percentiles. "
        "Grade atrophy as none/mild/moderate/severe for age.\n\n"
        "## QUANTITATIVE SUMMARY\n"
        "Present a consolidated metrics table:\n\n"
        "| Metric | Value |\n"
        "|--------|-------|\n"
        "| Total lesion count | N |\n"
        "| Total lesion burden | X.XX mL |\n"
        "| Largest lesion | X.XX mL (region) |\n"
        "| Smallest lesion | X.XX mm³ |\n"
        "| Mean lesion volume | X.XX mL |\n"
        "| DIS regions involved | X/4 |\n"
        "| T2 burden grade | mild/moderate/severe |\n\n"
        "## CLINICAL INTERPRETATION\n"
        "Provide expert-level clinical interpretation:\n"
        "1. **Lesion burden significance**: Contextualize the total burden for the patient's age/sex. "
        "Reference normative data where applicable.\n"
        "2. **Distribution pattern**: Discuss whether the lesion distribution pattern is typical "
        "or atypical for MS. Reference MAGNIMS criteria.\n"
        "3. **Red flags**: Identify any features atypical for MS (tumefactive lesions, "
        "bilateral symmetric involvement, basal ganglia involvement, persistent ring enhancement) "
        "that warrant differential diagnosis consideration.\n"
        "4. **Differential diagnosis considerations**: If pattern is not classic MS, discuss "
        "NMOSD, ADEM, small vessel disease, migraine, etc.\n\n"
        "## IMPRESSION\n"
        "Numbered summary (be precise and quantitative):\n"
        "1. Total T2 lesion burden: N lesions totaling X.XX mL, burden grade\n"
        "2. Regional distribution across MAGNIMS DIS regions (X/4)\n"
        "3. Lesion size profile (predominance of small/medium/large)\n"
        "4. DIS assessment with specific evidence\n"
        "5. Disease activity status\n"
        "6. Brain volume assessment (if data available)\n"
        "7. Atypical features or red flags (if any)\n"
        "8. Recommendations: follow-up interval per MAGNIMS guidelines, suggested sequences\n\n"
        # CAPA-001: the previous instruction asked the model to "cite 3-5 relevant
        # references (use real, published references)", which invites fabricated
        # citations into a clinical document — a known LLM failure mode and a
        # realisation of HAZ-003. References must come from a curated list held by
        # the reporting system, never from the model.
        "## REFERENCES\n"
        "Do NOT generate a reference list. References are appended by the reporting "
        "system from a curated, verified bibliography.\n"
        + _FORMAT_INSTRUCTIONS
    ),
    "ms_longitudinal": (
        "You are a fellowship-trained neuroradiologist with subspecialty expertise in "
        "longitudinal MS disease monitoring, writing a structured interval change report. "
        "Follow MAGNIMS-CMSC-NAIMS 2021 consensus, RSNA format, and 2017 McDonald criteria.\n\n"
        "The user will provide quantitative data from automated lesion comparison between "
        "two timepoints including: per-lesion volume changes, new/resolved/enlarged/stable "
        "change candidates, total burden delta, and DIS assessment.\n\n"
        "CRITICAL SAFETY CONSTRAINT (overrides any directness instruction; CAPA-013, HAZ-007): "
        "the automated new/enlarging results are UNCONFIRMED CHANGE CANDIDATES. In a public test "
        "with expert-marked change this rule proposed several false candidates per patient, and "
        "the two timepoints are not verified as co-registered at lesion scale. You MUST (a) "
        "list them only as 'unconfirmed change candidates awaiting radiologist review', never "
        "as new or enlarging lesions; (b) NOT assert dissemination in time from them; (c) NOT "
        "classify the disease course from them; (d) state no reader decision: the radiologist's "
        "decisions on the candidates are recorded in the application, not in this draft; (e) when "
        "the data say the change candidates were NOT computed (acquisition or visit order not "
        "established as comparable), report no count and no lesion load and state that the "
        "change must be assessed visually by the radiologist. The FLAIR subtraction is a "
        "signal, never a confirmation.\n\n"
        "Generate the report with these exact sections:\n\n"
        "## CLINICAL INDICATION\n"
        "Restate indication, noting longitudinal comparison purpose.\n\n"
        "## TECHNIQUE\n"
        "MRI technique per MAGNIMS MS protocol; note whether the acquisition of the two visits "
        "was established as the same (as supplied in the data).\n\n"
        "## COMPARISON\n"
        "Reference the prior timepoint study with specific comparison data provided.\n\n"
        "## INTERVAL CHANGES\n"
        "### Change Candidates (unconfirmed)\n"
        "- Number of unconfirmed new and enlarging change candidates awaiting radiologist review; "
        "approximate locations if centroid data provided\n\n"
        "### Radiologist Decisions\n"
        "- Write: 'The radiologist's decisions on these candidates are recorded in the "
        "application and are not part of this draft.'\n\n"
        "### Resolved/Shrunk and Stable Candidates\n"
        "- Counts, labelled as unconfirmed candidates\n\n"
        "## LESION BURDEN TRAJECTORY\n"
        "- Total T2 lesion load: prior vs. current (mL or mm³), only if supplied\n"
        "- Percentage change in total burden (only if supplied)\n\n"
        "## DIS ASSESSMENT\n"
        "- Present DIS data from provided analysis\n"
        "- Lesion presence across 4 MAGNIMS regions with checkmarks\n\n"
        "## INTERVAL CHANGE STATUS\n"
        "- Write: 'Not determined by the software — N unconfirmed change candidates for "
        "radiologist review; the radiologist's decisions are recorded in the application.' Never "
        "infer a conclusion from the candidates.\n\n"
        "## IMPRESSION\n"
        "Numbered summary:\n"
        "1. Unconfirmed change candidates for radiologist review\n"
        "2. Burden trajectory with quantitative delta (if supplied)\n"
        "3. DIS status (X/4 regions)\n"
        "4. Interval change status as above\n"
        "5. Recommended follow-up interval per MAGNIMS guidelines\n"
        + _FORMAT_INSTRUCTIONS
    ),
}


class BrainReportService:
    """
    Generates structured brain MRI reports using Claude API.

    Features:
    - Template-based report generation (general, ms_activity, ms_lesion_burden)
    - Integrates volumetry data when available
    - Multi-language support (en, es, de)

    CAPA-014: the prompt is built from a structured payload only (measurements, fixed labels, sex,
    age band) and checked against the patient's own identifiers before any call; without the
    patient's record no request is sent (see the module docstring).
    """

    def __init__(self):
        self._client = None
        self._settings = get_settings()

    def _get_client(self):
        """Lazy-load Anthropic client."""
        if self._client is None:
            api_key = self._settings.ANTHROPIC_API_KEY
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not configured. "
                    "Set the environment variable to enable report generation."
                )
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def _build_findings_prompt(
        self,
        findings: Dict[str, Any],
        volumetry: Optional[Dict[str, Any]] = None,
        language: str = "en",
    ) -> str:
        """Build the user prompt from clinical findings and volumetry data."""
        parts = []

        # Language instruction
        lang_map = {"en": "English", "es": "Spanish", "de": "German"}
        lang_name = lang_map.get(language, "English")
        parts.append(f"Generate the report in {lang_name}.")
        # CAPA-014 (RC-064): no free text is sent; when the clinician typed some, the route adds it to the
        # draft and the model is told so (only then).
        if findings.get("clinician_entry") is True:
            parts.append(CLINICIAN_TEXT_INSTRUCTION)

        if findings.get("patient_age"):
            # CAPA-014 (RC-064): the 5-year band of the structured payload, never the exact age
            parts.append(f"Patient age band: {findings['patient_age']} (years)")

        if findings.get("patient_sex") in ("M", "F"):
            sex_label = "Male" if findings["patient_sex"] == "M" else "Female"
            parts.append(f"Patient sex: {sex_label}")

        # Segmentation findings
        if findings.get("segmentation_labels"):
            labels = findings["segmentation_labels"]
            parts.append(f"Segmented structures identified: {', '.join(labels)}")

        # Anomaly findings
        if findings.get("anomalies"):
            parts.append("Detected anomalies:")
            for anomaly in findings["anomalies"]:
                line = f"  - {anomaly.get('type', 'unknown')}"
                if anomaly.get("location"):
                    line += f" at {anomaly['location']}"
                if anomaly.get("confidence"):
                    line += f" (confidence: {anomaly['confidence']:.0%})"
                if anomaly.get("volume_mm3"):
                    line += f" ({anomaly['volume_mm3']:.1f} mm3)"
                parts.append(line)

        # Volumetry data
        if volumetry:
            parts.append("\nBrain volumetry measurements:")
            if volumetry.get("total_brain_volume_ml"):
                parts.append(
                    f"  Total brain volume: {volumetry['total_brain_volume_ml']:.1f} mL"
                )
            if volumetry.get("intracranial_volume_ml"):
                parts.append(
                    f"  Intracranial volume: {volumetry['intracranial_volume_ml']:.1f} mL"
                )

            structures = volumetry.get("structures", [])
            abnormal = [s for s in structures if s.get("is_abnormal")]
            if abnormal:
                parts.append("  Abnormal structure volumes:")
                for s in abnormal:
                    atype = s.get("abnormality_type", "")
                    pct = s.get("normative_percentile")
                    line = f"    - {s['structure_name']}: {s['volume_ml']:.1f} mL"
                    if pct is not None:
                        line += f" ({pct:.0f}th percentile)"
                    if atype:
                        line += f" [{atype}]"
                    parts.append(line)

            # Normal structures summary
            normal = [s for s in structures if not s.get("is_abnormal") and s.get("volume_ml", 0) > 0.1]
            if normal:
                names = [s["structure_name"] for s in normal[:10]]
                parts.append(f"  Normal structures: {', '.join(names)}")
                if len(normal) > 10:
                    parts.append(f"    ... and {len(normal) - 10} more")

        # Lesion analysis data (from Phase 10)
        if findings.get("lesion_analysis"):
            la = findings["lesion_analysis"]
            parts.append(f"\nLesion analysis:")
            parts.append(f"  Total lesions: {la.get('total_count', 0)}")
            parts.append(f"  Total burden: {la.get('total_burden_mm3', 0):.2f} mm³ "
                         f"({la.get('total_burden_ml', 0):.4f} mL)")
            regions_confirmed = la.get("regions_confirmed") is not False      # release 2026-10-25, item 1
            if not regions_confirmed:
                parts.append(REGIONS_NOT_CONFIRMED_LINE)
            regions = la.get("regions", {}) if regions_confirmed else {}
            if regions:
                parts.append("  Regional summary:")
                for name, info in regions.items():
                    parts.append(f"    - {name}: {info.get('lesion_count', 0)} lesions, "
                                 f"{info.get('total_volume_mm3', 0):.2f} mm³ "
                                 f"({info.get('total_volume_ml', 0):.4f} mL)")
            size_dist = la.get("size_distribution", {})
            if size_dist:
                parts.append(f"  Size distribution: "
                             f"small(<100mm³)={size_dist.get('small', 0)}, "
                             f"medium(100-1000mm³)={size_dist.get('medium', 0)}, "
                             f"large(>1000mm³)={size_dist.get('large', 0)}")

            # Per-lesion detail table (critical for comprehensive reports)
            lesions = la.get("lesions", [])
            if lesions:
                parts.append(f"\n  Individual lesion data ({len(lesions)} lesions):")
                if regions_confirmed:
                    parts.append("  # | Region | Volume_mm3 | Volume_mL | Size | Centroid(z,y,x)")
                    parts.append("  --|--------|-----------|----------|------|----------------")
                else:   # no region column: the regions were not confirmed (release 2026-10-25, item 1)
                    parts.append("  # | Volume_mm3 | Volume_mL | Size | Centroid(z,y,x)")
                    parts.append("  --|-----------|----------|------|----------------")
                for les in lesions:
                    ctr = les.get("centroid", {})
                    region = f"{les.get('region', 'Unknown')} | " if regions_confirmed else ""
                    parts.append(
                        f"  {les.get('id', '?')} | {region}"
                        f"{les.get('volume_mm3', 0):.1f} | "
                        f"{les.get('volume_ml', 0):.4f} | "
                        f"{les.get('size_category', '?')} | "
                        f"z={ctr.get('z', 0):.0f}, y={ctr.get('y', 0):.0f}, x={ctr.get('x', 0):.0f}"
                    )

        # DIS assessment data. PRB-003 (RC-070; HAZ-008, HAZ-003): a DIS result is passed only when the
        # server evaluated it on a segmentation a radiologist confirmed ("evaluation_status": "evaluated",
        # set by the report route from the stored segmentation). Anything else — not evaluated, or a block
        # without that state — is NOT EVALUATED, never "NOT MET" (a missing flag used to print NOT MET),
        # and the model is told not to derive DIS from the lesion counts or regions.
        from app.services import dis_review_gate as gate   # the one "evaluated" rule (release 2026-10-25, item 3)
        dis = findings.get("dis_assessment")
        if not gate.is_evaluated(dis):
            if dis or findings.get("lesion_analysis"):
                parts.append(DIS_NOT_EVALUATED_PROMPT)
        else:
            met = "MET" if dis.get("dis_met") else "NOT MET"
            parts.append(f"\nDIS Assessment: {met} "
                         f"({dis.get('regions_with_lesions', 0)}/{dis.get('total_dis_regions', 4)} regions)")
            for name, detail in dis.get("region_details", {}).items():
                present = "PRESENT" if detail.get("present") else "absent"
                parts.append(f"  - {name}: {present}")
            if dis.get("has_active_lesions"):
                parts.append(f"  Active (Gd+) lesions present: {dis.get('active_voxels', 0)} voxels")
            if dis.get("has_black_holes"):
                parts.append(f"  T1 black holes present: {dis.get('black_hole_voxels', 0)} voxels")

        # Longitudinal comparison data (from Phase 11).
        # CLASS C SAFETY (adversarial finding): the longitudinal comparison does NOT verify
        # spatial registration — two timepoints with equal array dimensions need not be
        # voxel-aligned, so an IoU diff can manufacture FALSE new/enlarging lesions from
        # misregistration. These counts are therefore UNADJUDICATED CANDIDATES, never
        # confirmed findings, and must NOT drive dissemination-in-time (DIT) or any
        # diagnostic conclusion until a reader adjudicates them. We label them as such and
        # instruct the report generator not to assert them as findings.
        if findings.get("longitudinal"):
            lng = findings["longitudinal"]
            # No spatial registration is verified anywhere in the system, and `findings` can be
            # supplied straight from the client (/ai/report/generate). So NEVER trust a
            # caller-provided registration_verified=true (adversarial finding D4), and never
            # pass an activity or DIT flag: the candidates are unconfirmed (CAPA-013, RC-060).
            parts.append(f"\nLongitudinal comparison data:")
            if lng.get("abstained"):
                # RC-062: acquisition or visit order not established as comparable — no change
                # result and no lesion load or count of either visit (review of PR #63, blocker 2).
                parts.append(
                    "  Automatic change candidates were NOT computed: the acquisition of the two "
                    "visits, or their order, could not be established as comparable. Report no new, "
                    "enlarging or resolved figure and no lesion load of either visit; state that the "
                    "change between the visits must be assessed visually by the radiologist."
                )
            else:
                parts.append(f"  TP1 burden: {lng.get('burden_tp1_ml') or 0:.3f} mL "
                             f"({lng.get('total_lesions_tp1') or 0} lesions)")
                parts.append(f"  TP2 burden: {lng.get('burden_tp2_ml') or 0:.3f} mL "
                             f"({lng.get('total_lesions_tp2') or 0} lesions)")
                if lng.get("burden_delta_percent") is not None:
                    parts.append(f"  Burden delta: {percent_text(lng.get('burden_delta_percent'))}")
                sc = lng.get("status_counts") or {}
                parts.append(
                    "  NOTE: the following are UNCONFIRMED CHANGE CANDIDATES produced automatically, "
                    "without spatial registration verified at lesion scale. In a public test with "
                    "expert-marked change this rule proposed several false candidates per patient. "
                    "Do NOT report them as new or enlarging lesions, do NOT classify the disease "
                    "course from them, do NOT use them for dissemination in time; list them only as "
                    "unconfirmed candidates awaiting radiologist review."
                )
                parts.append(f"  New-lesion candidates (unconfirmed): {sc.get('new', 0)}")
                parts.append(f"  Enlarging candidates (unconfirmed): {sc.get('enlarged', 0)}")
                parts.append(f"  Resolved candidates (unconfirmed): {sc.get('resolved', 0)}")
                parts.append(f"  Shrunk candidates (unconfirmed): {sc.get('shrunk', 0)}")
                parts.append(f"  Stable candidates (unconfirmed): {sc.get('stable', 0)}")
                # Review of PR #63, blocker 1: findings come from the request and a reader decision
                # in them cannot be verified here, so none is ever passed to the model.
                parts.append(
                    "  Radiologist decisions on these candidates are recorded in the application and "
                    "are not part of this draft: state none."
                )

        # Zone map statistics (from MSMask atlas)
        if findings.get("zone_stats"):
            zs = findings["zone_stats"]
            parts.append(f"\nMAGNIMS zone map statistics (MSMask atlas, Wiltgen et al. 2024):")
            parts.append(f"  Total classified brain voxels: {zs.get('total_brain_voxels', 0)}")
            for zone_name, info in zs.get("zones", {}).items():
                parts.append(
                    f"  - {zone_name}: {info.get('voxel_count', 0)} voxels "
                    f"({percent_text(info.get('percentage', 0))})"
                )

        return "\n".join(parts)

    async def generate_report(
        self,
        template_type: str = "general",
        findings: Optional[Dict[str, Any]] = None,
        volumetry: Optional[Dict[str, Any]] = None,
        language: str = "en",
        identifiers: Optional[PatientIdentifiers] = None,
    ) -> Dict[str, Any]:
        """
        Generate a structured brain MRI report.

        Args:
            template_type: Report template (general, ms_activity, ms_lesion_burden)
            findings: Clinical findings dict (only the structured payload is sent, CAPA-014)
            volumetry: Volumetry results dict (optional)
            language: Report language (en, es, de)
            identifiers: The patient's own identifiers, from the patient record (required, for the check)

        Returns:
            Dict with report_id, content, template_type, language, processing_time_ms

        Raises:
            ProviderGuardError: no identifiers, or the check found one in the prompt — nothing was sent
        """
        start_time = time.time()
        report_id = str(uuid.uuid4())

        if findings is None:
            findings = {}

        # Validate template
        if template_type not in REPORT_TEMPLATES:
            template_type = "general"

        # CAPA-014 (RC-065, HAZ-016): without the patient's identifiers there is nothing to check
        # against, so no request is sent.
        if not isinstance(identifiers, PatientIdentifiers):
            raise PatientRecordUnavailable("the patient's identifiers were not supplied")

        system_prompt = REPORT_TEMPLATES[template_type]      # fixed text: carries no patient data
        # RC-064: structured payload only — measurements, fixed labels, sex, age band; no free text.
        payload = provider_payload(findings, volumetry, identifiers)   # the patient's own numbers refused (R2)
        # PRB-003 (RC-070; review of PR #68, finding 4): no DIS instruction in the template unless DIS was
        # evaluated on a classified, radiologist-confirmed segmentation (state set by the report route).
        # Release 2026-10-25 integration (PR #67 + PR #68): the variant is chosen on the DIS block the model
        # actually receives (the RC-064 payload), so the template and the findings prompt always agree; the
        # system prompt is one of the fixed template variants (RC-064 amended, PENDING owner approval).
        from app.services import dis_review_gate as gate   # the one "evaluated" rule (release 2026-10-25, item 3)
        dis_block = payload.findings.get("dis_assessment")
        if not gate.is_evaluated(dis_block):
            system_prompt = dis_not_evaluated_template(system_prompt)
        user_prompt = self._build_findings_prompt(payload.findings, payload.volumetry, language)
        # RC-065: detection-only tripwire on the final prompt; refuses to send on any finding.
        assert_prompt_carries_no_identifier(user_prompt, identifiers)
        # RC-066: record that the check ran and what was withheld (counts) — never the payload.
        logger.info(
            "[Report] Structured payload checked before the model provider call",
            extra={"report_id": report_id, "privacy_check": "passed", "withheld": payload.withheld},
        )

        logger.info(
            f"[Report] Generating {template_type} report in {language}",
            extra={"report_id": report_id},
        )

        try:
            client = self._get_client()
            # Use higher token limit for comprehensive reports with per-lesion data
            max_tokens = self._settings.CLAUDE_MAX_TOKENS
            if template_type == "ms_comprehensive":
                max_tokens = min(max(max_tokens, 8192), 16384)
            message = client.messages.create(
                model=self._settings.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt},
                ],
            )

            # RC-006 (HAZ-003): the disclaimer is applied here, in code, so that
            # no generated report can leave this service without it — regardless
            # of what the model produced. See _apply_disclaimer.
            content = _apply_disclaimer(message.content[0].text, language)
            processing_time_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"[Report] Generated successfully in {processing_time_ms}ms",
                extra={
                    "report_id": report_id,
                    "tokens_in": message.usage.input_tokens,
                    "tokens_out": message.usage.output_tokens,
                },
            )

            return {
                "report_id": report_id,
                "content": content,
                "template_type": template_type,
                "language": language,
                "processing_time_ms": processing_time_ms,
                "model": self._settings.CLAUDE_MODEL,
                "tokens_used": {
                    "input": message.usage.input_tokens,
                    "output": message.usage.output_tokens,
                },
                # CAPA-014: placeholder -> label as written, for the clinician's draft only (never sent)
                "unlisted_labels": payload.unlisted,
            }

        except Exception as e:
            logger.error(f"[Report] Generation failed: {e}")
            raise

    def list_templates(self) -> List[Dict[str, str]]:
        """List available report templates."""
        templates = [
            {
                "id": "general",
                "name": "General MS Brain MRI",
                "description": (
                    "MAGNIMS-compliant structured brain MRI report for MS evaluation. "
                    "Includes DIS/DIT assessment per 2017 McDonald criteria."
                ),
            },
            {
                "id": "ms_activity",
                "name": "MS Disease Activity Assessment",
                "description": (
                    "Disease activity monitoring report with DIS/DIT evaluation, "
                    "new/enhancing lesion analysis, and treatment response assessment."
                ),
            },
            {
                "id": "ms_comprehensive",
                "name": "Comprehensive MS Analysis",
                "description": (
                    "Publication-quality comprehensive report with per-lesion tables, "
                    "regional distribution, DIS assessment, size analysis, and clinical "
                    "interpretation per MAGNIMS/DIFUTURE/McDonald standards."
                ),
            },
            {
                "id": "ms_lesion_burden",
                "name": "Quantitative Lesion Burden Analysis",
                "description": (
                    "Comprehensive lesion burden quantification with longitudinal comparison, "
                    "regional distribution, and PIRA assessment per MAGNIMS/DIFUTURE standards."
                ),
            },
            {
                "id": "ms_longitudinal",
                "name": "MS Longitudinal Comparison",
                "description": (
                    "Interval change report: unconfirmed change candidates (new/enlarged/resolved) "
                    "for radiologist review, burden trajectory and DIS assessment."
                ),
            },
        ]
        return templates


# ─────────────────────────────────────────────────────────────────────────────
# CAPA-014 (RC-065): the device's own words — the tripwire never reports one of them on its own, so a
# patient named White does not stop "Deep White Matter", nor two of them in the order the device's text has
# them ("Deep White"). Derived only from what can appear in the user prompt — the prompt builder itself on
# synthetic payloads covering every label and branch — not from the system templates, which are never
# checked (second review, N5).
# ─────────────────────────────────────────────────────────────────────────────
def _synthetic_payloads():
    labels = sorted(set(label_vocabulary().values()))
    regions = {n: {"lesion_count": 1, "total_volume_mm3": 1.0, "total_volume_ml": 0.001} for n in labels}
    lesions = [{"id": i + 1, "region": n, "volume_mm3": 1.0, "volume_ml": 0.001, "size_category": "small",
                "centroid": {"z": 1, "y": 1, "x": 1}} for i, n in enumerate(labels)]
    base = {
        "clinician_entry": True,
        "patient_age": "45-49", "patient_sex": "M", "segmentation_labels": labels + [UNLISTED],
        "anomalies": [{"type": n, "location": n, "confidence": 0.5, "volume_mm3": 1.0} for n in labels],
        "lesion_analysis": {"total_count": 1, "total_burden_mm3": 1.0, "total_burden_ml": 0.001, "regions": regions,
                            "size_distribution": {"small": 1, "medium": 1, "large": 1}, "lesions": lesions},
        # an evaluated DIS with present and absent regions (third review, M2: also printed once PR #68 is in)
        "dis_assessment": {"evaluation_status": "evaluated", "dis_met": True, "regions_with_lesions": 1,
                           "total_dis_regions": 5,
                           "region_details": {n: {"present": i % 2 == 0} for i, n in enumerate(labels)},
                           "has_active_lesions": True,
                           "active_voxels": 1, "has_black_holes": True, "black_hole_voxels": 1},
        "zone_stats": {"total_brain_voxels": 1, "zones": {n: {"voxel_count": 1, "percentage": 1.0} for n in labels}},
    }
    volumetry = {"total_brain_volume_ml": 1.0, "intracranial_volume_ml": 1.0, "structures":
                 [{"structure_name": n, "volume_ml": 1.0, "is_abnormal": True, "normative_percentile": 1,
                   "abnormality_type": "atrophy"} for n in labels]
                 + [{"structure_name": n, "volume_ml": 1.0, "is_abnormal": False} for n in labels]}
    for longitudinal in ({"burden_tp1_ml": 1.0, "burden_tp2_ml": 1.0, "total_lesions_tp1": 1, "total_lesions_tp2": 1,
                          "burden_delta_percent": 1.0, "status_counts": {"new": 1}}, {"abstained": True}):
        yield {**base, "longitudinal": longitudinal}, volumetry
    yield {**base, "patient_sex": "F", "patient_age": "90 or older"}, volumetry
    # regions not confirmed (release 2026-10-25, item 1): the fixed line and the table without a region column
    yield {**base, "lesion_analysis": {**base["lesion_analysis"], "regions_confirmed": False},
           "dis_assessment": {"evaluation_status": "not_evaluated"}}, volumetry
    # every value missing: what "not available" looks like in each block
    sparse = provider_payload({"lesion_analysis": {"regions": {"Lesion": {}}, "size_distribution": {"small": None},
                                                   "lesions": [{}]},
                               "dis_assessment": {"has_active_lesions": True, "has_black_holes": True},
                               "zone_stats": {"zones": {"Lesion": {}}}, "longitudinal": {"status_counts": {}}}, None)
    yield sparse.findings, None


@lru_cache(maxsize=1)
def _fixed_prompt_word_lists() -> tuple:
    builder = BrainReportService.__new__(BrainReportService)
    texts = [UNLISTED, "Structure Label"]
    for findings, volumetry in _synthetic_payloads():
        for language in ("en", "es", "de"):
            texts.append(builder._build_findings_prompt(findings, volumetry, language))
    return tuple(tuple(words_of(text)) for text in texts)


@lru_cache(maxsize=1)
def fixed_prompt_words() -> frozenset:
    """Words the device's own text can put in the user prompt."""
    return frozenset(w for words in _fixed_prompt_word_lists() for w in words)


@lru_cache(maxsize=1)
def fixed_prompt_pairs() -> frozenset:
    """Two such words in the order the device's own text has them, e.g. ("deep", "white")."""
    return frozenset(pair for words in _fixed_prompt_word_lists() for pair in zip(words, words[1:]))


def assert_prompt_carries_no_identifier(user_prompt: str, identifiers: PatientIdentifiers) -> None:
    """RC-065: the tripwire on the final prompt (raises IdentifierInPrompt; never edits the text)."""
    assert_no_identifiers(user_prompt, identifiers, fixed_prompt_words(), fixed_prompt_pairs())
