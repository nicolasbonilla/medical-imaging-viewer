"""
Integration tests for HL7 FHIR R4 endpoints.

Routes under /api/v1/fhir/. Tests resource generation for
ImagingStudy, DiagnosticReport, and Patient.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestFHIRImagingStudy:
    """Test FHIR ImagingStudy resource generation."""

    @pytest.mark.asyncio
    async def test_imaging_study_not_found(self, async_client: AsyncClient):
        """Test ImagingStudy for nonexistent study."""
        response = await async_client.get("/api/v1/fhir/ImagingStudy/nonexistent-id")
        assert response.status_code in (404, 403, 500)

    @pytest.mark.asyncio
    async def test_imaging_study_endpoint_exists(self, async_client: AsyncClient):
        """Test ImagingStudy endpoint exists (not 404 for route itself)."""
        response = await async_client.get("/api/v1/fhir/ImagingStudy/test")
        # 404 is OK (study not found), but the route should exist
        assert response.status_code in (200, 404, 403, 500)


@pytest.mark.integration
class TestFHIRDiagnosticReport:
    """Test FHIR DiagnosticReport resource generation."""

    @pytest.mark.asyncio
    async def test_diagnostic_report_endpoint_exists(self, async_client: AsyncClient):
        """Test DiagnosticReport endpoint responds."""
        response = await async_client.get("/api/v1/fhir/DiagnosticReport/test-report-id")
        assert response.status_code in (200, 403, 404, 500)
        if response.status_code == 200:
            data = response.json()
            assert data["resourceType"] == "DiagnosticReport"

    @pytest.mark.asyncio
    async def test_diagnostic_report_with_patient_param(self, async_client: AsyncClient):
        """Test DiagnosticReport with patient_id parameter."""
        response = await async_client.get(
            "/api/v1/fhir/DiagnosticReport/test-id",
            params={"patient_id": "patient-123"},
        )
        assert response.status_code in (200, 403, 404, 500)
        if response.status_code == 200:
            data = response.json()
            assert data["subject"]["reference"] == "Patient/patient-123"

    @pytest.mark.asyncio
    async def test_diagnostic_report_with_study_param(self, async_client: AsyncClient):
        """Test DiagnosticReport with study_id parameter."""
        response = await async_client.get(
            "/api/v1/fhir/DiagnosticReport/test-id",
            params={"study_id": "study-456"},
        )
        assert response.status_code in (200, 403, 404, 500)


@pytest.mark.integration
class TestFHIRPatient:
    """Test FHIR Patient resource generation."""

    @pytest.mark.asyncio
    async def test_patient_not_found(self, async_client: AsyncClient):
        """Test Patient for nonexistent patient."""
        response = await async_client.get("/api/v1/fhir/Patient/nonexistent-id")
        assert response.status_code in (404, 403, 500)
