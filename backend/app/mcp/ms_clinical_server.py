"""
MS Clinical Analysis MCP Server (investigational decision support, read-only).

Lets an AI assistant (Claude Desktop / Claude Code) READ the measurements the device has
already computed for a lesion segmentation — lesion analysis, region classification, the
brain-MRI dissemination-in-space (DIS) items of the McDonald 2024 criteria (Montalban et al.,
Lancet Neurology 2025; 24(10): 850-865) — compare two timepoints, and draft a report from
those measurements for physician review.

CAPA-008: the assistant is read-only and is never a diagnostic tool.
- Every backend call goes through ``app.mcp._backend`` (GET, or POST to a compute-only route).
- No tool writes a record. Region classification and CVS/PRL readings are recorded by the
  clinician in the application, never by the assistant.
- Texts state what the device measures and nothing more; MS is diagnosed by a physician
  with clinical, laboratory and imaging information the device does not have.

@module mcp.ms_clinical_server
"""

from fastmcp import FastMCP
from app.mcp._backend import api_get, api_post_compute
from app.services.region_evidence import strip_region_confidence as _strip_region_confidence

mcp = FastMCP(
    "ms-clinical-mcp",
    description=(
        "Investigational, read-only MS lesion measurements for physician review: lesion "
        "analysis, MAGNIMS region classification, brain-MRI DIS items (McDonald 2024), "
        "two-timepoint comparison candidates and draft reports. Not for diagnosis."
    ),
    instructions=(
        "You assist a physician who reviews brain MRI measurements computed by an "
        "investigational device. The device is NOT intended for diagnosis: never state or "
        "imply that a patient has or does not have MS, never state that diagnostic criteria "
        "are met, and never recommend treatment. Present every number as a device "
        "measurement that the physician must verify on the images.\n\n"
        "Typical workflow:\n"
        "1. get_region_classification() — the stored MAGNIMS region per lesion (candidates)\n"
        "2. summarize_dis_items() — brain-MRI DIS items + clinician-recorded CVS/PRL readings\n"
        "3. compare_longitudinal() — new/enlarging lesion CANDIDATES between two timepoints\n"
        "4. generate_ms_report() — a DRAFT report from the measurements above\n\n"
        "What the device can and cannot tell (McDonald 2024):\n"
        "- DIS needs typical lesions in >=2 of 5 regions (periventricular, cortical/"
        "juxtacortical, infratentorial, spinal cord, optic nerve). Brain MRI covers 3 of "
        "them; spinal cord and optic nerve are NOT evaluable here — say 'not evaluable', "
        "never 'absent'.\n"
        "- Deep white matter is not a DIS region. Periventricular = abutting the lateral "
        "ventricles.\n"
        "- The central vein sign (CVS) and paramagnetic rim lesions (PRL) need "
        "susceptibility-sensitive MRI and a human reading. They give supportive evidence "
        "only in specific situations defined by the criteria; report the clinician-recorded "
        "counts and never infer a CVS or PRL status yourself.\n"
        "- New or enlarging lesions from compare_longitudinal() are unconfirmed change "
        "CANDIDATES (spatial registration not verified). Never call them disease activity "
        "or dissemination in time. In a public expert-annotated test this rule proposed about "
        "9 false candidates per patient (`false_candidate_evidence` in the response gives the "
        "measured figures and source): most candidates may be false. Only "
        "`reader_confirmed_activity`, present when a radiologist confirmed candidates in the "
        "application, may be reported — as the radiologist's confirmation, naming them.\n"
        "- `subtraction_confirmed` / `new_subtraction_confirmed` mean only 'brighter at "
        "follow-up on the FLAIR subtraction': a signal, never a confirmation of a lesion.\n"
        "- When the response says `abstained: true`, the acquisition of the two visits differs or "
        "could not be established: report no change count; say the images must be compared "
        "visually."
    ),
)


# =============================================================================
# Tools (read-only)
# =============================================================================


@mcp.tool()
async def get_region_classification(segmentation_id: str) -> dict:
    """
    Read the MAGNIMS region classification STORED for a lesion segmentation.

    The assistant never runs or overwrites a classification (CAPA-008): the clinician runs
    it in the application, choosing the method. Each lesion's region is a deterministic
    MAGNIMS rule applied by one path (LST-AI zones, parcellation of the same image, MSMask
    atlas on MNI-grid images, or geometric heuristics); the stored result says which.
    Region-assignment accuracy has NOT been measured for any path (HAZ-005): present the
    regions as candidates to verify. `confidence` is always removed — there is no calibrated
    probability; never report or estimate one.

    Args:
        segmentation_id: ID of the lesion segmentation

    Returns:
        {"classification": stored result with per-lesion regions and evidence, or None,
         "message": what to do when nothing is stored}
    """
    seg = await api_get(f"/segmentation/{segmentation_id}")
    analysis_data = (seg.get("metadata") or {}).get("analysis_data") or {}
    classification = analysis_data.get("classification")
    if not classification:
        return {
            "classification": None,
            "message": "No region classification is stored for this segmentation. Ask the "
                       "physician to run the region classification in the application.",
        }
    return {"classification": _strip_region_confidence(classification)}


