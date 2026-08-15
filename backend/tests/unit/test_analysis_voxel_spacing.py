"""Voxel spacing for the analysis suite must come from the SOURCE IMAGE.

Production incident (live-confirmed 500s): lesion-analysis, dis-assessment and
compare all resolved voxel_spacing from the SEGMENTATION metadata via
resolve_voxel_spacing() — but SegmentationMetadata never carries pixel_spacing /
slice_thickness (no `extra_fields`), so it raised on EVERY call and the whole
MAGNIMS analysis suite returned 500. The RC-024 unit test only exercised a mock
object WITH extra_fields, so it never caught this against the real metadata.

These tests exercise the REAL SegmentationMetadata and the new source-image
resolver, so the regression cannot recur silently.
"""
import numpy as np
import nibabel as nib
import pytest

from app.api.routes.segmentation_analysis import _voxel_spacing_from_source_image
from app.models.schemas import SegmentationMetadata
from app.utils import resolve_voxel_spacing, VoxelSpacingUnavailableError


def _nifti_bytes(zooms):
    """A NIfTI (native a0,a1,k) with the given (za0, za1, zk) zooms."""
    img = nib.Nifti1Image(np.zeros((4, 5, 3), dtype=np.uint8), np.eye(4))
    img.header.set_zooms(tuple(zooms))
    return img.to_bytes()


class _FakeStorage:
    def __init__(self, data: bytes):
        self._data = data

    async def download_file(self, bucket, file_id):
        return self._data


class TestRootCauseIsPinned:
    def test_resolve_voxel_spacing_raises_on_real_segmentation_metadata(self):
        """The exact defect: resolve_voxel_spacing on a real SegmentationMetadata
        (no extra_fields) raises — which is why the analysis suite 500'd. This
        documents WHY spacing must not be taken from segmentation metadata."""
        meta = SegmentationMetadata(file_id="img-1")
        with pytest.raises(VoxelSpacingUnavailableError):
            resolve_voxel_spacing(meta, context="seg")


class TestSourceImageResolver:
    @pytest.mark.asyncio
    async def test_resolves_dz_dy_dx_from_image_zooms(self):
        # NIfTI zooms native (za0=0.9, za1=0.8, zk=3.0). Internal mask is
        # (D,H,W)=(k,a0,a1) -> spacing (dz=zk, dy=za0, dx=za1) = (3.0, 0.9, 0.8).
        storage = _FakeStorage(_nifti_bytes((0.9, 0.8, 3.0)))
        spacing = await _voxel_spacing_from_source_image("img-1", storage, context="seg")
        assert spacing == pytest.approx((3.0, 0.9, 0.8))

    @pytest.mark.asyncio
    async def test_missing_file_id_raises_cleanly(self):
        storage = _FakeStorage(_nifti_bytes((1.0, 1.0, 1.0)))
        with pytest.raises(VoxelSpacingUnavailableError):
            await _voxel_spacing_from_source_image(None, storage, context="seg")

    @pytest.mark.asyncio
    async def test_unreadable_image_raises_cleanly(self):
        class _BadStorage:
            async def download_file(self, bucket, file_id):
                raise RuntimeError("gcs down")
        with pytest.raises(VoxelSpacingUnavailableError):
            await _voxel_spacing_from_source_image("img-1", _BadStorage(), context="seg")

    @pytest.mark.asyncio
    async def test_non_3d_image_raises_cleanly(self):
        # A 2D image yields fewer than 3 zooms -> no volumetric geometry.
        img = nib.Nifti1Image(np.zeros((4, 5), dtype=np.uint8), np.eye(4))
        storage = _FakeStorage(img.to_bytes())
        with pytest.raises(VoxelSpacingUnavailableError):
            await _voxel_spacing_from_source_image("img-1", storage, context="seg")
