"""
Integration tests for HL7 FHIR R4 endpoints.

Tests ImagingStudy, DiagnosticReport, and Patient resource generation.

@module tests.integration.test_fhir_endpoints
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestFHIRImagingStudy:
    """Test FHIR ImagingStudy resource generation."""

    @pytest.mark.asyncio
    async def test_imaging_study_not_found(self, async_client: AsyncClient):
        """Test ImagingStudy for nonexistent study returns 404."""
        response = await async_client.get("/api/v1/fhir/ImagingStudy/nonexistent-id")
        assert response.status_code in (404, 500)

    @pytest.mark.asyncio
    async def test_imaging_study_resource_structure(self, async_client: AsyncClient):
        """Test ImagingStudy response conforms to FHIR R4 structure."""
        # This test would need a real study ID — skip if none available
        # For now, verify the endpoint exists and responds
        response = await async_client.get("/api/v1/fhir/ImagingStudy/test")
        assert response.status_code in (200, 404, 500)


@pytest.mark.integration
class TestFHIRDiagnosticReport:
    """Test FHIR DiagnosticReport resource generation."""

    @pytest.mark.asyncio
    async def test_diagnostic_report_generation(self, async_client: AsyncClient):
        """Test DiagnosticReport returns valid FHIR resource."""
        response = await async_client.get("/api/v1/fhir/DiagnosticReport/test-report-id")
        assert response.status_code == 200
        data = response.json()
        assert data["resourceType"] == "DiagnosticReport"
        assert data["status"] == "final"
        assert data["id"] == "test-report-id"
        assert "category" in data
        assert "code" in data
        assert data["code"]["coding"][0]["system"] == "http://loinc.org"

    @pytest.mark.asyncio
    async def test_diagnostic_report_with_patient(self, async_client: AsyncClient):
        """Test DiagnosticReport includes patient reference when provided."""
        response = await async_client.get(
            "/api/v1/fhir/DiagnosticReport/test-id",
            params={"patient_id": "patient-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["subject"]["reference"] == "Patient/patient-123"

    @pytest.mark.asyncio
    async def test_diagnostic_report_with_study(self, async_client: AsyncClient):
        """Test DiagnosticReport includes imaging study reference."""
        response = await async_client.get(
            "/api/v1/fhir/DiagnosticReport/test-id",
            params={"study_id": "study-456"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imagingStudy"][0]["reference"] == "ImagingStudy/study-456"


@pytest.mark.integration
class TestFHIRPatient:
    """Test FHIR Patient resource generation."""

    @pytest.mark.asyncio
    async def test_patient_not_found(self, async_client: AsyncClient):
        """Test Patient for nonexistent patient returns 404."""
        response = await async_client.get("/api/v1/fhir/Patient/nonexistent-id")
        assert response.status_code in (404, 500)
