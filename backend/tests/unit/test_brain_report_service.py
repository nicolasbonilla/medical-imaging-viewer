"""
Unit tests for BrainReportService — IEC 62304 Class C.

Tests verify report generation, template handling and prompt construction
per DD-RPT-001. De-identification of what is sent to the provider (CAPA-014,
REQ-SEC-021..023) is tested in test_capa014_report_provider_payload.py.

Requirement traceability:
  - REQ-FUNC-045: AI-assisted report generation
  - REQ-SAFE-006: AI disclaimer (RC-006)
  - DD-RPT-001: Report generation via Claude API
  - REQ-FUNC-116, REQ-SAFE-048..051 (DRAFT, PENDING owner approval): the verified report. The generate_report,
    list_templates and error-handling tests below were rewritten for it (2026-11-10): the model writes two comments
    in a fixed format, the answer is read by block type, every template id gives the same structure, a provider
    failure or a missing key gives a measurements-only report instead of an exception. The tests of the retired
    prompt builder and templates (kept as the benchmark's arm A0 reference) are unchanged.
"""

import pytest
from datetime import date
from unittest.mock import MagicMock, patch, AsyncMock

# CAPA-014 (RC-065): the service sends nothing without the patient's identifiers.
from app.services.report_payload_guard import PatientIdentifiers

TEST_IDENTIFIERS = PatientIdentifiers.from_record({
    "mrn": "MRN-TEST-0001", "given_name": "Testgiven", "family_name": "Testfamily",
    "birth_date": date(1980, 1, 1),
})


# Verified report (REQ-FUNC-116, DRAFT): a measurement to comment on, and the model's answer in the fixed format.
MEASURED = {"lesion_analysis": {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
                                "size_distribution": {"small": 4, "medium": 2, "large": 1}}}


def _answer(findings_comment="Most lesions are small.", impression_comment="Automatic marking, to be reviewed.",
            input_tokens=10, output_tokens=10):
    block = MagicMock(type="text", text=f"[FINDINGS_COMMENT]\n{findings_comment}\n[IMPRESSION_COMMENT]\n"
                                         f"{impression_comment}")
    return MagicMock(content=[block], stop_reason="end_turn", model="claude-sonnet-5-5",
                     usage=MagicMock(input_tokens=input_tokens, output_tokens=output_tokens))


def _client(response):
    client = MagicMock()
    client.messages.create = MagicMock(return_value=response)
    return client


