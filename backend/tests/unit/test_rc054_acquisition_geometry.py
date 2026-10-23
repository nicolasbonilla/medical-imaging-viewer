"""RC-054 — the acquisition slice thickness is read from the file, never guessed.

CP-SLICE-THICKNESS-001 — DRAFT, PENDING owner approval. REQ-FUNC-099, REQ-SAFE-034;
HAZ-015 (wrong statement of what the automatic lesion list can be trusted for) and HAZ-001.

Research input: Paper A v0.3 (PR #54). A FLAIR acquired at 2-5 mm and resampled to 1 mm
(MSLesSeg) shows 1-mm spacing in its header, so a fine grid is not evidence of a thin
acquisition; detection of small lesions falls with the ORIGINAL slice thickness.

What these tests pin down:
  * DICOM: ``native`` only for an ORIGINAL image that records its slice thickness and whose
    spacing between slices is recorded or whose acquisition is 3D; the effective value counts
    the gap (max of thickness and spacing). A spacing without a thickness is not determinable.
    Derived images and 2D images without the spacing give a lower bound (thick) or nothing.
  * NIfTI: never ``native``; a grid coarser than 1.5 mm is a lower bound; a fine grid is
    ``not_determinable`` (template grid named when recognisable).
  * Missing, invalid or contradictory values are ``not_determinable`` — never a default
    (the legacy ``ImageMetadata.slice_thickness`` is 1.0 mm for a DICOM without the tag).
  * Every function is total: garbage in -> ``not_determinable``, never an exception.
  * The image loaders expose it on ``ImageMetadata.acquisition_geometry``.
  * The Class C utilities are wrapped, not modified.

Negative controls: scripts/safety/slice_thickness_negative_controls.py.
"""
from __future__ import annotations

import gzip
import io
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from app.services import acquisition_geometry as ag
from app.services.acquisition_geometry import derive_from_dicom_dataset, derive_from_nifti_image
from app.services.imaging_service import ImagingService

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
ASSET = REPO_ROOT / "frontend" / "src" / "config" / "sliceThicknessReliability.v2.json"


# ─── fixtures ─────────────────────────────────────────────────────────────────────────

def _ds(**tags) -> Dataset:
    ds = Dataset()
    for k, v in tags.items():
        setattr(ds, k, v)
    return ds


ORIGINAL = ["ORIGINAL", "PRIMARY", "M", "ND"]
DERIVED = ["DERIVED", "SECONDARY", "MPR"]


def _nifti(zooms, shape=(24, 24, 12), sform_code=1, unit="mm", affine=None) -> nib.Nifti1Image:
    aff = np.diag(list(zooms) + [1.0]) if affine is None else np.asarray(affine, float)
    img = nib.Nifti1Image(np.zeros(shape, np.float32), aff)
    img.set_sform(aff, sform_code)
    img.set_qform(aff, 1)
    img.header.set_xyzt_units(unit)
    return img


def _nifti_bytes(img: nib.Nifti1Image, gz: bool = False) -> bytes:
    # A small all-zero volume gzips below the 348-byte NIfTI minimum the loader enforces.
    return gzip.compress(img.to_bytes()) if gz else img.to_bytes()


