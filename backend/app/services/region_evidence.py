"""HAZ-005 / RC-010 (amended) — helpers shared by every channel that serves MAGNIMS region
classifications (HTTP routes, the MCP clinical server). Pure functions, no dependencies."""


def strip_region_confidence(classification):
    """HAZ-005: classifications persisted BEFORE 2026-09-28 still carry fabricated per-lesion
    `confidence` values (a distance mapped onto 0.70-0.95, or a fixed 0.50). Null them before they
    reach the assistant, which would otherwise repeat them as clinical certainty."""
    if not isinstance(classification, dict):
        return classification
    lesions = classification.get("lesions")
    if not isinstance(lesions, list):
        return classification
    return {**classification,
            "lesions": [{**l, "confidence": None} if isinstance(l, dict) else l for l in lesions]}
