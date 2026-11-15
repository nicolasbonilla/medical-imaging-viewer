"""Read-only access to the app's own functions (PREREG 2.2). Nothing here changes app behaviour.

Imports are lazy so that the verifier and the analysis can run without the backend environment.
"""
import sys
import warnings
from datetime import date
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def app():
    """The app modules the benchmark uses, imported once in an offline environment."""
    config.offline_env()
    if str(config.BACKEND) not in sys.path:
        sys.path.insert(0, str(config.BACKEND))
    warnings.filterwarnings("ignore")
    import logging
    logging.disable(logging.WARNING)
    from app.services import lesion_analysis_service as las
    from app.services import ms_region_classifier as rc
    from app.services import dis_review_gate as gate
    from app.services import longitudinal_candidate_safety as lcs
    from app.services import longitudinal_tracking_service as lts
    from app.services import acquisition_geometry as acq
    from app.services import report_payload_guard as guard
    from app.services import brain_report_service as brs
    from app.api.routes import ai_report as route
    from app.services.segmentation_service import SegmentationService

    class _M:
        pass

    m = _M()
    m.las, m.rc, m.gate, m.lcs, m.lts, m.acq, m.guard, m.brs, m.route = las, rc, gate, lcs, lts, acq, guard, brs, route
    m.SegmentationService = SegmentationService
    return m


def synthetic_identifiers():
    """A patient record whose fields cannot occur in a prompt (public data carries no identifiers)."""
    a = app()
    record = {"mrn": "ZZQX-PUBLIC-000000", "given_name": "Zzqxpublic", "family_name": "Zzqxdataset",
              "birth_date": date(1066, 12, 31).isoformat()}
    return a.guard.PatientIdentifiers.from_record(record)
