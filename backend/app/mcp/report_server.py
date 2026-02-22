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

@mcp.resource("report-templates://ms-activity")
async def ms_activity_template() -> str:
    """MS activity assessment report template reference."""
    return """# MS Activity Assessment Report Template

## Required Sections:
1. CLINICAL INDICATION: MS type, disease duration, current DMT, EDSS score
2. TECHNIQUE: MRI sequences (T1, T2, FLAIR, T1+Gd, DWI)
3. FINDINGS:
   - New T2/FLAIR lesions since prior study (count, location)
   - Gadolinium-enhancing lesions (count, location, size)
   - Total T2 lesion burden change
   - Brain atrophy assessment
4. IMPRESSION: Disease activity status, treatment response assessment

## Key Terminology:
- McDonald criteria for MS diagnosis
- DIS (Dissemination in Space) / DIT (Dissemination in Time)
- RRMS / SPMS / PPMS classification
- NEDA (No Evidence of Disease Activity) status
"""


@mcp.resource("report-templates://ms-lesion-burden")
async def ms_lesion_burden_template() -> str:
    """MS lesion burden analysis report template reference."""
    return """# MS Lesion Burden Analysis Report Template

## Required Sections:
1. LESION INVENTORY:
   - Total lesion count and volume (mL)
   - Distribution: periventricular, juxtacortical, infratentorial, spinal
   - Active vs chronic lesion ratio
2. VOLUMETRIC ANALYSIS:
   - Total T2 lesion volume
   - T1 black hole volume
   - Brain parenchymal fraction (atrophy measure)
3. LONGITUDINAL COMPARISON:
   - New lesions since prior study
   - Resolved/stable lesions
   - Volume change trends
4. CLINICAL CORRELATION:
   - Lesion burden vs EDSS correlation
   - Disease progression risk assessment
   - Treatment efficacy indicators
"""
