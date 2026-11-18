"""Lesion-by-lesion record of a clinician's review of an AI draft, and of the reader's own reading before the draft
(REQ-FUNC-119, REQ-FUNC-120; RC-131, RC-132; HAZ-001 cause (m): the reader goes along with the draft).

What the confirmation of an AI review left until now (RC-047) says WHO confirmed WHICH final mask. It does not say
what the reader did with each lesion the model drafted, nor which lesions the reader added that the model never
drafted: those misses cannot appear in an accept/reject log. And when the draft is on screen first, agreement with it
cannot be told apart from a reader going along with it. This module:

- keeps the AI draft exactly as the model produced it (a write-once object next to the mask, stored at the first save,
  before the clinician's version reaches the server), and the reader's own reading of the image when it was recorded
  before any draft (write-once as well, with a small write-once sidecar so it can be found without reading the mask);
- at the confirmation of the AI review, compares the draft with the confirmed mask lesion by lesion (18-connected
  lesions at least the application's minimum lesion volume, as the lesion table counts them, RC-030): kept unchanged,
  corrected (outline changed, split or merged), removed, and added by the reader; smaller components are counted
  apart, never as lesions;
- when that reviewer recorded a reading of the image before the draft existed, relates the result to it by lesion
  SITE (a connected region of reading, draft and final mask together, so a lesion is followed through outlines that
  differ between them): found by the reader and by the model, by the reader only, adopted from the draft, added later,
  and the reader's own lesions dropped once the draft was shown;
- decides, from the image id alone, whether an image is in the reader-study set read without the draft first (a fixed
  share chosen by a keyed hash; 0, the default, switches the set off), and keeps a write-once mark that a user saved
  an AI draft of an image (never deleted with the segmentation), so a reading cannot be recorded after it.

The record is evidence for oversight and for reader studies. It changes no mask, no review, no DIS assessment and no
report, and the confirmation never waits for it: what cannot be computed is stated in the record, with its reason.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

RECORD_VERSION = "lesion-review-record/2"
MAX_ENTRIES = 300                   # lesions listed one by one (largest first); the summary always counts all
ORIGINAL = "ai_draft_original"      # the AI draft as the model produced it
UNAIDED = "unaided_read"            # the reader's own reading before the draft


class Unreadable(Exception):
    """An object exists but cannot be read, or does not match the digest it was stored with."""


# ─────────────────────────────────────────────────────────────────────────── write-once storage of the masks
def blob_path(segmentation_id: str, kind: str) -> str:
    if kind not in (ORIGINAL, UNAIDED):
        raise ValueError(f"unknown kind {kind!r}")
    return f"segmentations/{segmentation_id}/{kind}.npz"


def sidecar_path(segmentation_id: str) -> str:
    return f"segmentations/{segmentation_id}/{UNAIDED}.json"


def records_prefix(segmentation_id: str) -> str:
    return f"segmentations/{segmentation_id}/review_records/"


def ai_seen_path(file_id: str, user_id: str) -> str:
    image = hashlib.sha256(str(file_id).encode("utf-8")).hexdigest()[:32]
    user = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:32]
    return f"reader_study/ai_draft_saved/{image}/{user}.json"


def encode(mask: np.ndarray, meta: Dict[str, Any]) -> bytes:
    """The mask and who stored it, when, with its digest, in ONE object: the object alone is the record (a metadata
    document rewritten from another server instance's cached copy can never separate them)."""
    buf = io.BytesIO()
    np.savez_compressed(buf, mask=np.ascontiguousarray(mask, dtype=np.uint8),
                        meta=np.frombuffer(json.dumps(meta, sort_keys=True).encode("utf-8"), dtype=np.uint8))
    return buf.getvalue()


def decode(data: bytes) -> Tuple[np.ndarray, Dict[str, Any]]:
    with np.load(io.BytesIO(data), allow_pickle=False) as z:
        return (np.ascontiguousarray(z["mask"], dtype=np.uint8),
                json.loads(bytes(np.asarray(z["meta"], dtype=np.uint8)).decode("utf-8")))


def _create_only(service: Any, path: str, data: bytes, content_type: str) -> bool:
    """Create-only write: True when written now, False when an object was already there (left untouched)."""
    from google.api_core.exceptions import PreconditionFailed

    try:
        service.gcs_bucket.blob(path).upload_from_string(data, content_type=content_type, if_generation_match=0)
    except PreconditionFailed:
        return False
    return True


def store_once(service: Any, segmentation_id: str, kind: str, mask: np.ndarray, meta: Dict[str, Any]) -> bool:
    """Store `mask` (with `meta`) as the segmentation's `kind` object, never over an existing one. True: stored now.
    False: an object was already there (left untouched). A storage failure raises. A reading also gets its sidecar."""
    if not _create_only(service, blob_path(segmentation_id, kind), encode(mask, meta), "application/octet-stream"):
        return False
    if kind == UNAIDED:
        _create_only(service, sidecar_path(segmentation_id), json.dumps(meta, sort_keys=True).encode("utf-8"),
                     "application/json")
    return True


def load(service: Any, segmentation_id: str, kind: str) -> Optional[Tuple[np.ndarray, Dict[str, Any]]]:
    """The stored `kind` mask and its meta; None when there is none. Raises Unreadable when it exists but cannot be
    read or does not match the digest it was stored with."""
    try:
        blob = service.gcs_bucket.blob(blob_path(segmentation_id, kind))
        if not blob.exists():
            return None
        mask, meta = decode(blob.download_as_bytes())
    except Exception as e:  # noqa: BLE001
        raise Unreadable(f"{kind}: {e}") from e
    if meta.get("mask_sha256") != mask_sha256(mask):
        raise Unreadable(f"{kind}: the mask does not match its digest")
    return mask, meta


def load_reading_meta(service: Any, segmentation_id: str) -> Optional[Dict[str, Any]]:
    """Who recorded a reading and when, from its small sidecar (no mask read); None when there is none."""
    try:
        blob = service.gcs_bucket.blob(sidecar_path(segmentation_id))
        if not blob.exists():
            return None
        return json.loads(blob.download_as_bytes().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise Unreadable(f"reading sidecar: {e}") from e


def mark_ai_draft_saved(service: Any, file_id: str, user: Any, at: str) -> None:
    """A write-once mark that this user saved an AI draft of this image (best effort, logged)."""
    try:
        _create_only(service, ai_seen_path(file_id, getattr(user, "id", "")),
                     json.dumps({"at": at}).encode("utf-8"), "application/json")
    except Exception as e:  # noqa: BLE001
        logger.error("AI-draft mark not stored", extra={"error": str(e)})


def ai_draft_saved(service: Any, file_id: str, user_id: str) -> bool:
    """Whether the user ever saved an AI draft of the image (a storage error counts as yes: fail closed)."""
    try:
        return bool(service.gcs_bucket.blob(ai_seen_path(file_id, user_id)).exists())
    except Exception as e:  # noqa: BLE001
        logger.error("AI-draft mark could not be read", extra={"error": str(e)})
        return True


def store_record(service: Any, segmentation_id: str, record: Dict[str, Any]) -> Optional[str]:
    """Each confirmation's record as its own write-once object, never overwritten: the path, or None (logged)."""
    path = records_prefix(segmentation_id) + str(record.get("computed_at", "")).replace(":", "-") + ".json"
    try:
        _create_only(service, path, json.dumps(record, sort_keys=True).encode("utf-8"), "application/json")
        return path
    except Exception as e:  # noqa: BLE001 — the copy in the metadata and the server log remain
        logger.error("Lesion review record not stored as an object",
                     extra={"segmentation_id": segmentation_id, "error": str(e)})
        return None


def delete_all(service: Any, segmentation_id: str) -> None:
    """Remove the segmentation's objects with it (best effort, logged): data deleted is deleted everywhere. The mark
    that a user saved an AI draft of the image stays (it names no lesion and keeps a later reading honest)."""
    try:
        bucket = service.gcs_bucket
        for path in (blob_path(segmentation_id, ORIGINAL), blob_path(segmentation_id, UNAIDED),
                     sidecar_path(segmentation_id)):
            blob = bucket.blob(path)
            if blob.exists():
                blob.delete()
        for blob in list(bucket.list_blobs(prefix=records_prefix(segmentation_id))):
            blob.delete()
    except Exception as e:  # noqa: BLE001
        logger.error("Review-record objects not deleted", extra={"segmentation_id": segmentation_id, "error": str(e)})


def mask_sha256(mask: np.ndarray) -> str:
    """The digest the rest of the application uses for a mask (SegmentationService.mask_sha256)."""
    return hashlib.sha256(np.ascontiguousarray(mask, dtype=np.uint8).tobytes()).hexdigest()


def voxel_volume_mm3(affine: Any) -> Optional[float]:
    try:
        v = abs(float(np.linalg.det(np.asarray(affine, dtype=float)[:3, :3])))
        return v if v > 0 and math.isfinite(v) else None
    except Exception:  # noqa: BLE001
        return None


# ───────────────────────────────────────────────────────────────────────────────────────────────── lesions
def _components(mask: np.ndarray, voxel_volume: Optional[float]):
    """Labels, count, voxel count per component and, per component, whether it is below the application's minimum
    lesion volume (never, when the voxel volume is unknown)."""
    from app.services.lesion_metrics import label_lesions, meets_min_volume   # RC-030: as the lesion table

    labels, count = label_lesions(np.ascontiguousarray(mask) > 0)
    labels = np.asarray(labels)
    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    small = np.zeros(count + 1, dtype=bool)
    if voxel_volume:
        small[1:] = [not meets_min_volume(int(s), voxel_volume) for s in sizes[1:]]
    return labels, int(count), sizes, small


def _overlaps(a: np.ndarray, b: np.ndarray) -> Dict[Tuple[int, int], int]:
    """Shared voxels of every (component of a, component of b) pair that touch."""
    both = (a > 0) & (b > 0)
    if not both.any():
        return {}
    base = int(b.max()) + 1
    keys, counts = np.unique(a[both].astype(np.int64) * base + b[both].astype(np.int64), return_counts=True)
    return {(int(k // base), int(k % base)): int(c) for k, c in zip(keys, counts)}


def _places(labels: np.ndarray, count: int) -> List[Tuple[int, List[int]]]:
    """Per component (index 0 unused): the slice the lesion table opens for it (centroid z rounded to 0.1, then to
    the nearest slice, 0-based) and its first voxel [slice, row, column] in raster order."""
    flat = labels.ravel()
    where = np.flatnonzero(flat)
    comp = flat[where]
    plane = labels.shape[1] * labels.shape[2]
    sums = np.bincount(comp, weights=(where // plane).astype(np.float64), minlength=count + 1)
    sizes = np.bincount(comp, minlength=count + 1)
    ids, positions = np.unique(comp, return_index=True)
    first = dict(zip(ids.tolist(), where[positions].tolist()))
    out: List[Tuple[int, List[int]]] = [(0, [0, 0, 0])]
    for c in range(1, count + 1):
        z = int(math.floor(round(float(sums[c] / sizes[c]), 1) + 0.5))
        out.append((z, [int(v) for v in np.unravel_index(first[c], labels.shape)]))
    return out


def _dice(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    sa, sb = int((a > 0).sum()), int((b > 0).sum())
    if sa + sb == 0:
        return None
    return round(2.0 * int(((a > 0) & (b > 0)).sum()) / (sa + sb), 4)


def _bounded(entries: List[Dict[str, Any]], size_keys: Tuple[str, ...]) -> Tuple[List[Dict[str, Any]], bool]:
    entries.sort(key=lambda e: -max(int(e.get(k) or 0) for k in size_keys))   # stable: raster order within a size
    return entries[:MAX_ENTRIES], len(entries) > MAX_ENTRIES


def _size_rule(voxel_volume: Optional[float]) -> Dict[str, Any]:
    from app.services.lesion_metrics import MIN_LESION_VOLUME_MM3
    return {"lesion_connectivity": 18, "voxel_volume_mm3": voxel_volume,
            "min_lesion_volume_mm3": MIN_LESION_VOLUME_MM3 if voxel_volume else None,
            "min_volume_applied": bool(voxel_volume)}


def decision_record(draft: np.ndarray, final: np.ndarray, voxel_volume: Optional[float] = None) -> Dict[str, Any]:
    """What the reviewer did with each lesion of the draft, and which lesions the reviewer added.

    Lesions are 18-connected components at least the minimum lesion volume (when the voxel volume is known); smaller
    components are counted apart and never as lesions.
    kept:      a final lesion with exactly the draft lesion's voxels;
    corrected: the draft lesion meets a final lesion but not as it was drafted (outline changed, split, merged with
               another lesion, or grown into a lesion the reader drew touching it);
    removed:   no final lesion meets it (a remnant below the minimum volume is not a lesion);
    added:     a final lesion that meets no draft lesion (a lesion the model did not draft)."""
    if draft.shape != final.shape:
        raise ValueError(f"draft {draft.shape} and final {final.shape} are not on the same grid")
    ld, nd, sd, small_d = _components(draft, voxel_volume)
    lf, nf, sf, small_f = _components(final, voxel_volume)
    d_to_f: Dict[int, Dict[int, int]] = {}
    f_to_d: Dict[int, Dict[int, int]] = {}
    for (d, f), c in _overlaps(ld, lf).items():
        if small_d[d] or small_f[f]:
            continue
        d_to_f.setdefault(d, {})[f] = c
        f_to_d.setdefault(f, {})[d] = c
    pd, pf = _places(ld, nd), _places(lf, nf)
    counts = {"kept": 0, "corrected": 0, "removed": 0, "added": 0}
    entries: List[Dict[str, Any]] = []
    for d in range(1, nd + 1):
        if small_d[d]:
            continue
        finals = d_to_f.get(d, {})
        if not finals:
            outcome = "removed"
        elif len(finals) == 1 and next(iter(finals.values())) == sd[d] == sf[next(iter(finals))]:
            outcome = "kept"
        else:
            outcome = "corrected"
        counts[outcome] += 1
        entries.append({"outcome": outcome, "draft_voxels": int(sd[d]),
                        "final_voxels": int(sum(int(sf[f]) for f in finals)), "shared_voxels": int(sum(finals.values())),
                        "slice": pd[d][0], "first_voxel": pd[d][1]})
    for f in range(1, nf + 1):
        if not small_f[f] and f not in f_to_d:
            counts["added"] += 1
            entries.append({"outcome": "added", "draft_voxels": 0, "final_voxels": int(sf[f]), "shared_voxels": 0,
                            "slice": pf[f][0], "first_voxel": pf[f][1]})
    listed, truncated = _bounded(entries, ("draft_voxels", "final_voxels"))
    return {
        "summary": {
            "draft_lesions": int(nd - small_d[1:].sum()), "final_lesions": int(nf - small_f[1:].sum()), **counts,
            "draft_small_components": int(small_d[1:].sum()), "final_small_components": int(small_f[1:].sum()),
            "draft_voxels": int((draft > 0).sum()), "final_voxels": int((final > 0).sum()),
            "voxels_added": int(((final > 0) & (draft == 0)).sum()),
            "voxels_removed": int(((draft > 0) & (final == 0)).sum()),
            "dice_draft_final": _dice(draft, final),
            **_size_rule(voxel_volume),
        },
        "lesions": listed,
        "lesions_truncated": truncated,
    }


def _without_small(mask: np.ndarray, voxel_volume: Optional[float]) -> Tuple[np.ndarray, int]:
    labels, count, _sizes, small = _components(mask, voxel_volume)
    keep = ~small
    keep[0] = False
    return keep[labels], int(count - small[1:].sum())


def unaided_record(unaided: np.ndarray, draft: np.ndarray, final: np.ndarray,
                   voxel_volume: Optional[float] = None) -> Dict[str, Any]:
    """How the result relates to the reader's own reading before the draft, by lesion SITE.

    A site is a connected region (18-connected) of the reading, the draft and the final mask taken together, each
    without its components below the minimum lesion volume: the same lesion is followed through outlines that differ,
    touch or only partly overlap between the three. A site with final voxels is one of: found by the reader and in the
    draft ("reader_and_draft"), by the reader only ("reader_only": the model missed it), in the draft only
    ("adopted_from_draft": the reader had not marked it), in neither ("added_later"). A site with the reader's voxels
    and no final voxel is "dropped_after_draft" (with whether the draft had it); a site of the draft alone was removed
    by the reviewer ("draft_removed"). Each entry gives the reader's, draft's and final lesions it holds (a merge shows
    as more than one)."""
    if not (unaided.shape == draft.shape == final.shape):
        raise ValueError("the reading, the draft and the final mask are not on the same grid")
    u, nu = _without_small(unaided, voxel_volume)
    d, nd = _without_small(draft, voxel_volume)
    f, nf = _without_small(final, voxel_volume)
    sites, ns, _s, _small = _components(u | d | f, None)
    flat = sites.ravel()

    def per_site(mask: np.ndarray) -> np.ndarray:
        return np.bincount(flat, weights=mask.ravel().astype(np.float64), minlength=ns + 1).astype(np.int64)

    def parts_per_site(mask: np.ndarray) -> np.ndarray:
        from app.services.lesion_metrics import label_lesions
        labels, count = label_lesions(mask)
        labels = np.asarray(labels)
        out = np.zeros(ns + 1, dtype=np.int64)
        if count:
            where = labels > 0
            pairs = np.unique(np.stack([sites[where], labels[where]]), axis=1)
            np.add.at(out, pairs[0], 1)
        return out

    uv, dv, fv = per_site(u), per_site(d), per_site(f)
    up, dp, fp = parts_per_site(u), parts_per_site(d), parts_per_site(f)
    places = _places(sites, ns)
    counts = {"reader_and_draft": 0, "reader_only": 0, "adopted_from_draft": 0, "added_later": 0,
              "dropped_after_draft": 0, "draft_removed": 0}
    entries: List[Dict[str, Any]] = []
    for s in range(1, ns + 1):
        if fv[s]:
            category = ("reader_and_draft" if uv[s] and dv[s] else "reader_only" if uv[s]
                        else "adopted_from_draft" if dv[s] else "added_later")
        elif uv[s]:
            category = "dropped_after_draft"
        else:
            category = "draft_removed"
        counts[category] += 1
        entries.append({"category": category, "final_voxels": int(fv[s]), "reader_voxels": int(uv[s]),
                        "draft_voxels": int(dv[s]), "reader_lesions": int(up[s]), "draft_lesions": int(dp[s]),
                        "final_lesions": int(fp[s]), "slice": places[s][0], "first_voxel": places[s][1]})
    listed, truncated = _bounded(entries, ("final_voxels", "reader_voxels", "draft_voxels"))
    return {
        "summary": {
            "reader_lesions": nu, "draft_lesions": nd, "final_lesions": nf, "sites": ns, **counts,
            "dice_reader_final": _dice(unaided, final), "dice_draft_final": _dice(draft, final),
            "dice_reader_draft": _dice(unaided, draft),
            **_size_rule(voxel_volume),
        },
        "sites": listed,
        "sites_truncated": truncated,
    }


# ──────────────────────────────────────────────────────────────────────────────────── the reader-study set
def in_unaided_first_set(file_id: str, fraction: float, key: str) -> bool:
    """Whether an image is in the set read without the draft first: a fixed share of images chosen by a keyed hash of
    the image id alone (the reader cannot choose, and the answer never changes for an image). 0, or no key, switches
    it off."""
    if not fraction or fraction <= 0 or not key:
        return False
    if fraction >= 1:
        return True
    digest = hashlib.sha256(f"{key}\n{file_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2.0 ** 64 < fraction


def _as_datetime(value: Any) -> Optional[datetime]:
    """A naive UTC datetime from a datetime or an ISO string (with "Z", an offset, or none = UTC)."""
    try:
        if isinstance(value, str) and value:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    except (ValueError, TypeError):
        return None
    return None


def own_readings(service: Any, same_image: List[Any], user: Any) -> List[Tuple[Any, Dict[str, Any]]]:
    """The user's recorded readings of an image: (segmentation, meta), from the small write-once sidecars alone
    (segmentations without AI provenance, drawn by the user)."""
    out = []
    for seg in same_image:
        metadata = getattr(seg, "metadata", None)
        if getattr(metadata, "ai_provenance", None) is not None:
            continue
        if getattr(metadata, "created_by", None) != getattr(user, "username", None):
            continue
        meta = load_reading_meta(service, seg.segmentation_id)
        if meta is not None and meta.get("by_id") == getattr(user, "id", None):
            out.append((seg, meta))
    return out


def reading_before(readings: List[Tuple[Any, Dict[str, Any]]], draft_created_at: Any) -> Optional[Tuple[Any, Dict]]:
    """The most recent of the reviewer's readings recorded BEFORE the draft was created on the server (server times
    on both sides); None when there is none."""
    created = _as_datetime(draft_created_at)
    if created is None:
        return None
    best, best_at = None, None
    for item in readings:
        at = _as_datetime(item[-1].get("at"))
        if at is None or at >= created:
            continue
        if best_at is None or at > best_at:
            best, best_at = item, at
    return best


def build(service: Any, segmentation_id: str, metadata: Any, final: np.ndarray, reviewer: Any,
          list_same_image, voxel_volume: Optional[float] = None) -> Dict[str, Any]:
    """The record stored with a confirmation of the AI review. Never raises: what cannot be computed is reported with
    its reason, and a failure in the comparison with the reading never discards the comparison with the draft."""
    record: Dict[str, Any] = {"version": RECORD_VERSION, "computed_at": datetime.utcnow().isoformat() + "Z",
                              "reviewed_mask_sha256": mask_sha256(final)}
    try:
        loaded = load(service, segmentation_id, ORIGINAL)
    except Unreadable as e:
        logger.error("AI draft original unreadable", extra={"segmentation_id": segmentation_id, "error": str(e)})
        return {**record, "available": False, "reason": "original_unreadable"}
    if loaded is None:
        return {**record, "available": False, "reason": "original_not_stored"}
    draft, meta = loaded
    if draft.shape != final.shape:
        return {**record, "available": False, "reason": "original_on_another_grid"}
    try:
        record.update({"available": True, "draft_mask_sha256": meta.get("mask_sha256"),
                       "draft_stored_at": meta.get("at"), **decision_record(draft, final, voxel_volume)})
    except Exception as e:  # noqa: BLE001 — the record never blocks the confirmation
        logger.error("Lesion review record not computed", extra={"segmentation_id": segmentation_id, "error": str(e)})
        return {**record, "available": False, "reason": "not_computed"}
    try:
        reading = reading_before(own_readings(service, list_same_image(), reviewer),
                                 getattr(metadata, "created_at", None))
        if reading is None:
            record["unaided"] = {"available": False, "reason": "no_reading_before_draft"}
        else:
            seg, umeta = reading
            loaded_reading = load(service, seg.segmentation_id, UNAIDED)
            if loaded_reading is None or loaded_reading[0].shape != final.shape:
                record["unaided"] = {"available": False, "reason": "reading_unreadable",
                                     "segmentation_id": seg.segmentation_id}
            else:
                record["unaided"] = {"available": True, "segmentation_id": seg.segmentation_id,
                                     "recorded_at": umeta.get("at"), "reading_mask_sha256": umeta.get("mask_sha256"),
                                     **unaided_record(loaded_reading[0], draft, final, voxel_volume)}
    except Unreadable as e:
        logger.error("Reading unreadable", extra={"segmentation_id": segmentation_id, "error": str(e)})
        record["unaided"] = {"available": False, "reason": "reading_unreadable"}
    except Exception as e:  # noqa: BLE001
        logger.error("Reading not compared", extra={"segmentation_id": segmentation_id, "error": str(e)})
        record["unaided"] = {"available": False, "reason": "reading_not_compared"}
    return record


def banner_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    """The few counts the AI-draft banner shows after a confirmation (the full record stays in the metadata)."""
    if not record.get("available"):
        return {"available": False, "reason": record.get("reason")}
    s = record["summary"]
    out: Dict[str, Any] = {"available": True, **{k: int(s[k]) for k in
                                                 ("draft_lesions", "final_lesions", "kept", "corrected", "removed",
                                                  "added")}}
    unaided = record.get("unaided") or {}
    if unaided.get("available"):
        us = unaided["summary"]
        out["unaided"] = {k: int(us[k]) for k in ("reader_lesions", "reader_and_draft", "reader_only",
                                                  "adopted_from_draft", "added_later", "dropped_after_draft")}
    return out


def slim(record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The record without its per-lesion lists (for listings)."""
    if not record:
        return record
    out = {k: v for k, v in record.items() if k not in ("lesions",)}
    if isinstance(out.get("unaided"), dict):
        out["unaided"] = {k: v for k, v in out["unaided"].items() if k != "sites"}
    return out
