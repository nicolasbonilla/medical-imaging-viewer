"""Storage-reference parsing and authorization — IEC 62304 Class C.

Risk control RC-027 for HAZ-010. Implements CAPA-002 CA-2.3 for patient-scoped
imaging objects.

THE DEFECT (CAPA-002 §2)
------------------------
The imaging routes take `{file_id:path}` and pass it straight to
`storage_service.download_file(bucket, file_id)`. `file_id` is a raw,
caller-supplied object key of the form
`patients/{patient_id}/studies/{study_id}/series/{series_id}/{file}`.

A caller could therefore supply ANY key in the bucket — including another
patient's image, or a non-patient object such as `segmentations/...` — and the
server would fetch and return it. Authentication was enforced; authorization was
not. OWASP API1:2023 applied to protected health information.

WHY THIS IS A PARSER, NOT A BLOCKLIST
-------------------------------------
The instinct is to *reject bad paths* (strip `..`, block `/config/`). That is a
blocklist, and blocklists on storage keys are a losing game — GCS object names
are opaque byte strings, `..` does not traverse, encodings vary, and every new
object prefix is a new hole. Instead this module **parses against a positive
grammar**: an input is a storage reference only if it matches
`patients/{uuid}/studies/{uuid}/series/{uuid}/{safe-filename}` exactly.
Everything else — every prefix, every encoding, every extra segment — is not a
storage reference and is refused. Anything that parses has, by construction, a
patient_id that can then be authorized.

This is ISO 14971 §7.1 inherent-safety: rather than trusting each route to
validate a raw key correctly forever, the key is only ever handled as a
structured, validated, patient-attributed reference.

SCOPE
-----
Covers the patient-scoped imaging grammar (shape 1). Segmentation objects
(`segmentations/{id}/...`, shape 2) are authorized via their Firestore
patient link, not via this parser, and are tracked separately.
"""
import re
from dataclasses import dataclass
from uuid import UUID


class StorageRefError(ValueError):
    """Raised when a caller-supplied identifier is not a valid, safe,
    patient-scoped storage reference. Deliberately a distinct type so the API
    layer can map it to a 404 (never revealing whether the object exists)."""


# Filename: a non-empty run of a strict safe charset, no path separators, no
# parent-directory tokens. Instance files are `{uuid}.{ext}`; masks etc. share
# the same safe shape. The charset intentionally excludes '/', '\', spaces and
# control bytes, so a filename can never re-introduce a path segment.
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")

# Extensions the imaging pipeline actually reads. An allowlist, not a blocklist:
# an unrecognised extension is refused rather than passed through.
_ALLOWED_SUFFIXES = (".dcm", ".nii", ".nii.gz", ".npz", ".json")

_EXPECTED_SEGMENTS = 7  # patients / pid / studies / sid / series / serid / file


@dataclass(frozen=True)
class PatientStorageRef:
    """A parsed, validated, patient-attributed storage reference.

    Constructing one is proof that the raw input matched the canonical grammar
    and carried three well-formed UUIDs. `object_path` is rebuilt from the parsed
    components, never echoed from the input, so no unparsed byte of caller input
    can reach the storage key.
    """

    patient_id: str
    study_id: str
    series_id: str
    filename: str

    @property
    def object_path(self) -> str:
        return (
            f"patients/{self.patient_id}/studies/{self.study_id}"
            f"/series/{self.series_id}/{self.filename}"
        )


def _valid_uuid(segment: str) -> str:
    """Return the canonical string form of a UUID segment, or raise.

    Canonicalising (rather than merely checking) means the rebuilt object_path
    uses a normalised UUID, so two inputs differing only in UUID casing cannot
    map to two different-looking keys.
    """
    try:
        return str(UUID(segment))
    except (ValueError, AttributeError, TypeError):
        raise StorageRefError("storage reference contains a malformed identifier")


def _valid_filename(segment: str) -> str:
    if not _SAFE_FILENAME.match(segment):
        raise StorageRefError("storage reference contains an unsafe filename")
    if segment in (".", ".."):
        raise StorageRefError("storage reference contains an unsafe filename")
    lowered = segment.lower()
    if not any(lowered.endswith(suffix) for suffix in _ALLOWED_SUFFIXES):
        raise StorageRefError("storage reference has an unsupported file type")
    return segment


def parse_patient_storage_ref(raw: str) -> PatientStorageRef:
    """Parse a caller-supplied identifier into a validated storage reference.

    Raises StorageRefError on ANY deviation from
    `patients/{uuid}/studies/{uuid}/series/{uuid}/{safe-filename}`:
    wrong prefix, wrong segment count, non-UUID segment, unsafe filename,
    leading/trailing slash, empty segment, or any control/traversal byte.

    Pure and total: no I/O, every input either yields a reference or raises.
    """
    if not raw or not isinstance(raw, str):
        raise StorageRefError("empty storage reference")

    # Reject control bytes and NULs outright — they have no place in a key and
    # are a classic smuggling vector past downstream parsers.
    if any(ord(ch) < 0x20 for ch in raw):
        raise StorageRefError("storage reference contains control characters")

    # No absolute paths, no backslashes, no scheme. Anchored, not a search.
    if raw.startswith("/") or "\\" in raw or "://" in raw:
        raise StorageRefError("storage reference is not a relative object path")

    segments = raw.split("/")
    if len(segments) != _EXPECTED_SEGMENTS:
        raise StorageRefError("storage reference does not match the expected shape")
    if any(seg == "" for seg in segments):
        raise StorageRefError("storage reference has an empty path segment")

    prefix_p, patient, prefix_s, study, prefix_ser, series, filename = segments

    if (prefix_p, prefix_s, prefix_ser) != ("patients", "studies", "series"):
        raise StorageRefError("storage reference is not a patient imaging object")

    return PatientStorageRef(
        patient_id=_valid_uuid(patient),
        study_id=_valid_uuid(study),
        series_id=_valid_uuid(series),
        filename=_valid_filename(filename),
    )
