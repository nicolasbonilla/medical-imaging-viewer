"""Lesion-by-lesion record of a clinician's review of an AI draft, and of the reader's own reading before the draft
(REQ-FUNC-119, REQ-FUNC-120; RC-131, RC-132; HAZ-001 cause (h): the reader goes along with the draft).

What the confirmation of an AI review left until now (RC-047) says WHO confirmed WHICH final mask. It does not say
what the reader did with each lesion the model drafted, nor which lesions the reader added that the model never
drafted: those misses cannot appear in an accept/reject log. And when the draft is on screen first, agreement with it
cannot be told apart from a reader going along with it. This module:

- keeps the AI draft exactly as the model produced it (a write-once object next to the mask, stored at the first
  save, before any correction reaches the server), and the reader's own reading of the image when it was recorded
  before the draft (write-once as well);
- at the confirmation of the AI review, compares the draft with the confirmed mask lesion by lesion (18-connected
  lesions, the connectivity of the lesion table, RC-030): kept unchanged, corrected (outline changed, split or
  merged), removed, and added by the reader;
- when that reviewer recorded a reading of the image before the draft existed, relates every final lesion to it
  (found by the reader and by the model, by the reader only, adopted from the draft, added later) and lists the
  reader's own lesions that were dropped once the draft was shown;
- decides, from the image id alone, whether an image is in the reader-study set read without the draft first
  (a fixed fraction; 0, the default, switches the set off).

The record is evidence for oversight and for reader studies. It changes no mask, no review, no DIS assessment and no
report, and the confirmation never waits for it: a draft saved before this version has no original, and the record
says so. Counts are in voxels. A lesion the reader drew touching a draft lesion is part of it (a correction).
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

RECORD_VERSION = "lesion-review-record/1"
MAX_ENTRIES = 300                   # lesions listed one by one (largest first); the summary always counts all
ORIGINAL = "ai_draft_original"      # the AI draft as the model produced it
UNAIDED = "unaided_read"            # the reader's own reading before the draft


# ─────────────────────────────────────────────────────────────────────────── write-once storage of the two masks
def blob_path(segmentation_id: str, kind: str) -> str:
    if kind not in (ORIGINAL, UNAIDED):
        raise ValueError(f"unknown kind {kind!r}")
    return f"segmentations/{segmentation_id}/{kind}.npz"


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


def store_once(service: Any, segmentation_id: str, kind: str, mask: np.ndarray, meta: Dict[str, Any]) -> bool:
    """Store `mask` (with `meta`) as the segmentation's `kind` object, never over an existing one (create-only
    write). True: stored now. False: an object was already there (left untouched). A storage failure raises."""
    from google.api_core.exceptions import PreconditionFailed

    blob = service.gcs_bucket.blob(blob_path(segmentation_id, kind))
    try:
        blob.upload_from_string(encode(mask, meta), content_type="application/octet-stream", if_generation_match=0)
    except PreconditionFailed:
        return False
    return True


def load(service: Any, segmentation_id: str, kind: str) -> Optional[Tuple[np.ndarray, Dict[str, Any]]]:
    """The stored `kind` mask and its meta, or None when there is none or it cannot be read (logged). An object
    whose mask does not match the digest it was stored with is not returned."""
    try:
        blob = service.gcs_bucket.blob(blob_path(segmentation_id, kind))
        if not blob.exists():
            return None
        mask, meta = decode(blob.download_as_bytes())
    except Exception as e:  # noqa: BLE001 — a record that cannot be read is reported as not available
        logger.error("Review-record mask could not be read",
                     extra={"segmentation_id": segmentation_id, "kind": kind, "error": str(e)})
        return None
    if meta.get("mask_sha256") != mask_sha256(mask):
        logger.error("Review-record mask does not match its digest", extra={"segmentation_id": segmentation_id,
                                                                            "kind": kind})
        return None
    return mask, meta


def records_prefix(segmentation_id: str) -> str:
    return f"segmentations/{segmentation_id}/review_records/"


def store_record(service: Any, segmentation_id: str, record: Dict[str, Any]) -> Optional[str]:
    """Each confirmation's record as its own write-once object, never overwritten: the path, or None (logged)."""
    path = records_prefix(segmentation_id) + str(record.get("computed_at", "")).replace(":", "-") + ".json"
    try:
        service.gcs_bucket.blob(path).upload_from_string(json.dumps(record, sort_keys=True),
                                                         content_type="application/json", if_generation_match=0)
        return path
    except Exception as e:  # noqa: BLE001 — the copy in the metadata and the server log remain
        logger.error("Lesion review record not stored as an object",
                     extra={"segmentation_id": segmentation_id, "error": str(e)})
        return None


def delete_all(service: Any, segmentation_id: str) -> None:
    """Remove the objects with their segmentation (best effort, logged): data deleted is deleted everywhere."""
    try:
        bucket = service.gcs_bucket
        for kind in (ORIGINAL, UNAIDED):
            blob = bucket.blob(blob_path(segmentation_id, kind))
            if blob.exists():
                blob.delete()
        for blob in list(bucket.list_blobs(prefix=records_prefix(segmentation_id))):
            blob.delete()
    except Exception as e:  # noqa: BLE001
        logger.error("Review-record objects not deleted", extra={"segmentation_id": segmentation_id, "error": str(e)})


