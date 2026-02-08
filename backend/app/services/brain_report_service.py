"""
Brain Report Generation Service using Claude API.

Generates structured radiology reports for brain MRI studies.
Templates: stroke, tumor, dementia, general.

HIPAA Compliance:
- Patient data is de-identified before sending to Claude API
- Only clinical findings and measurements are transmitted
- No names, IDs, or dates are sent to the external API

@module services.brain_report_service
"""

import time
import uuid
from typing import Optional, List, Dict, Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Report templates — system prompts for Claude
REPORT_TEMPLATES: Dict[str, str] = {
    "general": (
        "You are a board-certified neuroradiologist generating a structured "
        "brain MRI report. Use standard radiology reporting format with sections: "
        "CLINICAL INDICATION, TECHNIQUE, FINDINGS, IMPRESSION. "
        "Be precise with anatomical terminology. Use standard abbreviations. "
        "Report abnormalities with location, size, signal characteristics."
    ),
    "stroke": (
        "You are a board-certified neuroradiologist specializing in stroke imaging. "
        "Generate a structured brain MRI report focused on acute stroke evaluation. "
        "Include: CLINICAL INDICATION, TECHNIQUE, FINDINGS (with DWI/ADC analysis, "
        "vascular territory, ASPECTS score if applicable, hemorrhagic transformation), "
        "IMPRESSION with differential diagnosis. "
        "Note: perfusion-diffusion mismatch if relevant."
    ),
    "tumor": (
        "You are a board-certified neuroradiologist specializing in neuro-oncology. "
        "Generate a structured brain MRI report focused on tumor evaluation. "
        "Include: CLINICAL INDICATION, TECHNIQUE, FINDINGS (tumor location, "
        "dimensions in 3 planes, enhancement pattern, edema, mass effect, "
        "midline shift, herniation, RANO criteria measurements if follow-up), "
        "IMPRESSION with differential diagnosis and WHO grade estimation."
    ),
    "dementia": (
        "You are a board-certified neuroradiologist specializing in neurodegenerative diseases. "
        "Generate a structured brain MRI report focused on dementia/cognitive decline evaluation. "
        "Include: CLINICAL INDICATION, TECHNIQUE, FINDINGS (hippocampal volumes with "
        "Scheltens MTA score, cortical atrophy pattern with GCA score, Fazekas score "
        "for white matter hyperintensities, ventricular enlargement), "
        "IMPRESSION with pattern analysis suggesting specific diagnoses "
        "(Alzheimer's, vascular dementia, frontotemporal dementia, Lewy body, etc.)."
    ),
}


class BrainReportService:
    """
    Generates structured brain MRI reports using Claude API.

    Features:
    - Template-based report generation (stroke, tumor, dementia, general)
    - Integrates volumetry data when available
    - Multi-language support (en, es, de)
    - HIPAA-compliant: de-identifies all patient data before API call
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

        # Clinical context (de-identified)
        if findings.get("clinical_indication"):
            parts.append(f"Clinical indication: {findings['clinical_indication']}")

        if findings.get("technique"):
            parts.append(f"Technique/Sequences: {findings['technique']}")

        if findings.get("patient_age"):
            parts.append(f"Patient age: {findings['patient_age']} years")

        if findings.get("patient_sex"):
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

        # Additional observations
        if findings.get("additional_observations"):
            parts.append(f"\nAdditional observations: {findings['additional_observations']}")

        return "\n".join(parts)

    async def generate_report(
        self,
        template_type: str = "general",
        findings: Optional[Dict[str, Any]] = None,
        volumetry: Optional[Dict[str, Any]] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Generate a structured brain MRI report.

        Args:
            template_type: Report template (general, stroke, tumor, dementia)
            findings: Clinical findings dict (de-identified)
            volumetry: Volumetry results dict (optional)
            language: Report language (en, es, de)

        Returns:
            Dict with report_id, content, template_type, language, processing_time_ms
        """
        start_time = time.time()
        report_id = str(uuid.uuid4())

        if findings is None:
            findings = {}

        # Validate template
        if template_type not in REPORT_TEMPLATES:
            template_type = "general"

        system_prompt = REPORT_TEMPLATES[template_type]
        user_prompt = self._build_findings_prompt(findings, volumetry, language)

        logger.info(
            f"[Report] Generating {template_type} report in {language}",
            extra={"report_id": report_id},
        )

        try:
            client = self._get_client()
            message = client.messages.create(
                model=self._settings.CLAUDE_MODEL,
                max_tokens=self._settings.CLAUDE_MAX_TOKENS,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt},
                ],
            )

            content = message.content[0].text
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
            }

        except Exception as e:
            logger.error(f"[Report] Generation failed: {e}")
            raise

    def list_templates(self) -> List[Dict[str, str]]:
        """List available report templates."""
        templates = [
            {
                "id": "general",
                "name": "General Brain MRI",
                "description": "Standard structured brain MRI report",
            },
            {
                "id": "stroke",
                "name": "Stroke Protocol",
                "description": "Acute stroke evaluation with DWI, vascular territory, ASPECTS",
            },
            {
                "id": "tumor",
                "name": "Tumor Follow-up",
                "description": "Neuro-oncology report with RANO criteria and measurements",
            },
            {
                "id": "dementia",
                "name": "Dementia Assessment",
                "description": "Cognitive decline evaluation with MTA score, GCA, Fazekas",
            },
        ]
        return templates
