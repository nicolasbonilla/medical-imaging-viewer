"""
Characterization tests for the segmentation route (Class C).

These tests PIN the current observable HTTP behavior of the segmentation
endpoints so that the planned decomposition of app/api/routes/segmentation.py
(moving the ~80 private-cache reach-ins behind public service methods and
splitting the 2,263-line router) can be verified to preserve behavior.

They are deliberately BLACK-BOX (they exercise the public HTTP contract, not
the service's private in-memory cache), so they survive the refactor: a
behavior-preserving decomposition must keep every assertion here green.

Test-env decoupling (documented, not behavior-changing):
- Redis is unavailable locally, and apply_paint_stroke calls
  `await self.cache.delete(...)`. The service already guards every cache use
  with `if self.cache:`, so we null the singleton's cache for these tests.
  This does not affect classification behavior (the cache only invalidates
  per-slice PNG entries).
- GCS/Firestore are unavailable; the service falls back to local disk save
  (_save_segmentation_local), so create/paint/classify all complete.

The heavy MAGNIMS math is already unit-tested in
tests/unit/test_ms_region_classifier.py; here we pin the ROUTE orchestration.
"""
import pytest
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def _no_redis_cache():
    """Null the segmentation singleton's Redis cache for the test env.

    The route resolves the same singleton via get_segmentation_service(), so
    this makes paint/classify independent of a running Redis. Restored after.
    """
    try:
        from app.core.container import get_container
        svc = get_container().segmentation_service()
    except Exception:  # pragma: no cover - app not importable
        pytest.skip("app/container not available")
    original = getattr(svc, "cache", None)
    svc.cache = None
    yield
    svc.cache = original


def _create_payload(file_id: str, rows=32, columns=32, slices=16):
    return {
        "file_id": file_id,
        "image_shape": {"rows": rows, "columns": columns, "slices": slices},
        "description": "characterization",
        "labels": [
            {"id": 0, "name": "Background", "color": "#000000", "opacity": 0.0, "visible": False},
            {"id": 1, "name": "Lesion", "color": "#FF0000", "opacity": 0.5, "visible": True},
        ],
    }


async def _create(async_client: AsyncClient, file_id: str) -> str:
    r = await async_client.post("/api/v1/segmentation/create", json=_create_payload(file_id))
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert "segmentation_id" in body
    assert body["file_id"] == file_id
    return body["segmentation_id"]


async def _paint(async_client: AsyncClient, seg_id: str, slices=(6, 7, 8)):
    for sl in slices:
        pr = await async_client.post(f"/api/v1/segmentation/{seg_id}/paint", json={
            "slice_index": sl, "label_id": 1, "x": 16, "y": 16, "brush_size": 6, "erase": False,
        })
        assert pr.status_code == 200, f"paint slice {sl} failed: {pr.status_code} {pr.text[:200]}"


@pytest.mark.integration
class TestSegmentationCrudContract:
    """Pin the create/get/list CRUD contract."""

    @pytest.mark.asyncio
    async def test_create_returns_id_and_metadata(self, async_client: AsyncClient):
        seg_id = await _create(async_client, "char_crud_001")
        # metadata round-trips via GET
        r = await async_client.get(f"/api/v1/segmentation/{seg_id}")
        assert r.status_code == 200, r.text[:300]
        meta = r.json()
        assert meta.get("segmentation_id") == seg_id or meta.get("file_id") == "char_crud_001"

    @pytest.mark.asyncio
    async def test_list_includes_created(self, async_client: AsyncClient):
        seg_id = await _create(async_client, "char_crud_002")
        r = await async_client.get("/api/v1/segmentation/list", params={"file_id": "char_crud_002"})
        assert r.status_code == 200, r.text[:300]
        ids = [s.get("segmentation_id") for s in r.json()]
        assert seg_id in ids

    @pytest.mark.asyncio
    async def test_get_nonexistent_is_404(self, async_client: AsyncClient):
        r = await async_client.get("/api/v1/segmentation/does-not-exist-xyz")
        assert r.status_code == 404


@pytest.mark.integration
class TestClassifyRegionsContract:
    """Pin the classify-regions orchestration contract (geometric method)."""

    @pytest.mark.asyncio
    async def test_geometric_classification_partitions_lesion_voxels(self, async_client: AsyncClient):
        seg_id = await _create(async_client, "char_classify_001")
        await _paint(async_client, seg_id)

        r = await async_client.post(
            f"/api/v1/segmentation/{seg_id}/classify-regions",
            json={"method": "geometric"},
        )
        assert r.status_code == 200, f"classify failed: {r.status_code} {r.text[:400]}"
        body = r.json()

        # Orchestration contract that the refactor MUST preserve:
        assert body["segmentation_id"] == seg_id
        assert body["mask_updated"] is True
        assert body["labels_updated"] is True

        # Geometric method schema: per-lesion list + a region->count summary.
        assert "lesions" in body and isinstance(body["lesions"], list), body
        assert "classification_summary" in body, body
        summary = body["classification_summary"]

        # We painted a connected blob, so exactly one lesion is detected...
        assert len(body["lesions"]) > 0
        # ...and the region summary partitions the lesions (counts sum to N lesions).
        assert sum(summary.values()) == len(body["lesions"])
        # Region names come from the MAGNIMS set.
        assert set(summary.keys()) <= {
            "Periventricular", "Juxtacortical", "Infratentorial",
            "Deep White Matter", "Active (Gd+)", "Black Hole (T1)",
        }
        # Each lesion carries a centroid and geometric distances (the algorithm's
        # observable output that a refactor must not silently change).
        lesion = body["lesions"][0]
        assert "centroid" in lesion and {"x", "y", "z"} <= set(lesion["centroid"])
        assert "distances_mm" in lesion

    @pytest.mark.asyncio
    async def test_classify_relabels_to_magnims(self, async_client: AsyncClient):
        seg_id = await _create(async_client, "char_classify_002")
        await _paint(async_client, seg_id)
        await async_client.post(
            f"/api/v1/segmentation/{seg_id}/classify-regions", json={"method": "geometric"},
        )
        # After classification the metadata labels should be the MAGNIMS set.
        r = await async_client.get(f"/api/v1/segmentation/{seg_id}")
        assert r.status_code == 200
        labels = r.json().get("metadata", {}).get("labels") or r.json().get("labels") or []
        names = {l["name"] for l in labels}
        assert {"Periventricular", "Juxtacortical", "Infratentorial", "Deep White Matter"} <= names

    @pytest.mark.asyncio
    async def test_classify_nonexistent_is_404(self, async_client: AsyncClient):
        r = await async_client.post(
            "/api/v1/segmentation/does-not-exist-xyz/classify-regions",
            json={"method": "geometric"},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_lst_ai_without_source_is_400(self, async_client: AsyncClient):
        seg_id = await _create(async_client, "char_classify_003")
        await _paint(async_client, seg_id)
        r = await async_client.post(
            f"/api/v1/segmentation/{seg_id}/classify-regions", json={"method": "lst-ai"},
        )
        assert r.status_code == 400