def _dicom_bytes(**tags) -> bytes:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset("x.dcm", {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "MR"
    ds.Rows, ds.Columns = 8, 8
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit = 16, 16, 15
    ds.PixelRepresentation = 0
    ds.PixelData = (np.arange(64, dtype=np.uint16).reshape(8, 8)).tobytes()
    for k, v in tags.items():
        setattr(ds, k, v)
    buf = io.BytesIO()
    pydicom.dcmwrite(buf, ds, write_like_original=False)
    return buf.getvalue()


# ─── DICOM ────────────────────────────────────────────────────────────────────────────

def test_rc054_original_2d_dicom_with_spacing_is_native_and_counts_the_gap():
    g = derive_from_dicom_dataset(_ds(ImageType=ORIGINAL, MRAcquisitionType="2D", SliceThickness="5", SpacingBetweenSlices="6.5"))
    assert g.state == "native"
    assert g.source == "dicom_header"
    assert g.effective_mm == pytest.approx(6.5)  # 5 mm slices with a 1.5 mm gap: 6.5 mm apart
    assert g.slice_thickness_mm == pytest.approx(5.0)
    assert g.spacing_between_slices_mm == pytest.approx(6.5)


def test_rc054_original_3d_dicom_is_native_thin_even_without_spacing():
    g = derive_from_dicom_dataset(_ds(ImageType=ORIGINAL, MRAcquisitionType="3D", SliceThickness="1.0"))
    assert (g.state, g.effective_mm) == ("native", pytest.approx(1.0))
    # overlapping 3D partitions: spacing smaller than thickness -> the thickness counts
    g = derive_from_dicom_dataset(_ds(ImageType=ORIGINAL, MRAcquisitionType="3D", SliceThickness="1.2", SpacingBetweenSlices="0.6"))
    assert (g.state, g.effective_mm) == ("native", pytest.approx(1.2))


def test_rc054_2d_dicom_without_spacing_is_only_a_lower_bound():
    g = derive_from_dicom_dataset(_ds(ImageType=ORIGINAL, MRAcquisitionType="2D", SliceThickness="5"))
    assert (g.state, g.effective_mm, g.reason) == ("at_least", pytest.approx(5.0), "thin_without_3d_or_spacing")
    g = derive_from_dicom_dataset(_ds(ImageType=ORIGINAL, SliceThickness="4"))  # acquisition type absent
    assert g.state == "at_least"


def test_rc054_thin_dicom_without_3d_or_spacing_is_not_determinable():
    g = derive_from_dicom_dataset(_ds(ImageType=ORIGINAL, MRAcquisitionType="2D", SliceThickness="1.0"))
    assert (g.state, g.effective_mm, g.reason) == ("not_determinable", None, "thin_without_3d_or_spacing")


def test_rc054_derived_or_untyped_dicom_is_never_native():
    thick = derive_from_dicom_dataset(_ds(ImageType=DERIVED, MRAcquisitionType="3D", SliceThickness="3", SpacingBetweenSlices="3"))
    assert (thick.state, thick.reason) == ("at_least", "derived_image")
    thin = derive_from_dicom_dataset(_ds(ImageType=DERIVED, MRAcquisitionType="3D", SliceThickness="1", SpacingBetweenSlices="1"))
    assert (thin.state, thin.reason) == ("not_determinable", "derived_image")
    untyped = derive_from_dicom_dataset(_ds(MRAcquisitionType="3D", SliceThickness="1", SpacingBetweenSlices="1"))
    assert untyped.state == "not_determinable"
    # backslash-joined string form of ImageType
    joined = derive_from_dicom_dataset(_ds(ImageType="DERIVED\\SECONDARY", MRAcquisitionType="3D", SliceThickness="1"))
    assert joined.state == "not_determinable"


def test_rc054_missing_thickness_is_not_determinable_never_a_default():
    g = derive_from_dicom_dataset(_ds(ImageType=ORIGINAL, MRAcquisitionType="2D"))
    assert (g.state, g.effective_mm, g.reason) == ("not_determinable", None, "missing")


@pytest.mark.parametrize("image_type, acq", [(ORIGINAL, "2D"), (ORIGINAL, "3D"), (ORIGINAL, None), (DERIVED, "2D")])
def test_rc054_spacing_without_thickness_is_not_determinable(image_type, acq):
    """Independent review of PR #59: SpacingBetweenSlices is the distance between slice
    centres, not the thickness of a slice (slices may overlap). Without SliceThickness the
    acquisition thickness is missing -> not determinable (REQ-SAFE-034 (c)), never the spacing."""
    tags = dict(ImageType=image_type, SpacingBetweenSlices="2.5")
    if acq is not None:
        tags["MRAcquisitionType"] = acq
    g = derive_from_dicom_dataset(_ds(**tags))
    assert (g.state, g.effective_mm, g.reason) == ("not_determinable", None, "missing")
    assert g.spacing_between_slices_mm == pytest.approx(2.5)  # read and reported, not used as a thickness
    thick = derive_from_dicom_dataset(_ds(**{**tags, "SpacingBetweenSlices": "6"}))
    assert (thick.state, thick.effective_mm) == ("not_determinable", None)


def test_rc054_loader_never_reports_the_spacing_as_the_thickness():
    """The reviewer's case through the real DICOM loader: an original 2D image with
    SpacingBetweenSlices 2.5 mm and no SliceThickness is not '2.5 mm, from the header'."""
    svc = ImagingService(cache_service=None)
    _, meta = svc.load_dicom(_dicom_bytes(ImageType=ORIGINAL, MRAcquisitionType="2D", SpacingBetweenSlices="2.5"))
    g = meta.acquisition_geometry
    assert (g.state, g.effective_mm, g.reason) == ("not_determinable", None, "missing")


@pytest.mark.parametrize("bad", ["0", "-5", "25", "nan", "inf"])
def test_rc054_invalid_values_are_rejected_not_clipped(bad):
    g = derive_from_dicom_dataset(_ds(ImageType=ORIGINAL, MRAcquisitionType="3D", SliceThickness=bad))
    assert (g.state, g.effective_mm, g.reason) == ("not_determinable", None, "invalid")


def test_rc054_an_invalid_spacing_does_not_make_a_value_native():
    # thickness valid, spacing negative (old vendor sign convention): no native claim from a 2D image
    g = derive_from_dicom_dataset(_ds(ImageType=ORIGINAL, MRAcquisitionType="2D", SliceThickness="5", SpacingBetweenSlices="-6"))
    assert (g.state, g.effective_mm) == ("at_least", pytest.approx(5.0))


def test_rc054_enhanced_multiframe_reads_the_shared_functional_group():
    measures = Dataset()
    measures.SliceThickness = "4"
    measures.SpacingBetweenSlices = "4.8"
    shared = Dataset()
    shared.PixelMeasuresSequence = [measures]
    ds = _ds(ImageType=ORIGINAL, MRAcquisitionType="2D")
    ds.SharedFunctionalGroupsSequence = [shared]
    g = derive_from_dicom_dataset(ds)
    assert (g.state, g.effective_mm) == ("native", pytest.approx(4.8))


# ─── NIfTI ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("zooms", [(0.9, 0.9, 5.0), (1, 1, 1), (0.47, 0.47, 0.8), (2, 2, 2), (5.0, 0.9, 0.9)])
def test_rc054_nifti_is_never_native(zooms):
    assert derive_from_nifti_image(_nifti(zooms)).state != "native"


def test_rc054_nifti_thick_grid_is_a_lower_bound_on_any_axis():
    axial = derive_from_nifti_image(_nifti((0.9, 0.9, 5.0)))
    assert (axial.state, axial.effective_mm, axial.source) == ("at_least", pytest.approx(5.0), "nifti_grid")
    assert axial.grid_spacing_mm == [pytest.approx(0.9), pytest.approx(0.9), pytest.approx(5.0)]
    sagittal = derive_from_nifti_image(_nifti((6.0, 0.9, 0.9)))
    assert (sagittal.state, sagittal.effective_mm) == ("at_least", pytest.approx(6.0))
    # rotated affine: the spacing is the column norm, not the diagonal
    theta = np.deg2rad(30)
    rot = np.array([[np.cos(theta), -np.sin(theta), 0], [np.sin(theta), np.cos(theta), 0], [0, 0, 1]])
    aff = np.eye(4)
    aff[:3, :3] = rot @ np.diag([0.9, 0.9, 7.0])
    rotated = derive_from_nifti_image(_nifti((0.9, 0.9, 7.0), affine=aff))
    assert (rotated.state, rotated.effective_mm) == ("at_least", pytest.approx(7.0))


def test_rc054_nifti_fine_grid_is_not_determinable_mslesseg_case():
    # MSLesSeg: acquired at 2-5 mm, delivered on the MNI 1-mm grid (182 x 218 x 182)
    mni = derive_from_nifti_image(_nifti((1, 1, 1), shape=(182, 218, 182)))
    assert (mni.state, mni.effective_mm, mni.reason) == ("not_determinable", None, "template_grid")
    mni_code = derive_from_nifti_image(_nifti((1, 1, 1), sform_code=4))
    assert mni_code.reason == "template_grid"
    native_looking = derive_from_nifti_image(_nifti((0.47, 0.47, 0.8)))
    assert (native_looking.state, native_looking.reason) == ("not_determinable", "fine_grid_no_acquisition_metadata")


def test_rc054_nifti_header_contradicting_itself_is_not_determinable():
    img = _nifti((1, 1, 1))
    img.header.set_zooms((1.0, 1.0, 5.0))  # pixdim says 5 mm, the sform says 1 mm
    g = derive_from_nifti_image(img)
    assert (g.state, g.reason) == ("not_determinable", "inconsistent_header")


def test_rc054_nifti_units_are_honoured():
    metres = derive_from_nifti_image(_nifti((0.0009, 0.0009, 0.005), unit="meter"))
    assert (metres.state, metres.effective_mm) == ("at_least", pytest.approx(5.0))
    microns = derive_from_nifti_image(_nifti((900, 900, 5000), unit="micron"))
    assert (microns.state, microns.effective_mm) == ("at_least", pytest.approx(5.0))


def test_rc054_nifti_single_slice_is_not_a_volume():
    g = derive_from_nifti_image(_nifti((1, 1, 5), shape=(24, 24, 1)))
    assert (g.state, g.reason) == ("not_determinable", "not_a_volume")


@pytest.mark.parametrize("garbage", [None, 0, "x", object(), Dataset(), {"affine": None}])
def test_rc054_never_raises_on_garbage(garbage):
    for fn in (derive_from_dicom_dataset, derive_from_nifti_image):
        g = fn(garbage)
        assert g.state == "not_determinable"
        assert g.effective_mm is None


# ─── exposure on the image metadata ─────────────────────────────────────────────────────

def test_rc054_image_loaders_expose_the_geometry():
    svc = ImagingService(cache_service=None)
    _, meta = svc.load_nifti(_nifti_bytes(_nifti((0.9, 0.9, 6.0))))
    assert meta.acquisition_geometry is not None
    assert (meta.acquisition_geometry.state, meta.acquisition_geometry.effective_mm) == ("at_least", pytest.approx(6.0))

    _, meta = svc.load_dicom(_dicom_bytes(ImageType=ORIGINAL, MRAcquisitionType="2D", SliceThickness="5", SpacingBetweenSlices="6"))
    assert (meta.acquisition_geometry.state, meta.acquisition_geometry.effective_mm) == ("native", pytest.approx(6.0))


def test_rc054_the_legacy_default_never_leaks_into_the_geometry():
    svc = ImagingService(cache_service=None)
    _, meta = svc.load_dicom(_dicom_bytes(ImageType=ORIGINAL, MRAcquisitionType="2D"))
    assert meta.slice_thickness == pytest.approx(1.0)  # legacy display default, unchanged
    assert meta.acquisition_geometry.state == "not_determinable"
    assert meta.acquisition_geometry.effective_mm is None
    payload = json.loads(meta.model_dump_json())
    assert payload["acquisition_geometry"]["state"] == "not_determinable"


async def test_rc054_process_image_response_carries_the_geometry():
    svc = ImagingService(cache_service=None)
    resp = await svc.process_image(_nifti_bytes(_nifti((1, 1, 1), shape=(182, 218, 182)), gz=True), "x.nii.gz", slice_range=(0, 1))
    g = resp.model_dump()["metadata"]["acquisition_geometry"]
    assert (g["state"], g["reason"]) == ("not_determinable", "template_grid")


# ─── boundaries ──────────────────────────────────────────────────────────────────────

def test_rc054_class_c_utilities_are_wrapped_not_modified():
    src = (BACKEND_ROOT / "app" / "services" / "acquisition_geometry.py").read_text(encoding="utf-8")
    assert "from app.utils.dicom_utils import extract_dicom_metadata" in src
    assert "from app.utils.nifti_utils import extract_nifti_metadata" in src
    for rel in ("app/utils/nifti_utils.py", "app/utils/dicom_utils.py"):
        text = (BACKEND_ROOT / rel).read_text(encoding="utf-8")
        assert "acquisition_geometry" not in text and "AcquisitionGeometry" not in text


def test_rc054_every_reason_has_a_message_on_the_card():
    """The card shows a plain-language reason for every 'not determinable' the backend emits."""
    asset = json.loads(ASSET.read_text(encoding="utf-8"))
    for lang in ("en", "es", "de"):
        messages = asset["messages"][lang]["reasons"]
        missing = [r for r in ag.REASONS if r not in messages]
        assert not missing, f"{lang}: no card message for {missing}"
    assert asset["thin_limit_mm"] == ag.THIN_LIMIT_MM
    assert asset["plausible_max_mm"] == ag.PLAUSIBLE_MAX_MM