@mcp.tool()
async def summarize_dis_items(segmentation_id: str) -> dict:
    """
    Brain-MRI dissemination-in-space (DIS) items of McDonald 2024, as measured by the device.

    Returns the device's DIS assessment and lesion analysis, plus the CVS and PRL counts
    RECORDED BY A CLINICIAN in the application (if any). This is a summary of measurements
    for physician review, not a diagnostic evaluation: spinal cord and optic nerve are not
    evaluable from brain MRI, and CVS/PRL count only in the situations the criteria define.

    Reference: Montalban et al., Lancet Neurology 2025; 24(10): 850-865

    Args:
        segmentation_id: ID of the classified lesion segmentation

    Returns:
        {"dis_assessment", "lesion_analysis", "clinician_recorded_cvs", "clinician_recorded_prl",
         "criteria_version", "not_evaluable_from_brain_mri"}
    """
    dis = await api_get(f"/segmentation/{segmentation_id}/dis-assessment")
    analysis = await api_get(f"/segmentation/{segmentation_id}/lesion-analysis")
    seg = await api_get(f"/segmentation/{segmentation_id}")
    analysis_data = (seg.get("metadata") or {}).get("analysis_data") or {}
    return {
        "dis_assessment": dis,
        "lesion_analysis": analysis,
        "clinician_recorded_cvs": analysis_data.get("cvs_summary"),
        "clinician_recorded_prl": analysis_data.get("prl_summary"),
        "criteria_version": "McDonald 2024 (Montalban et al., Lancet Neurology 2025)",
        "not_evaluable_from_brain_mri": ["spinal cord", "optic nerve"],
    }


@mcp.tool()
async def analyze_lesions(segmentation_id: str) -> dict:
    """
    Lesion analysis of a segmentation (connected components).

    Returns per-lesion volume (mm3, mL), centroid, size category and stored region, and the
    total lesion burden. Volumes depend on the segmentation, which a physician must verify.

    Args:
        segmentation_id: ID of the lesion segmentation
    """
    return await api_get(f"/segmentation/{segmentation_id}/lesion-analysis")


@mcp.tool()
async def compare_longitudinal(baseline_id: str, followup_id: str) -> dict:
    """
    Compare two timepoint segmentations: new, enlarged, shrunk, resolved and stable lesion
    CANDIDATES and the burden change.

    The counts are unconfirmed change candidates: in a public expert-annotated test the rule
    proposed about 9 false candidates per patient (see `false_candidate_evidence`), and a
    misregistration between the timepoints can create more. Never report them as disease
    activity or as dissemination in time; a radiologist confirms or rejects each one in the
    application (`reader_confirmed_activity` is present only after a confirmation). The FLAIR
    subtraction flag is a signal, never a confirmation of a lesion. When `abstained` is true the
    acquisition of the two visits differs or could not be established and no count is given.

    Args:
        baseline_id: Segmentation ID for the baseline timepoint
        followup_id: Segmentation ID for the follow-up timepoint
    """
    return await api_post_compute(
        "/segmentation/longitudinal/compare",
        {
            "tp1": {"type": "segmentation", "id": baseline_id},
            "tp2": {"type": "segmentation", "id": followup_id},
        },
    )


