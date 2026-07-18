"""RC-023 — anatomical orientation is determinable, and never guessed (CAPA-004 CA-4.1).

Risk control for HAZ-006 (misaligned / mirrored anatomy → wrong-side reporting).

CAPA-004 §2 found that the product contained NO orientation logic of any kind:
no affine inspection, no laterality handling, no L/R labels anywhere. A volume
stored LAS rendered mirrored relative to one stored RAS with nothing to indicate
it. RC-013 was recorded as PARTIAL — "loaded and parsed; orientation warning
pending" — describing a system that did not exist, because orientation was never
parsed.

The central assertion of these tests is that the code REFUSES to guess. For a
brain viewer, a plausible-looking wrong laterality label is more dangerous than
no label, because it converts an obvious absence into a confident error.

This is NOT the whole of RC-013 (orientation validation on upload). RC-013
remains not implemented: these primitives are deliberately not yet wired into
load_nifti_from_bytes, because image and mask load through separate calls and
canonicalising one without the other would misalign them — a worse hazard than
the one being fixed. RC-023 is the primitive; RC-013 is the wiring.

Negative control (CAPA-001 §5): make `get_orientation_codes` return a fixed
tuple instead of reading the affine, or make `canonicalize_orientation` return
the input unchanged, and these tests MUST fail.
"""
import numpy as np
import nibabel as nib
import pytest

from app.utils.nifti_utils import (
    canonicalize_orientation,
    describe_orientation,
    get_orientation_codes,
    is_orientation_determinate,
)


def _img(affine):
    """A small volume with a deliberately asymmetric pattern.

    Asymmetric on purpose: a symmetric phantom cannot reveal a left/right flip,
    which is the failure this control exists to catch.
    """
    data = np.zeros((4, 5, 6), dtype=np.float32)
    data[0, 0, 0] = 1.0
    data[3, 0, 0] = 2.0
    return nib.Nifti1Image(data, affine)


class _DegenerateImage:
    """Stand-in for an image carrying an unusable affine.

    nibabel refuses to CONSTRUCT a Nifti1Image from a singular affine, so a real
    image cannot be used to exercise the indeterminate paths. But such affines do
    reach the code in practice — from a file whose header was written by other
    software, or corrupted in transit — and `nib.load` will surface them. This
    double reproduces that state, which is exactly the state the control must
    refuse to guess about.
    """

    def __init__(self, affine):
        self.affine = affine


RAS = np.diag([1.0, 1.0, 1.0, 1.0])
LAS = np.diag([-1.0, 1.0, 1.0, 1.0])   # first axis mirrored vs RAS


class TestRC023OrientationIsDetermined:
    def test_rc023_reads_ras_orientation(self):
        assert get_orientation_codes(_img(RAS)) == ("R", "A", "S")

    def test_rc023_reads_las_orientation(self):
        """The mirrored case. Before CA-4.1 this was indistinguishable from RAS."""
        assert get_orientation_codes(_img(LAS)) == ("L", "A", "S")

    def test_rc023_distinguishes_mirrored_volumes(self):
        """The core safety property: LAS and RAS must not look alike."""
        assert get_orientation_codes(_img(RAS)) != get_orientation_codes(_img(LAS))

    def test_rc023_describes_orientation_for_display(self):
        assert describe_orientation(_img(RAS)) == "RAS"
        assert describe_orientation(_img(LAS)) == "LAS"

    def test_rc023_handles_oblique_affine(self):
        """Real acquisitions are rarely axis-aligned; a rotated affine must still
        resolve to the nearest anatomical axes rather than failing."""
        affine = np.array([
            [0.98, -0.17, 0.0, 0.0],
            [0.17, 0.98, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ])
        codes = get_orientation_codes(_img(affine))
        assert codes is not None
        assert is_orientation_determinate(_img(affine))


class TestRC023RefusesToGuess:
    """The most important behaviour here. A confident wrong answer about
    laterality is worse than an admitted unknown."""

    def test_rc023_singular_affine_is_indeterminate(self):
        singular = np.zeros((4, 4))
        singular[3, 3] = 1.0
        img = _DegenerateImage(singular)

        assert get_orientation_codes(img) is None
        assert not is_orientation_determinate(img)
        assert describe_orientation(img) == "UNKNOWN"

    def test_rc023_degenerate_axis_is_indeterminate(self):
        """One collapsed axis carries no direction for that axis."""
        affine = np.diag([1.0, 0.0, 1.0, 1.0])
        assert not is_orientation_determinate(_DegenerateImage(affine))

    def test_rc023_non_finite_affine_is_indeterminate(self):
        affine = np.diag([1.0, np.nan, 1.0, 1.0])
        assert get_orientation_codes(_DegenerateImage(affine)) is None

    def test_rc023_never_reports_a_default_orientation_on_failure(self):
        """Guard against a future 'sensible default' being introduced. Returning
        RAS for an unusable affine would silently label mirrored anatomy."""
        singular = np.zeros((4, 4))
        singular[3, 3] = 1.0
        assert get_orientation_codes(_DegenerateImage(singular)) not in [("R", "A", "S"), ("L", "A", "S")]


class TestRC023Canonicalisation:
    def test_rc023_canonicalises_las_to_ras(self):
        canonical = canonicalize_orientation(_img(LAS))
        assert get_orientation_codes(canonical) == ("R", "A", "S")

    def test_rc023_ras_is_unchanged_by_canonicalisation(self):
        original = _img(RAS)
        canonical = canonicalize_orientation(original)
        assert get_orientation_codes(canonical) == ("R", "A", "S")
        np.testing.assert_array_equal(canonical.get_fdata(), original.get_fdata())

    def test_rc023_canonicalisation_actually_moves_the_voxels(self):
        """Verify the DATA is reoriented, not merely the header relabelled —
        a header-only change would leave the rendered image mirrored while
        claiming to be canonical."""
        las = _img(LAS)
        canonical = canonicalize_orientation(las)

        assert not np.array_equal(canonical.get_fdata(), las.get_fdata()), (
            "canonicalising a mirrored volume must reorder voxel data"
        )
        # The marker at index 0 along the flipped axis must now be at the far end.
        assert canonical.get_fdata()[3, 0, 0] == 1.0
        assert canonical.get_fdata()[0, 0, 0] == 2.0

    def test_rc023_canonicalisation_is_idempotent(self):
        once = canonicalize_orientation(_img(LAS))
        twice = canonicalize_orientation(once)
        np.testing.assert_array_equal(once.get_fdata(), twice.get_fdata())

    def test_rc023_canonicalisation_fails_closed_when_indeterminate(self):
        """It must raise, not return the input unchanged. Returning the original
        would leave the caller believing it holds canonical data when it does
        not — reintroducing the exact hazard."""
        singular = np.zeros((4, 4))
        singular[3, 3] = 1.0

        with pytest.raises(ValueError, match="Cannot canonicalise orientation"):
            canonicalize_orientation(_DegenerateImage(singular))

    def test_rc023_error_explains_the_safety_reason(self):
        """The message must tell a developer why guessing is not an option,
        otherwise the natural 'fix' is to add a default."""
        singular = np.zeros((4, 4))
        singular[3, 3] = 1.0

        with pytest.raises(ValueError) as exc:
            canonicalize_orientation(_DegenerateImage(singular))

        assert "wrong-side" in str(exc.value).lower()
