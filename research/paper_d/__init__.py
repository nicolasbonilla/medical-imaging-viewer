"""Paper D — fragility of automated dissemination-in-space (DIS) decisions.

RESEARCH CODE, NOT THE MEDICAL DEVICE. Nothing here is imported by `backend/app`. The device's
Class C modules (`ms_region_classifier`, `lesion_analysis_service`, `lesion_metrics`) are imported
READ-ONLY so the reference DIS is computed by the device's own code; they are never modified.

Protocol: docs/research/paper-d/PROTOCOL.md (committed before any result was computed).
"""