@mcp.tool()
async def generate_ms_report(
    segmentation_id: str,
    language: str = "en",
    include_longitudinal: bool = False,
    longitudinal_baseline_id: str = "",
) -> dict:
    """
    Draft a structured MS brain MRI report FROM THE DEVICE'S MEASUREMENTS, for physician
    review. The report carries the mandatory AI-draft disclaimer (RC-006).

    The measurements (lesion analysis, DIS assessment and, if requested, the longitudinal
    comparison) are read first; if none can be read, no report is requested (CAPA-008:
    a report without measurements would be invented). Read failures are returned, not hidden.

    Args:
        segmentation_id: ID of the analysed segmentation
        language: Report language ('en', 'es', 'de')
        include_longitudinal: Include the longitudinal comparison
        longitudinal_baseline_id: Baseline segmentation ID for the longitudinal comparison
    """
    findings, unavailable = {}, {}
    try:
        findings["lesion_analysis"] = await api_get(f"/segmentation/{segmentation_id}/lesion-analysis")
    except Exception as exc:  # report what could not be read instead of hiding it
        unavailable["lesion_analysis"] = str(exc)
    try:
        findings["dis_assessment"] = await api_get(f"/segmentation/{segmentation_id}/dis-assessment")
    except Exception as exc:
        unavailable["dis_assessment"] = str(exc)
    if include_longitudinal and longitudinal_baseline_id:
        try:
            findings["longitudinal"] = await api_post_compute(
                "/segmentation/longitudinal/compare",
                {
                    "tp1": {"type": "segmentation", "id": longitudinal_baseline_id},
                    "tp2": {"type": "segmentation", "id": segmentation_id},
                },
            )
        except Exception as exc:
            unavailable["longitudinal"] = str(exc)

    if not findings:
        return {
            "report": None,
            "message": "No measurement could be read, so no report was drafted.",
            "unavailable": unavailable,
        }

    # Field names are those of the report route's request model (ReportGenerateRequest);
    # a test binds them, because unknown names are silently dropped by the backend.
    report = await api_post_compute(
        "/ai/report/generate",
        {
            "template_type": "ms_longitudinal" if "longitudinal" in findings else "general",
            "language": language,
            "findings": findings,
        },
    )
    return {"report": report, "unavailable": unavailable}


# =============================================================================
# Workflow prompts (resources for the assistant)
# =============================================================================


@mcp.resource("prompts://ms-review-workflow")
def ms_review_workflow() -> str:
    """Review workflow for the device's MS lesion measurements (investigational, read-only)."""
    return """
# MS lesion measurement review — investigational device, not for diagnosis

You assist a physician reviewing measurements computed by the device. Never state or imply a
diagnosis, never state that criteria are met, never recommend treatment.

## Steps

1. **Regions**: `get_region_classification(segmentation_id)` — stored MAGNIMS region per
   lesion (candidates; accuracy not measured, HAZ-005). If none is stored, ask the physician
   to run the classification in the application.

2. **DIS items**: `summarize_dis_items(segmentation_id)` — brain-MRI DIS items of
   McDonald 2024:
   - DIS needs typical lesions in >=2 of 5 regions (periventricular, cortical/juxtacortical,
     infratentorial, spinal cord, optic nerve)
   - Brain MRI covers 3 of 5; spinal cord and optic nerve are "not evaluable", never "absent"

3. **CVS / PRL**: only the counts a clinician recorded from susceptibility-sensitive MRI.
   They give supportive evidence only in the specific situations the criteria define.
   Never infer a CVS or PRL status yourself.

4. **Draft report**: `generate_ms_report(segmentation_id)` — a draft from the measurements,
   with the AI-draft disclaimer, for the physician to review, correct and sign.

## Key references
- Montalban et al., Lancet Neurol 2025; 24(10): 850-865 (McDonald 2024)
- Barkhof et al., Lancet Neurol 2025; 24(10): 866-879 (MAGNIMS-CMSC-NAIMS 2024)
- Filippi et al., Brain 2019; 142(7): 1858-1875 (practical MRI guidelines)

## Definitions used by the device
- Deep white matter is NOT a DIS region
- Periventricular = abutting the lateral ventricles (excludes 3rd/4th ventricle)
- Juxtacortical = directly abutting the cortex (no white matter in between)
"""


@mcp.resource("prompts://ms-longitudinal-workflow")
def ms_longitudinal_workflow() -> str:
    """Two-timepoint comparison review workflow (candidates only)."""
    return """
# Two-timepoint lesion comparison — candidates for radiologist review

## Steps

1. **Identify timepoints**: baseline and follow-up segmentations of the same patient.

2. **Compare**: `compare_longitudinal(baseline_id, followup_id)` — new, enlarged, shrunk,
   resolved and stable lesion CANDIDATES.

3. **Present as unconfirmed candidates**: in a public expert-annotated test the rule proposed
   about 9 false candidates per patient (`false_candidate_evidence`), and the comparison does not
   verify spatial registration. Never call the counts disease activity or dissemination in time;
   a radiologist confirms or rejects each one in the application. Report
   `reader_confirmed_activity` only as the radiologist's confirmation. The FLAIR subtraction is a
   signal, never a confirmation. If `abstained` is true, report no count: the acquisition of the
   two visits differs or could not be established — the images must be compared visually.

4. **Draft report**: `generate_ms_report(followup_id, include_longitudinal=True,
   longitudinal_baseline_id=baseline_id)`.

## Candidate categories (device definitions)
- NEW: present at follow-up, not at baseline
- ENLARGED: >20% volume increase
- SHRUNK: >20% volume decrease
- RESOLVED: present at baseline, absent at follow-up
- STABLE: within 20% volume change
"""
