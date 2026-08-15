"""Audit P-1.1: painting a mask that was ingested from an immutable buffer.

PUT /mask/binary builds the cached mask with np.frombuffer(...), which yields a
READ-ONLY array backed by the request bytes. A subsequent /paint stroke edits
that array in place and would raise "assignment destination is read-only" -> 500.

Two guards, both exercised here:
  1. the route .copy()s the frombuffer array at ingestion, and
  2. apply_paint_stroke promotes any read-only cached mask to writable once.

Regression: without the fix, apply_paint_stroke raises ValueError.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from app.services.segmentation_service import SegmentationService
from app.models.schemas import PaintStroke


def _readonly_mask(depth=4, h=16, w=16):
    """Mask exactly as PUT /mask/binary would build it: read-only frombuffer."""
    buf = bytes(depth * h * w)  # all-zero immutable bytes
    m = np.frombuffer(buf, dtype=np.uint8).reshape((depth, h, w))
    assert not m.flags.writeable, "precondition: frombuffer mask must be read-only"
    return m


@pytest.fixture
def svc(tmp_path):
    """Service with GCS/Firestore persistence stubbed out — this suite exercises
    the in-memory paint-mutation path, not durable storage."""
    s = SegmentationService(storage_path=str(tmp_path), cache_service=None)
    s._save_segmentation = lambda segmentation_id: None  # no-op persist
    return s


def _seed(svc, sid):
    svc.segmentations_cache[sid] = {
        "masks_3d": _readonly_mask(),
        "metadata": SimpleNamespace(modified_at=None),
    }


async def test_paint_on_readonly_mask_does_not_raise_and_persists(svc):
    sid = "seg-ro-1"
    _seed(svc, sid)

    stroke = PaintStroke(slice_index=0, label_id=1, x=5, y=5, brush_size=3)
    ok = await svc.apply_paint_stroke(sid, stroke)
    assert ok is True

    cached = svc.segmentations_cache[sid]["masks_3d"]
    # The cached array was promoted to writable and the edit persisted in memory.
    assert cached.flags.writeable
    assert cached[0, 5, 5] == 1
    assert int(cached.sum()) > 0


async def test_second_stroke_accumulates(svc):
    # A writable promotion must persist across strokes (not a per-call throwaway).
    sid = "seg-ro-2"
    _seed(svc, sid)

    await svc.apply_paint_stroke(sid, PaintStroke(slice_index=0, label_id=1, x=3, y=3, brush_size=1))
    await svc.apply_paint_stroke(sid, PaintStroke(slice_index=0, label_id=1, x=10, y=10, brush_size=1))

    cached = svc.segmentations_cache[sid]["masks_3d"]
    assert cached[0, 3, 3] == 1
    assert cached[0, 10, 10] == 1
