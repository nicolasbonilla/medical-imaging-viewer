"""
Unit tests for BrainReportService — IEC 62304 Class C.

Tests verify report generation, template handling, HIPAA compliance,
and prompt construction per DD-RPT-001.

Requirement traceability:
  - REQ-FUNC-045: AI-assisted report generation
  - REQ-SAFE-006: HIPAA-compliant de-identification before external API calls
  - DD-RPT-001: Report generation via Claude API
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


@pytest.mark.unit
class TestBrainReportService:
    """Tests for BrainReportService (Class C — DD-RPT-001)."""

    def setup_method(self):
        with patch("app.services.brain_report_service.get_settings") as mock_settings:
            settings = MagicMock()
            settings.ANTHROPIC_API_KEY = "test-key-123"
            settings.CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
            settings.CLAUDE_MAX_TOKENS = 4096
            mock_settings.return_value = settings
            from app.services.brain_report_service import BrainReportService
            self.service = BrainReportService()
            self.service._settings = settings

    # =========================================================================
    # Template listing
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
        """All documented template types are present."""
        templates = self.service.list_templates()
        ids = [t["id"] for t in templates]
        expected = ["general", "ms_activity", "ms_lesion_burden", "ms_longitudinal", "ms_comprehensive"]
        for expected_id in expected:
            assert expected_id in ids, f"Template '{expected_id}' missing from list_templates()"

    def test_list_templates_have_required_fields(self):
        """Each template entry has id, name, and description."""
        templates = self.service.list_templates()
        for t in templates:
            assert "id" in t, f"Template missing 'id': {t}"
            assert "name" in t, f"Template missing 'name': {t}"
            assert "description" in t, f"Template missing 'description': {t}"
            assert isinstance(t["id"], str)
            assert isinstance(t["name"], str)
            assert isinstance(t["description"], str)
            assert len(t["name"]) > 0
            assert len(t["description"]) > 0

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
    # Report generation — success path
    # =========================================================================

    @pytest.mark.asyncio
    async def test_generate_report_success(self):
        """Successful report generation with mocked Claude API."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="# Brain MRI Report\n\nFindings: Normal brain.")]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch.object(self.service, '_get_client', return_value=mock_client):
            result = await self.service.generate_report(
                template_type="general",
                findings={"clinical_indication": "MS follow-up"},
                language="en",
            )

        assert "report_id" in result
        assert "content" in result
        assert result["content"] == "# Brain MRI Report\n\nFindings: Normal brain."
        assert result["template_type"] == "general"
        assert result["language"] == "en"
        assert "processing_time_ms" in result
        assert result["processing_time_ms"] >= 0

    @pytest.mark.asyncio
    async def test_generate_report_returns_token_usage(self):
        """Report result includes token usage statistics."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Report content.")]
        mock_response.usage = MagicMock(input_tokens=200, output_tokens=150)

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch.object(self.service, '_get_client', return_value=mock_client):
            result = await self.service.generate_report(
                template_type="general", findings={}, language="en"
            )

        assert "tokens_used" in result
        assert result["tokens_used"]["input"] == 200
        assert result["tokens_used"]["output"] == 150

    @pytest.mark.asyncio
    async def test_generate_report_includes_model_name(self):
        """Report result includes the Claude model used."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Content.")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=10)

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch.object(self.service, '_get_client', return_value=mock_client):
            result = await self.service.generate_report(
                template_type="general", findings={}, language="en"
            )

        assert result["model"] == "claude-sonnet-4-5-20250929"

    @pytest.mark.asyncio
    async def test_generate_report_unique_ids(self):
        """Each report gets a unique report_id."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Content.")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=10)

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch.object(self.service, '_get_client', return_value=mock_client):
            r1 = await self.service.generate_report(template_type="general", findings={})
            r2 = await self.service.generate_report(template_type="general", findings={})

        assert r1["report_id"] != r2["report_id"]

    # =========================================================================
    # Template selection and fallback
    # =========================================================================

    @pytest.mark.asyncio
    async def test_invalid_template_falls_back_to_general(self):
        """Unknown template type falls back to 'general'."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Fallback report.")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=10)

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch.object(self.service, '_get_client', return_value=mock_client):
            result = await self.service.generate_report(
                template_type="nonexistent_template", findings={}, language="en"
            )

        assert result["template_type"] == "general"

    @pytest.mark.asyncio
    async def test_each_template_uses_correct_system_prompt(self):
        """Each template type sends its corresponding system prompt to Claude."""
        from app.services.brain_report_service import REPORT_TEMPLATES

        for template_type in ["general", "ms_activity", "ms_lesion_burden", "ms_longitudinal"]:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Content.")]
            mock_response.usage = MagicMock(input_tokens=10, output_tokens=10)

            mock_client = MagicMock()
            mock_client.messages.create = MagicMock(return_value=mock_response)

            with patch.object(self.service, '_get_client', return_value=mock_client):
                await self.service.generate_report(
                    template_type=template_type, findings={}, language="en"
                )

            call_kwargs = mock_client.messages.create.call_args
            assert call_kwargs.kwargs["system"] == REPORT_TEMPLATES[template_type], \
                f"Wrong system prompt for template '{template_type}'"

    # =========================================================================
    # Comprehensive template max_tokens override
    # =========================================================================

    @pytest.mark.asyncio
    async def test_ms_comprehensive_uses_higher_token_limit(self):
        """ms_comprehensive template requests more tokens (up to 16384)."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Comprehensive report.")]
        mock_response.usage = MagicMock(input_tokens=500, output_tokens=3000)

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch.object(self.service, '_get_client', return_value=mock_client):
            await self.service.generate_report(
                template_type="ms_comprehensive", findings={}, language="en"
            )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        # Default is 4096, ms_comprehensive should use max(4096, 8192) = 8192
        assert call_kwargs["max_tokens"] >= 8192

    @pytest.mark.asyncio
    async def test_non_comprehensive_uses_default_tokens(self):
        """Non-comprehensive templates use the default CLAUDE_MAX_TOKENS."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Report.")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=10)

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch.object(self.service, '_get_client', return_value=mock_client):
            await self.service.generate_report(
                template_type="general", findings={}, language="en"
            )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 4096

    # =========================================================================
    # Multi-language support
    # =========================================================================

    @pytest.mark.asyncio
    async def test_language_english_prompt(self):
        """English language generates English instruction in prompt."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="English report.")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=10)

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch.object(self.service, '_get_client', return_value=mock_client):
            await self.service.generate_report(
                template_type="general", findings={}, language="en"
            )

        user_msg = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "English" in user_msg

    @pytest.mark.asyncio
    async def test_language_spanish_prompt(self):
        """Spanish language generates Spanish instruction in prompt."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Informe en espanol.")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=10)

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch.object(self.service, '_get_client', return_value=mock_client):
            await self.service.generate_report(
                template_type="general", findings={}, language="es"
            )

        user_msg = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Spanish" in user_msg

    @pytest.mark.asyncio
    async def test_language_german_prompt(self):
        """German language generates German instruction in prompt."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Bericht auf Deutsch.")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=10)

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch.object(self.service, '_get_client', return_value=mock_client):
            await self.service.generate_report(
                template_type="general", findings={}, language="de"
            )

        user_msg = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "German" in user_msg

    @pytest.mark.asyncio
    async def test_unknown_language_defaults_to_english(self):
        """Unknown language code falls back to English."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Report.")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=10)

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch.object(self.service, '_get_client', return_value=mock_client):
            await self.service.generate_report(
                template_type="general", findings={}, language="xx"
            )

        user_msg = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "English" in user_msg

    # =========================================================================
    # Findings prompt construction — HIPAA compliance (REQ-SAFE-006)
    # =========================================================================

    def test_build_findings_prompt_clinical_indication(self):
        """Clinical indication is included in the prompt."""
        prompt = self.service._build_findings_prompt(
            {"clinical_indication": "Known MS, annual follow-up"}, language="en"
        )
        assert "Known MS, annual follow-up" in prompt

    def test_build_findings_prompt_patient_age(self):
        """Patient age is included (de-identified — age alone is not PHI)."""
        prompt = self.service._build_findings_prompt(
            {"patient_age": 42}, language="en"
        )
        assert "42 years" in prompt

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
        """DIS assessment data is included in the prompt."""
        findings = {
            "dis_assessment": {
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
        assert "New lesions: 3" in prompt
        assert "Enlarged lesions: 1" in prompt
        assert "25.0%" in prompt

    # =========================================================================
    # Error handling
    # =========================================================================

    @pytest.mark.asyncio
    async def test_generate_report_api_error_propagates(self):
        """Claude API errors are propagated to the caller."""
        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(
            side_effect=Exception("API rate limit exceeded")
        )

        with patch.object(self.service, '_get_client', return_value=mock_client):
            with pytest.raises(Exception, match="API rate limit exceeded"):
                await self.service.generate_report(
                    template_type="general", findings={}, language="en"
                )

    @pytest.mark.asyncio
    async def test_generate_report_missing_key_raises_runtime(self):
        """generate_report raises RuntimeError when API key is missing."""
        self.service._client = None
        self.service._settings.ANTHROPIC_API_KEY = ""

        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            await self.service.generate_report(
                template_type="general", findings={}, language="en"
            )

    @pytest.mark.asyncio
    async def test_generate_report_none_findings_defaults_to_empty(self):
        """None findings parameter defaults to empty dict without error."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Minimal report.")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=10)

        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_response)

        with patch.object(self.service, '_get_client', return_value=mock_client):
            result = await self.service.generate_report(
                template_type="general", findings=None, language="en"
            )

        assert result["content"] == "Minimal report."

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
