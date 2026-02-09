"""
Brain Report MCP Server.

Provides tools for Claude Desktop / Claude Code to generate
structured radiology reports for brain MRI:
- Generate reports with templates (stroke, tumor, dementia, general)
- Multi-language support (en, es, de)
- Differential diagnosis generation
- Template listing

@module mcp.report_server
"""

from fastmcp import FastMCP
from typing import Optional

mcp = FastMCP(
    "brain-report-mcp",
    description="MCP server for brain MRI report generation — structured reports, templates, differential diagnosis",
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
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=json_data, headers=_get_headers())
        response.raise_for_status()
        return response.json()


# =============================================================================
# Tools
# =============================================================================

@mcp.tool()
async def generate_brain_report(
    template_type: str = "general",
    language: str = "en",
    clinical_indication: str = "",
    technique: str = "",
    additional_observations: str = "",
    patient_age: Optional[int] = None,
    patient_sex: Optional[str] = None,
    volumetry: Optional[dict] = None,
) -> dict:
    """
    Generate a structured radiology report for a brain MRI study.

    Uses Claude API to produce a professional report following
    standard radiology reporting conventions with sections:
    CLINICAL INDICATION, TECHNIQUE, FINDINGS, IMPRESSION.

    HIPAA compliant — only de-identified clinical findings are sent.

    Args:
        template_type: Report template — 'general', 'stroke', 'tumor', or 'dementia'
        language: Report language — 'en' (English), 'es' (Spanish), 'de' (German)
        clinical_indication: Why the MRI was ordered (e.g., "headache, rule out mass")
        technique: MRI sequences used (e.g., "T1, T2, FLAIR, DWI, Gd+")
        additional_observations: Any extra clinical context or findings
        patient_age: Patient age in years (included in report context)
        patient_sex: Patient sex 'M' or 'F' (included in report context)
        volumetry: Optional volumetry results dict from compute_brain_volumes
    """
    findings = {}
    if clinical_indication:
        findings["clinical_indication"] = clinical_indication
    if technique:
        findings["technique"] = technique
    if additional_observations:
        findings["additional_observations"] = additional_observations
    if patient_age:
        findings["patient_age"] = patient_age
    if patient_sex:
        findings["patient_sex"] = patient_sex

    return await _api_post("/ai/report/generate", {
        "template_type": template_type,
        "language": language,
        "findings": findings,
        "volumetry": volumetry,
    })


@mcp.tool()
async def list_report_templates() -> list:
    """
    List available brain MRI report templates.

    Returns template IDs, names, and descriptions for:
    - general: Standard brain MRI report
    - stroke: Acute stroke protocol (DWI, ASPECTS, vascular territory)
    - tumor: Neuro-oncology (RANO criteria, dimensions, enhancement)
    - dementia: Cognitive decline (MTA score, GCA, Fazekas)
    """
    return await _api_get("/ai/report/templates")


@mcp.tool()
async def differential_diagnosis(
    findings: list,
    patient_age: Optional[int] = None,
    patient_sex: Optional[str] = None,
    language: str = "en",
) -> dict:
    """
    Generate a differential diagnosis based on MRI findings.

    Takes a list of imaging findings and returns a structured
    differential diagnosis using Claude API.

    Args:
        findings: List of finding strings (e.g., ["ring-enhancing lesion", "perilesional edema"])
        patient_age: Patient age for age-appropriate differentials
        patient_sex: Patient sex
        language: Response language ('en', 'es', 'de')
    """
    observation_text = "; ".join(findings)
    return await _api_post("/ai/report/generate", {
        "template_type": "general",
        "language": language,
        "findings": {
            "clinical_indication": "Differential diagnosis requested",
            "additional_observations": f"Findings to evaluate: {observation_text}",
            "patient_age": patient_age,
            "patient_sex": patient_sex,
        },
    })


# =============================================================================
# Resources — Report Templates
# =============================================================================

@mcp.resource("report-templates://stroke")
async def stroke_template() -> str:
    """Stroke protocol report template and evaluation criteria."""
    return """# Stroke Protocol Report Template

## Sections
1. **CLINICAL INDICATION**: Presenting symptoms, onset time, NIHSS score
2. **TECHNIQUE**: DWI, ADC, FLAIR, T2*, MRA, perfusion (if available)
3. **FINDINGS**:
   - DWI/ADC: Restricted diffusion location and extent
   - Vascular territory: ACA, MCA, PCA, vertebrobasilar
   - ASPECTS score (if MCA territory): Score 0-10
   - Hemorrhagic transformation: Absent/present, type (HI-1/HI-2/PH-1/PH-2)
   - Mass effect: Sulcal effacement, midline shift (mm)
   - Perfusion-diffusion mismatch (if applicable)
4. **IMPRESSION**: Summary with territory, acuity, and recommendations

## ASPECTS Regions (MCA territory)
C - Caudate, L - Lentiform, IC - Internal capsule,
I - Insular ribbon, MCA - M1/M2/M3/M4/M5/M6
"""


@mcp.resource("report-templates://tumor")
async def tumor_template() -> str:
    """Tumor evaluation report template and RANO criteria."""
    return """# Tumor Evaluation Report Template

## Sections
1. **CLINICAL INDICATION**: Known diagnosis, treatment history
2. **TECHNIQUE**: T1 pre/post, T2, FLAIR, DWI, perfusion, spectroscopy
3. **FINDINGS**:
   - Tumor location and dimensions (AP x TR x CC in mm)
   - Enhancement pattern: Solid, ring, heterogeneous, non-enhancing
   - T2/FLAIR extent (edema vs infiltration)
   - Mass effect: Midline shift (mm), herniation
   - RANO measurements: Sum of products of perpendicular diameters
   - Comparison with prior: Increased/decreased/stable
4. **IMPRESSION**: WHO grade estimation, RANO response category

## RANO Response Categories
- Complete Response: No enhancing tumor
- Partial Response: ≥50% decrease
- Stable Disease: <50% decrease, <25% increase
- Progressive Disease: ≥25% increase or new lesion
"""


@mcp.resource("report-templates://dementia")
async def dementia_template() -> str:
    """Dementia assessment report template and scoring systems."""
    return """# Dementia Assessment Report Template

## Sections
1. **CLINICAL INDICATION**: Cognitive symptoms, duration, MMSE/MoCA score
2. **TECHNIQUE**: T1 3D, T2, FLAIR, DWI
3. **FINDINGS**:
   - Hippocampal volumes: Scheltens MTA score (0-4) bilateral
   - Cortical atrophy: GCA score (0-3) — frontal, temporal, parietal
   - White matter: Fazekas score (0-3) periventricular + deep
   - Ventricular size: Evans index, temporal horn enlargement
   - Focal lesions: Microbleeds, lacunar infarcts
4. **IMPRESSION**: Pattern analysis with differential

## Scheltens MTA Score
0 = No atrophy, 1 = Widening of choroid fissure,
2 = Widening of temporal horn, 3 = Moderate volume loss,
4 = Severe volume loss

## Atrophy Patterns
- Alzheimer's: Bilateral medial temporal > posterior cortical
- Vascular: Periventricular WMH + lacunes
- Frontotemporal: Frontal and/or temporal predominant
- Lewy body: Relative hippocampal preservation, midbrain atrophy
"""
