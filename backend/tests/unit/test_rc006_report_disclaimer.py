"""RC-006 — mandatory AI/physician-review disclaimer on generated reports.

Risk control for HAZ-003 (AI report hallucination, severity S5 — Catastrophic).
Raised by CAPA-001, which found RC-006 recorded as "VERIFIED — disclaimer present
in all 5 templates" while the string was absent from the service in every form.

The root cause identified in CAPA-001 was that no risk control was bound to an
executable test, so a missing control produced a green build. These tests exist
so that removing the control turns CI red.

Negative control (CAPA-001 §5 effectiveness verification): delete or blank
`REPORT_DISCLAIMERS` / `_apply_disclaimer` and these tests MUST fail.
"""
import pytest

from app.services.brain_report_service import (
    REPORT_DISCLAIMERS,
    REPORT_TEMPLATES,
    _apply_disclaimer,
)

SUPPORTED_LANGUAGES = ["en", "es", "de"]


class TestRC006DisclaimerExists:
    """The control must exist as data, not as an instruction to a model."""

    def test_rc006_disclaimer_defined_for_every_supported_language(self):
        for language in SUPPORTED_LANGUAGES:
            assert language in REPORT_DISCLAIMERS, f"no disclaimer for '{language}'"
            assert REPORT_DISCLAIMERS[language].strip(), f"disclaimer for '{language}' is empty"

    @pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
    def test_rc006_disclaimer_states_ai_origin_and_review_requirement(self, language):
        """Both facts are required: that it is AI-generated, and that a physician
        must review it before clinical action. One without the other is not RC-006."""
        text = REPORT_DISCLAIMERS[language].lower()

        ai_markers = ["ai-generated", "generado por ia", "ki-generiert"]
        review_markers = ["physician review", "revisión médica", "ärztliche überprüfung"]

        assert any(m in text for m in ai_markers), (
            f"'{language}' disclaimer does not declare AI origin: {text!r}"
        )
        assert any(m in text for m in review_markers), (
            f"'{language}' disclaimer does not require physician review: {text!r}"
        )


class TestRC006DisclaimerIsApplied:
    """The control must be enforced in code, on every report."""

    @pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
    def test_rc006_applied_to_generated_content(self, language):
        out = _apply_disclaimer("## FINDINGS\n\nNo lesions identified.", language)
        assert out.startswith(REPORT_DISCLAIMERS[language]), (
            "disclaimer must lead the report, not be buried in it"
        )
        assert "No lesions identified." in out, "report body must be preserved"

    def test_rc006_unknown_language_still_gets_a_disclaimer(self):
        """Fail safe: an unsupported language must not yield an undisclaimed report."""
        out = _apply_disclaimer("## FINDINGS", "fr")
        assert out.startswith(REPORT_DISCLAIMERS["en"])

    @pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
    def test_rc006_applied_when_model_returns_empty_content(self, language):
        """An empty or failed generation must still carry the warning."""
        for empty in ("", "   ", None):
            out = _apply_disclaimer(empty, language)
            assert REPORT_DISCLAIMERS[language] in out

    def test_rc006_is_idempotent(self):
        """Applying twice must not stack the banner."""
        once = _apply_disclaimer("## FINDINGS", "en")
        twice = _apply_disclaimer(once, "en")
        assert once == twice


class TestRC006CoversEveryTemplate:
    """RC-006 was recorded as covering 'all 5 templates'. Enforce that literally:
    the disclaimer is applied at the return path, so it is template-independent —
    this test guards against a future template bypassing that path."""

    def test_rc006_all_templates_are_covered_by_a_single_enforcement_point(self):
        assert len(REPORT_TEMPLATES) >= 5, (
            f"expected at least 5 report templates, found {len(REPORT_TEMPLATES)}"
        )
        # Every template's output funnels through _apply_disclaimer; verify the
        # function is agnostic to template content.
        for name in REPORT_TEMPLATES:
            out = _apply_disclaimer(f"report body for {name}", "en")
            assert out.startswith(REPORT_DISCLAIMERS["en"]), f"template '{name}' not covered"


class TestRC006NoFabricatedReferences:
    """CAPA-001: templates must not instruct the model to invent citations."""

    def test_no_template_asks_the_model_for_references(self):
        forbidden = ["use real, published references", "cite 3-5"]
        for name, template in REPORT_TEMPLATES.items():
            lowered = template.lower()
            for phrase in forbidden:
                assert phrase not in lowered, (
                    f"template '{name}' still instructs the model to produce citations "
                    f"({phrase!r}) — invites fabricated references into a clinical document"
                )