@pytest.mark.unit
class TestBrainReportService:
    """Tests for BrainReportService (Class C — DD-RPT-001)."""

    def setup_method(self):
        with patch("app.services.brain_report_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.ANTHROPIC_API_KEY = "test-key-123"
            settings.CLAUDE_MODEL = "claude-sonnet-5-5"
            settings.CLAUDE_MAX_TOKENS = 4096
            settings.REPORT_LLM_ENABLED = True
            mock_settings.return_value = settings
            from app.services.brain_report_service import BrainReportService
            self.service = BrainReportService()
            self.service._settings = settings

    # =========================================================================
    # Template listing (verified report: one structure; the retired templates as reference)
    # =========================================================================

    def test_list_templates_returns_list(self):
        """Verify list_templates returns a non-empty list."""
        templates = self.service.list_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_list_templates_contains_general(self):
        """The 'general' template must always be available."""
        templates = self.service.list_templates()
        ids = [t["id"] for t in templates]
        assert "general" in ids

    def test_list_templates_contains_all_documented_types(self):
        """Verified report (DRAFT): the list offers the one verified structure; the retired templates' ids are kept
        in the reference list (and still accepted by the route, test_invalid_template_falls_back_to_general)."""
        assert [t["id"] for t in self.service.list_templates()] == ["general"]
        retired = [t["id"] for t in self.service.list_retired_templates()]
        for expected_id in ["general", "ms_activity", "ms_lesion_burden", "ms_longitudinal", "ms_comprehensive"]:
            assert expected_id in retired, f"Template '{expected_id}' missing from list_retired_templates()"

    def test_list_templates_have_required_fields(self):
        """Each template entry has id, name, and description."""
        for t in self.service.list_templates() + self.service.list_retired_templates():
            assert isinstance(t["id"], str) and isinstance(t["name"], str) and isinstance(t["description"], str)
            assert len(t["name"]) > 0 and len(t["description"]) > 0

    # =========================================================================
    # Client initialization — ANTHROPIC_API_KEY validation
    # =========================================================================

    def test_get_client_missing_api_key_raises(self):
        """Missing ANTHROPIC_API_KEY raises RuntimeError."""
        self.service._client = None
        self.service._settings.ANTHROPIC_API_KEY = ""
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            self.service._get_client()

    def test_get_client_none_api_key_raises(self):
        """None ANTHROPIC_API_KEY raises RuntimeError."""
        self.service._client = None
        self.service._settings.ANTHROPIC_API_KEY = None
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            self.service._get_client()

    def test_get_client_lazy_initialization(self):
        """Client is None until _get_client() is called (lazy loading)."""
        assert self.service._client is None

    def test_get_client_caches_instance(self):
        """Once created, the same client instance is reused."""
        mock_module = MagicMock()
        mock_module.Anthropic.return_value = MagicMock()
        self.service._settings.ANTHROPIC_API_KEY = "valid-key"
        self.service._client = None

        with patch.dict("sys.modules", {"anthropic": mock_module}):
            client1 = self.service._get_client()
            client2 = self.service._get_client()
            assert client1 is client2
            mock_module.Anthropic.assert_called_once()

    # =========================================================================
    # Report generation — success path (verified report)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_generate_report_success(self):
        """The verified draft: disclaimer, code-written measurements, the checked comments."""
        mock_client = _client(_answer("Most lesions are small.", "Automatic marking, to be reviewed."))
        with patch.object(self.service, '_get_client', return_value=mock_client):
            result = await self.service.generate_report(identifiers=TEST_IDENTIFIERS, template_type="general",
                                                        findings={**MEASURED, "clinical_indication": "MS follow-up"},
                                                        language="en")
        from app.services.brain_report_service import REPORT_DISCLAIMERS
        assert "report_id" in result and "content" in result
        assert result["content"].startswith(REPORT_DISCLAIMERS["en"])     # RC-006: the disclaimer first, in code
        assert "Lesions marked: 7 (MAGNIMS 2021: exact count below 20)." in result["content"]
        assert "Most lesions are small." in result["content"] and "MS follow-up" not in result["content"]
        assert result["verification"]["outcome"] == "passed_0"
        assert result["template_type"] == "general" and result["language"] == "en"
        assert result["processing_time_ms"] >= 0

    @pytest.mark.asyncio
    async def test_generate_report_returns_token_usage(self):
        """Report result includes token usage statistics."""
        mock_client = _client(_answer(input_tokens=200, output_tokens=150))
        with patch.object(self.service, '_get_client', return_value=mock_client):
            result = await self.service.generate_report(identifiers=TEST_IDENTIFIERS, template_type="general",
                                                        findings=MEASURED, language="en")
        assert result["tokens_used"] == {"input": 200, "output": 150}

    @pytest.mark.asyncio
    async def test_generate_report_includes_model_name(self):
        """Report result includes the Claude model used (the new default, never the retiring one)."""
        mock_client = _client(_answer())
        with patch.object(self.service, '_get_client', return_value=mock_client):
            result = await self.service.generate_report(identifiers=TEST_IDENTIFIERS, template_type="general",
                                                        findings=MEASURED, language="en")
        assert result["model"] == "claude-sonnet-5-5"
        assert mock_client.messages.create.call_args.kwargs["model"] == "claude-sonnet-5-5"

    @pytest.mark.asyncio
    async def test_generate_report_unique_ids(self):
        """Each report gets a unique report_id."""
        mock_client = _client(_answer())
        with patch.object(self.service, '_get_client', return_value=mock_client):
            r1 = await self.service.generate_report(identifiers=TEST_IDENTIFIERS, template_type="general", findings={})
            r2 = await self.service.generate_report(identifiers=TEST_IDENTIFIERS, template_type="general", findings={})
        assert r1["report_id"] != r2["report_id"]

    # =========================================================================
    # Template selection and fallback
    # =========================================================================

    @pytest.mark.asyncio
    async def test_invalid_template_falls_back_to_general(self):
        """Unknown template type falls back to 'general'."""
        mock_client = _client(_answer())
        with patch.object(self.service, '_get_client', return_value=mock_client):
            result = await self.service.generate_report(identifiers=TEST_IDENTIFIERS,
                                                        template_type="nonexistent_template", findings=MEASURED,
                                                        language="en")
        assert result["template_type"] == "general"

    @pytest.mark.asyncio
    async def test_each_template_uses_correct_system_prompt(self):
        """Verified report (DRAFT): every template id, with or without an evaluated DIS, sends the ONE fixed system
        prompt of the verified flow (was: the template, or its not-evaluated variant)."""
        from app.services import verified_report
        from app.services.brain_report_service import REPORT_TEMPLATES
        for template_type in REPORT_TEMPLATES:
            for dis in ({"evaluation_status": "not_evaluated"},
                        {"evaluation_status": "evaluated", "dis_met": True, "regions_with_lesions": 2}):
                mock_client = _client(_answer())
                with patch.object(self.service, '_get_client', return_value=mock_client):
                    await self.service.generate_report(identifiers=TEST_IDENTIFIERS, template_type=template_type,
                                                       findings={**MEASURED, "dis_assessment": dis}, language="en")
                assert mock_client.messages.create.call_args.kwargs["system"] == verified_report.SYSTEM_PROMPT

    # =========================================================================
    # Token limit and request parameters
    # =========================================================================

    @pytest.mark.asyncio
    async def test_ms_comprehensive_uses_higher_token_limit(self):
        """Verified report (DRAFT; name kept): the two comments need no larger limit — every template uses
        CLAUDE_MAX_TOKENS (was: 8192+ for ms_comprehensive)."""
        mock_client = _client(_answer())
        with patch.object(self.service, '_get_client', return_value=mock_client):
            await self.service.generate_report(identifiers=TEST_IDENTIFIERS, template_type="ms_comprehensive",
                                               findings=MEASURED, language="en")
        assert mock_client.messages.create.call_args.kwargs["max_tokens"] == 4096

    @pytest.mark.asyncio
    async def test_non_comprehensive_uses_default_tokens(self):
        """Non-comprehensive templates use the default CLAUDE_MAX_TOKENS; the allow-listed parameters are sent."""
        mock_client = _client(_answer())
        with patch.object(self.service, '_get_client', return_value=mock_client):
            await self.service.generate_report(identifiers=TEST_IDENTIFIERS, template_type="general",
                                               findings=MEASURED, language="en")
        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["max_tokens"] == 4096
        assert kwargs["extra_body"] == {"thinking": {"type": "between_tools"}, "output_config": {"effort": "low"}}
        assert "temperature" not in kwargs and "top_p" not in kwargs        # 400 on the current models

    # =========================================================================
    # Multi-language support
    # =========================================================================

    @pytest.mark.asyncio
    @pytest.mark.parametrize("language,name", [("en", "English"), ("es", "Spanish"), ("de", "German"),
                                               ("xx", "English")])
    async def test_language_prompt(self, language, name):
        """The first message names the report language; an unknown code falls back to English."""
        mock_client = _client(_answer())
        with patch.object(self.service, '_get_client', return_value=mock_client):
            await self.service.generate_report(identifiers=TEST_IDENTIFIERS, template_type="general",
                                               findings=MEASURED, language=language)
        user_msg = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert user_msg.startswith(f"Write the draft in {name}.")

    # =========================================================================
    # Findings prompt construction (what may be sent: test_capa014_report_provider_payload.py)
    # =========================================================================

    def test_build_findings_prompt_clinical_indication(self):
        """CAPA-014 (RC-064): the clinical indication is free text and is never sent (was: included);
        the route adds it to the draft after the model returns. The model is told so only when something
        was typed (CAPA-014 second review, N6)."""
        from app.services.report_payload_guard import provider_payload
        payload = provider_payload({"clinical_indication": "Known MS, annual follow-up"}, None)
        prompt = self.service._build_findings_prompt(payload.findings, language="en")
        assert "Known MS, annual follow-up" not in prompt
        assert "added to the draft by the application" in prompt

    def test_build_findings_prompt_patient_age(self):
        """CAPA-014 (RC-064): the age reaches the prompt as the 5-year band of the structured
        payload (was: the exact age)."""
        prompt = self.service._build_findings_prompt(
            {"patient_age": "40-44"}, language="en"
        )
        assert "Patient age band: 40-44 (years)" in prompt

    def test_build_findings_prompt_patient_sex(self):
        """Patient sex is included with readable label."""
        prompt_m = self.service._build_findings_prompt({"patient_sex": "M"}, language="en")
        prompt_f = self.service._build_findings_prompt({"patient_sex": "F"}, language="en")
        assert "Male" in prompt_m
        assert "Female" in prompt_f

    def test_build_findings_prompt_no_phi(self):
        """Prompt does NOT include patient name, DOB, MRN, or other PHI."""
        findings = {
            "clinical_indication": "MS follow-up",
            "patient_age": 45,
            "patient_sex": "F",
            "technique": "3T MRI with contrast",
        }
        prompt = self.service._build_findings_prompt(findings, language="en")
        # Should not contain PHI fields
        assert "patient_name" not in prompt.lower()
        assert "mrn" not in prompt.lower()
        assert "date_of_birth" not in prompt.lower()
        assert "ssn" not in prompt.lower()

    def test_build_findings_prompt_empty_findings(self):
        """Empty findings dict produces minimal but valid prompt."""
        prompt = self.service._build_findings_prompt({}, language="en")
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "English" in prompt

    def test_build_findings_prompt_anomalies(self):
        """Anomaly findings are included in the prompt."""
        findings = {
            "anomalies": [
                {"type": "lesion", "location": "periventricular", "confidence": 0.95,
                 "volume_mm3": 125.5},
            ]
        }
        prompt = self.service._build_findings_prompt(findings, language="en")
        assert "lesion" in prompt
        assert "periventricular" in prompt
        assert "95%" in prompt
        assert "125.5" in prompt

    def test_build_findings_prompt_volumetry_data(self):
        """Volumetry data is included in the prompt."""
        volumetry = {
            "total_brain_volume_ml": 1200.5,
            "intracranial_volume_ml": 1450.0,
            "structures": [
                {
                    "structure_name": "Left Hippocampus",
                    "volume_ml": 2.1,
                    "is_abnormal": True,
                    "abnormality_type": "atrophy",
                    "normative_percentile": 3.5,
                },
            ],
        }
        prompt = self.service._build_findings_prompt({}, volumetry=volumetry, language="en")
        assert "1200.5" in prompt
        assert "1450.0" in prompt
        assert "Left Hippocampus" in prompt
        assert "atrophy" in prompt

    def test_build_findings_prompt_lesion_analysis(self):
        """Lesion analysis data from Phase 10 is included in the prompt."""
        findings = {
            "lesion_analysis": {
                "total_count": 12,
                "total_burden_mm3": 1500.0,
                "total_burden_ml": 1.5,
                "regions": {
                    "Periventricular": {"lesion_count": 5, "total_volume_mm3": 800.0,
                                        "total_volume_ml": 0.8},
                },
                "size_distribution": {"small": 8, "medium": 3, "large": 1},
            }
        }
        prompt = self.service._build_findings_prompt(findings, language="en")
        assert "Total lesions: 12" in prompt
        assert "Periventricular" in prompt

    def test_build_findings_prompt_dis_assessment(self):
        """DIS assessment data is included in the prompt — for a block the server EVALUATED on a confirmed
        segmentation (PRB-003, RC-070: any other block is reported as NOT EVALUATED; see
        test_prb003_dis_requires_confirmed_segmentation.py)."""
        findings = {
            "dis_assessment": {
                "evaluation_status": "evaluated",
                "dis_met": True,
                "regions_with_lesions": 3,
                "total_dis_regions": 4,
                "region_details": {
                    "Periventricular": {"present": True},
                    "Cortical": {"present": True},
                    "Infratentorial": {"present": True},
                    "Deep WM": {"present": False},
                },
            }
        }
        prompt = self.service._build_findings_prompt(findings, language="en")
        assert "DIS Assessment: MET" in prompt
        assert "3/4" in prompt

    def test_build_findings_prompt_longitudinal(self):
        """Longitudinal comparison data is included in the prompt."""
        findings = {
            "longitudinal": {
                "burden_tp1_ml": 1.2,
                "burden_tp2_ml": 1.5,
                "total_lesions_tp1": 10,
                "total_lesions_tp2": 13,
                "burden_delta_percent": 25.0,
                "status_counts": {
                    "new": 3, "enlarged": 1, "resolved": 0, "shrunk": 1, "stable": 9,
                },
            }
        }
        prompt = self.service._build_findings_prompt(findings, language="en")
        # Longitudinal results are UNCONFIRMED change candidates (CAPA-013, RC-060; was
        # "candidate, registration unverified"), with a NOTE telling the generator not to report
        # them as new/enlarging lesions, classify the disease course from them or use them for DIT.
        assert "New-lesion candidates (unconfirmed): 3" in prompt
        assert "Enlarging candidates (unconfirmed): 1" in prompt
        assert "UNCONFIRMED CHANGE CANDIDATES" in prompt
        assert "Radiologist decisions on these candidates are recorded in the application" in prompt
        assert "25.0%" in prompt

    # =========================================================================
    # Error handling (verified report: the measurements are delivered without the comments)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_generate_report_api_error_gives_the_measurements_only(self):
        """A provider error no longer fails the report (was: propagated): the comments are not available, the
        code-written measurements are delivered with the note, the reason is recorded (RC-106)."""
        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(side_effect=Exception("API rate limit exceeded"))
        with patch.object(self.service, '_get_client', return_value=mock_client):
            result = await self.service.generate_report(identifiers=TEST_IDENTIFIERS, template_type="general",
                                                        findings=MEASURED, language="en")
        assert result["verification"]["reason"] == "provider_error"
        assert "Lesions marked: 7" in result["content"] and "Interpretive text not available" in result["content"]

    @pytest.mark.asyncio
    async def test_generate_report_missing_key_gives_the_measurements_only(self):
        """No ANTHROPIC_API_KEY: nothing is sent; the measurements-only report says the comments are unavailable."""
        self.service._client = None
        self.service._settings.ANTHROPIC_API_KEY = ""
        result = await self.service.generate_report(identifiers=TEST_IDENTIFIERS, template_type="general",
                                                    findings=MEASURED, language="en")
        assert result["verification"]["reason"] == "not_configured" and result["model"] is None
        assert self.service._client is None

    @pytest.mark.asyncio
    async def test_generate_report_none_findings_defaults_to_empty(self):
        """None findings parameter defaults to empty dict without error; nothing to comment on, nothing sent."""
        mock_client = _client(_answer())
        with patch.object(self.service, '_get_client', return_value=mock_client):
            result = await self.service.generate_report(identifiers=TEST_IDENTIFIERS, template_type="general",
                                                        findings=None, language="en")
        from app.services.brain_report_service import REPORT_DISCLAIMERS
        assert result["content"].startswith(REPORT_DISCLAIMERS["en"])     # RC-006: disclaimer unconditionally
        assert "Lesion count: not computed." in result["content"]
        assert result["verification"]["reason"] == "no_measurement_for_comment"
        mock_client.messages.create.assert_not_called()

    # =========================================================================
    # REPORT_TEMPLATES integrity
    # =========================================================================

    def test_all_templates_are_non_empty_strings(self):
        """Every template in REPORT_TEMPLATES is a non-empty string."""
        from app.services.brain_report_service import REPORT_TEMPLATES
        for key, prompt in REPORT_TEMPLATES.items():
            assert isinstance(prompt, str), f"Template '{key}' is not a string"
            assert len(prompt) > 100, f"Template '{key}' is suspiciously short ({len(prompt)} chars)"

    def test_all_templates_contain_format_instructions(self):
        """Every template includes the shared FORMAT_INSTRUCTIONS block."""
        from app.services.brain_report_service import REPORT_TEMPLATES
        for key, prompt in REPORT_TEMPLATES.items():
            assert "OUTPUT FORMAT RULES" in prompt, \
                f"Template '{key}' missing FORMAT_INSTRUCTIONS"

    def test_all_templates_have_impression_section(self):
        """Every template instructs Claude to include an IMPRESSION section."""
        from app.services.brain_report_service import REPORT_TEMPLATES
        for key, prompt in REPORT_TEMPLATES.items():
            assert "IMPRESSION" in prompt, \
                f"Template '{key}' missing IMPRESSION section directive"

    def test_templates_prohibit_phi(self):
        """FORMAT_INSTRUCTIONS block prohibits patient demographics."""
        from app.services.brain_report_service import _FORMAT_INSTRUCTIONS
        assert "DO NOT" in _FORMAT_INSTRUCTIONS
        assert "patient demographics" in _FORMAT_INSTRUCTIONS.lower()
