"""
MS Clinical Analysis MCP Server.

Provides tools for Claude Desktop / Claude Code to run comprehensive
MS clinical analysis per McDonald 2024 criteria (Montalban et al.,
Lancet Neurology 2025; 24(10): 850-865) and 2024 MAGNIMS-CMSC-NAIMS
consensus (Barkhof et al., Lancet Neurology 2025; 24(10): 866-879).

@module mcp.ms_clinical_server
"""

from fastmcp import FastMCP
from typing import Optional

mcp = FastMCP(
    "ms-clinical-mcp",
    description=(
        "MS Clinical Analysis MCP server. Complete McDonald 2024 diagnostic workflow: "
        "MAGNIMS region classification, DIS assessment, CVS/PRL biomarkers, "
        "longitudinal tracking, and clinical report generation."
    ),
    instructions=(
        "You are analyzing brain MRI for MS diagnosis per McDonald 2024 criteria "
        "(Montalban et al., Lancet Neurology 2025; 24(10): 850-865).\n\n"
        "Typical workflow:\n"
        "1. classify_lesions_magnims() — identify PV, JC, IT, DWM lesions\n"
        "2. evaluate_mcdonald_2024() — DIS assessment + CVS/PRL evaluation\n"
        "3. generate_ms_report() — comprehensive clinical report\n\n"
        "Key criteria (McDonald 2024):\n"
        "- DIS: >=2 of 5 regions (PV, JC, IT, spinal cord, optic nerve)\n"
        "- DIS without DIT: >=4 of 5 regions with typical lesions\n"
        "- CVS Select-6: >=6 CVS+ lesions supports MS diagnosis\n"
        "- PRL: >=1 paramagnetic rim lesion supports MS diagnosis\n"
        "- DWM is NOT a DIS region\n"
        "- PV = abutting lateral ventricles only"
    ),
)


def _get_api_base() -> str:
    """Get the backend API base URL."""
    import os
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