def mask_sha256(mask: np.ndarray) -> str:
    """The digest the rest of the application uses for a mask (SegmentationService.mask_sha256)."""
    return hashlib.sha256(np.ascontiguousarray(mask, dtype=np.uint8).tobytes()).hexdigest()


# ───────────────────────────────────────────────────────────────────────────────────────────────── lesions
def _components(mask: np.ndarray) -> Tuple[np.ndarray, int, np.ndarray]:
    from app.services.lesion_metrics import label_lesions   # RC-030: 18-connectivity, as the lesion table

    labels, count = label_lesions(np.ascontiguousarray(mask) > 0)
    labels = np.asarray(labels)
    return labels, int(count), np.bincount(labels.ravel(), minlength=count + 1)


def _overlaps(a: np.ndarray, b: np.ndarray) -> Dict[Tuple[int, int], int]:
    """Shared voxels of every (component of a, component of b) pair that touch."""
    both = (a > 0) & (b > 0)
    if not both.any():
        return {}
    base = int(b.max()) + 1
    keys, counts = np.unique(a[both].astype(np.int64) * base + b[both].astype(np.int64), return_counts=True)
    return {(int(k // base), int(k % base)): int(c) for k, c in zip(keys, counts)}


def _by_first(pairs: Dict[Tuple[int, int], int]) -> Dict[int, Dict[int, int]]:
    out: Dict[int, Dict[int, int]] = {}
    for (x, y), c in pairs.items():
        out.setdefault(x, {})[y] = c
    return out


def _by_second(pairs: Dict[Tuple[int, int], int]) -> Dict[int, Dict[int, int]]:
    return _by_first({(y, x): c for (x, y), c in pairs.items()})


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


def decision_record(draft: np.ndarray, final: np.ndarray) -> Dict[str, Any]:
    """What the reviewer did with each lesion of the draft, and which lesions the reviewer added.

    kept:      a final lesion with exactly the draft lesion's voxels;
    corrected: the draft lesion touches the final mask but not as it was drafted (outline changed, split, merged
               with another lesion, or grown into a lesion the reader drew touching it);
    removed:   no voxel of the draft lesion is left in the final mask;
    added:     a final lesion that touches no draft lesion (a lesion the model did not draft)."""
    if draft.shape != final.shape:
        raise ValueError(f"draft {draft.shape} and final {final.shape} are not on the same grid")
    ld, nd, sd = _components(draft)
    lf, nf, sf = _components(final)
    pairs = _overlaps(ld, lf)
    d_to_f, f_to_d = _by_first(pairs), _by_second(pairs)
    pd, pf = _places(ld, nd), _places(lf, nf)
    counts = {"kept": 0, "corrected": 0, "removed": 0, "added": 0}
    entries: List[Dict[str, Any]] = []
    for d in range(1, nd + 1):
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
        if f not in f_to_d:
            counts["added"] += 1
            entries.append({"outcome": "added", "draft_voxels": 0, "final_voxels": int(sf[f]), "shared_voxels": 0,
                            "slice": pf[f][0], "first_voxel": pf[f][1]})
    listed, truncated = _bounded(entries, ("draft_voxels", "final_voxels"))
    return {
        "summary": {
            "draft_lesions": nd, "final_lesions": nf, **counts,
            "draft_voxels": int((draft > 0).sum()), "final_voxels": int((final > 0).sum()),
            "voxels_added": int(((final > 0) & (draft == 0)).sum()),
            "voxels_removed": int(((draft > 0) & (final == 0)).sum()),
            "dice_draft_final": _dice(draft, final),
        },
        "lesions": listed,
        "lesions_truncated": truncated,
    }


def unaided_record(unaided: np.ndarray, draft: np.ndarray, final: np.ndarray) -> Dict[str, Any]:
    """How the final lesions relate to the reader's own reading before the draft, and what the draft changed.

    For each final lesion: found by the reader (before the draft) and in the draft ("reader_and_draft"), by the
    reader only ("reader_only": the model missed it), in the draft only ("adopted_from_draft": the reader had not
    marked it), or in neither ("added_later"). For each lesion of the reader's own reading that is not in the final
    mask: "dropped_after_draft" (with whether the draft had it)."""
    if not (unaided.shape == draft.shape == final.shape):
        raise ValueError("the reading, the draft and the final mask are not on the same grid")
    lu, nu, su = _components(unaided)
    ld, nd, _ = _components(draft)
    lf, nf, sf = _components(final)
    f_to_u = _by_first(_overlaps(lf, lu))
    f_to_d = _by_first(_overlaps(lf, ld))
    u_to_f = _by_first(_overlaps(lu, lf))
    u_to_d = _by_first(_overlaps(lu, ld))
    pu, pf = _places(lu, nu), _places(lf, nf)
    counts = {"reader_and_draft": 0, "reader_only": 0, "adopted_from_draft": 0, "added_later": 0,
              "dropped_after_draft": 0}
    entries: List[Dict[str, Any]] = []
    for f in range(1, nf + 1):
        in_u, in_d = f in f_to_u, f in f_to_d
        category = ("reader_and_draft" if in_u and in_d else "reader_only" if in_u
                    else "adopted_from_draft" if in_d else "added_later")
        counts[category] += 1
        entries.append({"category": category, "final_voxels": int(sf[f]),
                        "reader_voxels": int(sum(int(su[u]) for u in f_to_u.get(f, {}))),
                        "slice": pf[f][0], "first_voxel": pf[f][1]})
    for u in range(1, nu + 1):
        if u not in u_to_f:
            counts["dropped_after_draft"] += 1
            entries.append({"category": "dropped_after_draft", "final_voxels": 0, "reader_voxels": int(su[u]),
                            "in_draft": u in u_to_d, "slice": pu[u][0], "first_voxel": pu[u][1]})
    listed, truncated = _bounded(entries, ("final_voxels", "reader_voxels"))
    return {
        "summary": {
            "reader_lesions": nu, "draft_lesions": nd, "final_lesions": nf, **counts,
            "dice_reader_final": _dice(unaided, final), "dice_draft_final": _dice(draft, final),
            "dice_reader_draft": _dice(unaided, draft),
        },
        "lesions": listed,
        "lesions_truncated": truncated,
    }


# ──────────────────────────────────────────────────────────────────────────────────── the reader-study set
def in_unaided_first_set(file_id: str, fraction: float, salt: str) -> bool:
    """Whether an image is in the set read without the draft first: a fixed share of images chosen by a keyed hash of
    the image id alone (the reader cannot choose, and the answer never changes for an image). 0 switches it off."""
    if not fraction or fraction <= 0:
        return False
    if fraction >= 1:
        return True
    digest = hashlib.sha256(f"{salt}\n{file_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2.0 ** 64 < fraction


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.rstrip("Z").replace("+00:00", ""))
        except ValueError:
            return None
    return None


def own_readings(service: Any, same_image: List[Any], user: Any) -> List[Tuple[Any, np.ndarray, Dict[str, Any]]]:
    """The user's own readings of an image recorded before any draft: (segmentation, mask, meta), from the
    write-once objects alone (segmentations without AI provenance, drawn by the user)."""
    out = []
    for seg in same_image:
        metadata = getattr(seg, "metadata", None)
        if getattr(metadata, "ai_provenance", None) is not None:
            continue
        if getattr(metadata, "created_by", None) != getattr(user, "username", None):
            continue
        loaded = load(service, seg.segmentation_id, UNAIDED)
        if loaded is not None and loaded[1].get("by_id") == getattr(user, "id", None):
            out.append((seg, loaded[0], loaded[1]))
    return out


def reading_before(readings: List[Tuple[Any, np.ndarray, Dict[str, Any]]],
                   draft_created_at: Any) -> Optional[Tuple[Any, np.ndarray, Dict[str, Any]]]:
    """The most recent of the reviewer's readings recorded BEFORE the draft was created on the server (server times
    on both sides); None when there is none."""
    created = _as_datetime(draft_created_at)
    if created is None:
        return None
    best, best_at = None, None
    for item in readings:
        at = _as_datetime(item[2].get("at"))
        if at is None or at >= created:
            continue
        if best_at is None or at > best_at:
            best, best_at = item, at
    return best


def build(service: Any, segmentation_id: str, metadata: Any, final: np.ndarray, reviewer: Any,
          list_same_image) -> Dict[str, Any]:
    """The record stored with a confirmation of the AI review. Never raises: what cannot be computed is reported."""
    record: Dict[str, Any] = {"version": RECORD_VERSION, "computed_at": datetime.utcnow().isoformat() + "Z",
                              "lesion_connectivity": 18, "reviewed_mask_sha256": mask_sha256(final)}
    try:
        loaded = load(service, segmentation_id, ORIGINAL)
        if loaded is None or loaded[0].shape != final.shape:
            record.update({"available": False, "reason": "original_not_stored"})
            return record
        draft, meta = loaded
        record.update({"available": True, "draft_mask_sha256": meta.get("mask_sha256"),
                       "draft_stored_at": meta.get("at"), **decision_record(draft, final)})
        record["unaided"] = {"available": False, "reason": "no_reading_before_draft"}
        reading = reading_before(own_readings(service, list_same_image(), reviewer),
                                 getattr(metadata, "created_at", None))
        if reading is not None:
            seg, unaided, umeta = reading
            if unaided.shape != final.shape:
                record["unaided"] = {"available": False, "reason": "reading_on_another_grid",
                                     "segmentation_id": seg.segmentation_id}
            else:
                record["unaided"] = {"available": True, "segmentation_id": seg.segmentation_id,
                                     "recorded_at": umeta.get("at"), "reading_mask_sha256": umeta.get("mask_sha256"),
                                     **unaided_record(unaided, draft, final)}
    except Exception as e:  # noqa: BLE001 — the record never blocks the confirmation
        logger.error("Lesion review record not computed", extra={"segmentation_id": segmentation_id, "error": str(e)})
        record.update({"available": False, "reason": "not_computed"})
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
