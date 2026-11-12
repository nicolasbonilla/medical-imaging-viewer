"""G26 (fifth review of PR #81): the compare and SEL routes answered for generated request bodies, as (status, SHA-256 of
the canonical JSON). Imports only ``app.*`` and works on the base code (5ee06b7) and on this branch alike, so
scripts/safety/quality_gate_flags_off_snapshot.py records the base answers and test_rc122_flags_off_identity.py checks
that, with QUALITY_GATE_ENFORCED off, this branch answers byte-identically. DRAFT, PENDING owner approval.
"""
import hashlib
import json
from datetime import datetime

import numpy as np

PATIENT = "11111111-1111-1111-1111-111111111111"
SHAPE = (12, 24, 24)
SCANNER = {"manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0,
           "mr_acquisition_type": "2D", "slice_thickness_mm": 3.0, "repetition_time_ms": 9000.0,
           "echo_time_ms": 81.0, "inversion_time_ms": 2500.0}
ACQ_VARIANTS = {
    "same": (SCANNER, SCANNER),
    "other_vendor": (SCANNER, {**SCANNER, "manufacturer": "GE MEDICAL SYSTEMS"}),
    "other_field": (SCANNER, {**SCANNER, "magnetic_field_strength_t": 1.5}),
    "other_thickness": (SCANNER, {**SCANNER, "slice_thickness_mm": 5.0}),
    "missing_tp2": (SCANNER, None),
    "missing_both": (None, None),
    "partial_tp2": (SCANNER, {**SCANNER, "manufacturer": None}),
    "short_ti_tp2": (SCANNER, {**SCANNER, "inversion_time_ms": 900.0}),
}
ORDERS = {"ok": ("2024-01-10", "2025-01-12"), "same_date": ("2024-01-10", "2024-01-10"),
          "reversed": ("2025-01-12", "2024-01-10")}
BODIES = {
    "plain": {},
    "attested": {"quality_gate_attestation": {"tp1": True, "tp2": False}},
    "bad_string": {"quality_gate_attestation": "yes"},
    "bad_value": {"quality_gate_attestation": {"tp1": "true"}},
    "bad_list": {"quality_gate_attestation": ["tp1"]},
    "bad_key": {"quality_gate_attestation": {"tp3": True}},
    # SEL only: where it checks its input type (the base order, G26). Not sent to compare: an instance mask there
    # is read from the instance store, which a test never reaches.
    "tp2_instance": {"tp2": {"type": "instance", "id": "s2"}},
    "tp1_unknown_tp2_instance": {"tp1": {"type": "segmentation", "id": "nope"}, "tp2": {"type": "instance", "id": "s2"}},
    "no_tp2": {"tp2": None},
}
SEL_ONLY = ("tp2_instance", "tp1_unknown_tp2_instance")
ROUTES = {"compare": "/api/v1/segmentation/longitudinal/compare", "sel": "/api/v1/segmentation/longitudinal/sel"}


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def route_snapshot():
    from fastapi.testclient import TestClient
    import app.api.routes.segmentation_analysis as sa
    from app.core.container import get_segmentation_service, get_storage_service
    from app.main import app
    from app.security import get_current_active_user
    from app.security.models import User, UserRole

    tp1 = np.zeros(SHAPE, np.uint8)
    tp1[2:5, 4:7, 4:7] = 1
    tp2 = tp1.copy()
    tp2[7:10, 15:18, 15:18] = 1
    files = {sid: f"patients/{PATIENT}/studies/st-{sid}/series/se-{sid}/{sid}.nii.gz" for sid in ("s1", "s2")}

    class _Meta:
        def __init__(self, sid):
            self.file_id, self.analysis_data, self.modified_at = files[sid], {}, None

    class _Seg:
        cache = None

        def get_mask(self, sid):
            return {"s1": tp1, "s2": tp2}.get(sid)

        def get_loaded(self, sid):
            return {"metadata": _Meta(sid), "masks_3d": self.get_mask(sid)} if sid in files else None

        async def get_metadata(self, sid):
            return _Meta(sid) if sid in files else None

        def persist(self, sid):
            pass

    now = datetime(2026, 11, 12)
    user = User(id="id-dr_rev", username="dr_rev", email="dr_rev@example.com", full_name="dr_rev",
                role=UserRole.RADIOLOGIST, is_active=True, is_locked=False, email_verified=True,
                created_at=now, updated_at=now)
    state = {"acq": ACQ_VARIANTS["same"], "order": ORDERS["ok"]}

    async def _no_check(specs, u):
        return None

    async def _source(file_id, storage_service, context):
        return None, (1.0, 1.0, 3.0), None

    saved = {k: getattr(sa, k, None) for k in ("authorize_mask_specs", "_load_source_intensity", "_source_acquisition",
                                               "_source_visit")}
    settings_flag = getattr(sa.settings, "QUALITY_GATE_ENFORCED", None)
    sa.authorize_mask_specs = _no_check
    sa._load_source_intensity = _source
    sa._source_acquisition = lambda fid: dict(state["acq"][0 if fid == files["s1"] else 1] or {}) or None
    sa._source_visit = lambda fid: {"study_id": f"st-{'s1' if fid == files['s1'] else 's2'}",
                                    "study_date": state["order"][0 if fid == files["s1"] else 1]}
    if settings_flag is not None:
        sa.settings.QUALITY_GATE_ENFORCED = False
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_segmentation_service] = lambda: _Seg()
    app.dependency_overrides[get_storage_service] = lambda: object()
    out = {}
    try:
        client = TestClient(app)
        for acq_name, acq in ACQ_VARIANTS.items():
            for order_name, order in ORDERS.items():
                state.update(acq=acq, order=order)
                for body_name, extra in BODIES.items():
                    for route_name, path in ROUTES.items():
                        if route_name == "compare" and body_name in SEL_ONLY:
                            continue
                        body = {"tp1": {"type": "segmentation", "id": "s1"}, "tp2": {"type": "segmentation", "id": "s2"},
                                **extra}
                        r = client.post(path, json=body)
                        try:
                            payload = r.json()
                        except Exception:  # noqa: BLE001
                            payload = r.text
                        key = f"{route_name}|{acq_name}|{order_name}|{body_name}"
                        out[key] = [r.status_code, hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()[:16]]
    finally:
        for k, v in saved.items():
            if v is not None:
                setattr(sa, k, v)
        if settings_flag is not None:
            sa.settings.QUALITY_GATE_ENFORCED = settings_flag
        for dep in (get_current_active_user, get_segmentation_service, get_storage_service):
            app.dependency_overrides.pop(dep, None)
    return out


if __name__ == "__main__":  # pragma: no cover — used by the snapshot script on the base code
    print("G26-ROUTES:" + json.dumps(route_snapshot()), flush=True)   # marked: the app may log to stdout too