def _get_headers() -> dict:
    """Get auth headers for internal API calls."""
    import os
    token = os.environ.get("API_SERVICE_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


async def _api_get(path: str, params: Optional[dict] = None) -> dict:
    """Make an authenticated GET request to the backend."""
    import httpx
    url = f"{_get_api_base()}/api/v1{path}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, params=params, headers=_get_headers())
        response.raise_for_status()
        return response.json()


async def _api_post(path: str, json_data: Optional[dict] = None) -> dict:
    """Make an authenticated POST request to the backend."""
    import httpx
    url = f"{_get_api_base()}/api/v1{path}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=json_data, headers=_get_headers())
        response.raise_for_status()
        return response.json()


# =============================================================================
# Tools
# =============================================================================


@mcp.tool()
async def classify_lesions_magnims(
    segmentation_id: str,
    method: str = "auto",
) -> dict:
    """
    Classify MS lesions into MAGNIMS anatomical regions.

    Uses brain parcellation + distance transform analysis to classify each
    lesion as Periventricular (PV), Juxtacortical (JC), Infratentorial (IT),
    or Deep White Matter (DWM).

    Methods:
    - 'auto': Best available (MSMask atlas > geometric heuristics)
    - 'msmask': MSMask atlas-based classification (Wiltgen et al., 2024)
    - 'geometric': Geometric heuristics fallback

    Args:
        segmentation_id: ID of the lesion segmentation to classify
        method: Classification method ('auto', 'msmask', 'geometric')

    Returns:
        Classification results with per-lesion regions, distances, and confidence
    """
    return await _api_post(
        f"/segmentation/{segmentation_id}/classify-regions",
        json_data={"method": method},
    )


@mcp.tool()
async def evaluate_mcdonald_2024(
    segmentation_id: str,
    include_cvs: bool = True,
    include_prl: bool = True,
) -> dict:
    """
    Complete McDonald 2024 diagnostic evaluation for MS.

    Evaluates:
    - DIS (Dissemination in Space): >=2 of 5 regions with lesions
      - Brain MRI evaluable: PV, JC, IT (3 of 5)
      - Spinal cord and optic nerve require separate imaging
    - CVS Select-6 rule (if annotations available): >=6 CVS+ lesions
    - PRL criteria (if annotations available): >=1 PRL positive

    Reference: Montalban et al., Lancet Neurology 2025; 24(10): 850-865

    Args:
        segmentation_id: ID of the classified lesion segmentation
        include_cvs: Include CVS summary in evaluation (default: True)
        include_prl: Include PRL summary in evaluation (default: True)

    Returns:
        Comprehensive McDonald 2024 assessment with DIS, CVS, PRL results
    """
    # Get DIS assessment
    dis = await _api_get(f"/segmentation/{segmentation_id}/dis-assessment")

    # Get lesion analysis
    analysis = await _api_get(f"/segmentation/{segmentation_id}/lesion-analysis")

    result = {
        "mcdonald_2024_assessment": {
            "dis": dis,
            "lesion_analysis": analysis,
            "criteria_version": "McDonald 2024 (Montalban et al., Lancet Neurology 2025)",
        },
    }

    # Include CVS/PRL from cached analysis_data if available
    seg = await _api_get(f"/segmentation/{segmentation_id}")
    analysis_data = seg.get("metadata", {}).get("analysis_data", {})

    if include_cvs and analysis_data.get("cvs_summary"):
        result["mcdonald_2024_assessment"]["cvs_summary"] = analysis_data["cvs_summary"]
    if include_prl and analysis_data.get("prl_summary"):
        result["mcdonald_2024_assessment"]["prl_summary"] = analysis_data["prl_summary"]

    return result


@mcp.tool()
async def analyze_lesions(
    segmentation_id: str,
) -> dict:
    """
    Analyze MS lesions using connected components.

    Returns per-lesion statistics: volume (mm3, mL), centroid, size category,
    region, and overall burden. Also computes DIS criteria.

    Args:
        segmentation_id: ID of the lesion segmentation

    Returns:
        Lesion analysis with per-lesion stats, region summary, total burden
    """
    return await _api_get(f"/segmentation/{segmentation_id}/lesion-analysis")


@mcp.tool()
async def compare_longitudinal(
    baseline_id: str,
    followup_id: str,
) -> dict:
    """
    Compare two timepoint segmentations for longitudinal MS tracking.

    Identifies new, enlarged, shrunk, resolved, and stable lesions
    between baseline and follow-up. Returns burden delta and per-lesion changes.

    Args:
        baseline_id: Segmentation ID for baseline timepoint
        followup_id: Segmentation ID for follow-up timepoint

    Returns:
        Longitudinal comparison with per-lesion status changes and burden delta
    """
    return await _api_post(
        "/segmentation/longitudinal/compare",
        json_data={
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
    Generate comprehensive MS clinical report per MAGNIMS-CMSC-NAIMS 2024 guidelines.

    Combines lesion analysis, DIS assessment, classification results, and
    optional longitudinal data into a structured clinical report.

    Supports English, Spanish, and German output.

    Args:
        segmentation_id: ID of the analyzed/classified segmentation
        language: Report language ('en', 'es', 'de')
        include_longitudinal: Include longitudinal comparison in report
        longitudinal_baseline_id: Baseline segmentation ID for longitudinal

    Returns:
        Generated clinical report with structured findings and references
    """
    # Build clinical context for the report
    findings = {}

    # Get lesion analysis
    try:
        findings["lesion_analysis"] = await _api_get(
            f"/segmentation/{segmentation_id}/lesion-analysis"
        )
    except Exception:
        pass

    # Get DIS assessment
    try:
        findings["dis_assessment"] = await _api_get(
            f"/segmentation/{segmentation_id}/dis-assessment"
        )
    except Exception:
        pass

    # Get segmentation metadata (includes classification + CVS/PRL)
    try:
        seg = await _api_get(f"/segmentation/{segmentation_id}")
        analysis_data = seg.get("metadata", {}).get("analysis_data", {})
        if analysis_data.get("classification"):
            findings["classification"] = analysis_data["classification"]
        if analysis_data.get("cvs_summary"):
            findings["cvs_summary"] = analysis_data["cvs_summary"]
        if analysis_data.get("prl_summary"):
            findings["prl_summary"] = analysis_data["prl_summary"]
    except Exception:
        pass

    # Get longitudinal data if requested
    if include_longitudinal and longitudinal_baseline_id:
        try:
            findings["longitudinal"] = await _api_post(
                "/segmentation/longitudinal/compare",
                json_data={
                    "tp1": {"type": "segmentation", "id": longitudinal_baseline_id},
                    "tp2": {"type": "segmentation", "id": segmentation_id},
                },
            )
        except Exception:
            pass

    # Generate report via Claude API
    return await _api_post(
        "/ai/report/generate",
        json_data={
            "segmentation_id": segmentation_id,
            "template": "ms_longitudinal" if include_longitudinal else "general",
            "language": language,
            "clinical_context": (
                "MS clinical analysis per McDonald 2024 criteria "
                "(Montalban et al., Lancet Neurology 2025)."
            ),
            "additional_findings": findings,
        },
    )


@mcp.tool()
async def annotate_cvs_prl(
    segmentation_id: str,
    annotations: list,
) -> dict:
    """
    Save CVS (Central Vein Sign) and PRL (Paramagnetic Rim Lesion) annotations.

    McDonald 2024 officially incorporates CVS and PRL as diagnostic biomarkers.
    - CVS Select-6: >=6 CVS+ lesions supports MS diagnosis
    - CVS 40% rule: >=40% of evaluated lesions are CVS+ supports MS diagnosis
    - PRL: >=1 PRL positive supports MS diagnosis

    Each annotation should contain:
    - lesion_id: int
    - cvs_status: 'positive' | 'negative' | 'indeterminate' | null
    - prl_status: 'positive' | 'negative' | 'indeterminate' | null

    Args:
        segmentation_id: ID of the classified segmentation
        annotations: List of per-lesion CVS/PRL annotation dicts

    Returns:
        Updated CVS summary (Select-6, 40% rule) and PRL summary
    """
    return await _api_post(
        f"/segmentation/{segmentation_id}/lesion-annotations",
        json_data={"annotations": annotations},
    )


# =============================================================================
# Workflow Prompts (resources for Claude)
# =============================================================================


@mcp.resource("prompts://ms-diagnostic-workflow")
def ms_diagnostic_workflow() -> str:
    """Complete MS diagnostic workflow prompt per McDonald 2024."""
    return """
# MS Diagnostic Workflow — McDonald 2024

You are analyzing brain MRI for MS diagnosis per McDonald 2024 criteria
(Montalban et al., Lancet Neurology 2025; 24(10): 850-865).

## Steps

1. **Classify Regions**: Run `classify_lesions_magnims(segmentation_id)` to identify
   PV, JC, IT, DWM lesions using MAGNIMS region classification.

2. **Evaluate DIS**: Run `evaluate_mcdonald_2024(segmentation_id)` for complete
   McDonald 2024 assessment including:
   - DIS: >=2 of 5 regions (PV, JC, IT, spinal cord, optic nerve)
   - Brain MRI only evaluates 3 of 5 regions
   - DIS without DIT: >=4 of 5 regions with typical lesions

3. **CVS/PRL Biomarkers** (if SWI/T2*/phase data available):
   - Annotate CVS and PRL per lesion using `annotate_cvs_prl()`
   - CVS Select-6: >=6 CVS+ lesions supports MS diagnosis
   - PRL: >=1 paramagnetic rim lesion supports MS diagnosis

4. **Generate Report**: Run `generate_ms_report(segmentation_id)` for a
   comprehensive clinical report.

## Key References
- Montalban et al., Lancet Neurol 2025; 24(10): 850-865 (McDonald 2024)
- Barkhof et al., Lancet Neurol 2025; 24(10): 866-879 (MAGNIMS-CMSC-NAIMS 2024)
- Filippi et al., Brain 2019; 142(7): 1858-1875 (practical MRI guidelines)

## Important Notes
- DWM is NOT a DIS region (common misconception)
- PV = abutting lateral ventricles only (excludes 3rd/4th ventricle)
- JC = directly abutting cortex (no WM between lesion and cortex)
- Minimum lesion size: 3mm diameter (longest axis)
- Spinal cord and optic nerve require separate imaging
"""


@mcp.resource("prompts://ms-longitudinal-workflow")
def ms_longitudinal_workflow() -> str:
    """Longitudinal MS tracking workflow prompt."""
    return """
# MS Longitudinal Tracking Workflow

## Steps

1. **Identify Timepoints**: Locate baseline and follow-up segmentations
   for the same patient.

2. **Compare**: Run `compare_longitudinal(baseline_id, followup_id)` to
   identify new, enlarged, shrunk, resolved, and stable lesions.

3. **Assess Activity**: New or enlarging lesions indicate disease activity
   per McDonald 2024. Combined with Gd+ enhancement = DIT evidence.

4. **Generate Report**: Run `generate_ms_report(followup_id, include_longitudinal=True,
   longitudinal_baseline_id=baseline_id)` for a longitudinal clinical report.

## Disease Activity Categories
- NEW: Lesion present in follow-up but not baseline
- ENLARGED: >20% volume increase
- SHRUNK: >20% volume decrease
- RESOLVED: Lesion in baseline but absent in follow-up
- STABLE: Within 20% volume change
"""
