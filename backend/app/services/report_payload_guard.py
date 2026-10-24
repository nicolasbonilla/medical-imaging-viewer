"""What the AI report draft may send to the model provider, and the check before it leaves — CAPA-014.

Redesign after the independent review of PR #67 (ISO 14971 §7.1: inherent safety by design first).
Part of the Class C report software item; called only by ``brain_report_service.py``.

RC-064 — structured payload only (inherent safety by design), ``provider_payload``:
    The request is built from the device's measurements (numbers), labels from the device's fixed
    vocabulary (MAGNIMS regions, zone names, volumetry structure names, size classes, abnormality
    types, and every label name the application ships), sex (M or F) and a 5-year age band ("90 or
    older" from 90). Nothing else is copied: no free-text or user-typed field, no unknown field; a label
    outside the vocabulary becomes a numbered placeholder ("[unlisted label 2]", the same number for the
    same label in groups and rows; its name is shown to the clinician in the draft, never sent); a value
    where a number is expected and that is not one is printed "not available", never 0; a number outside
    the physical range of its field (a date or a record number in a number field) refuses the request.
    Only a flag says that the clinician typed something; the typed text is merged into the draft by the
    route, after the model returns.

RC-065 — detection-only tripwire on the final prompt, ``find_identifiers``:
    It never edits text. Before the call it looks — after NFKC normalisation, removal of format
    characters (soft hyphen, zero-width characters, BOM), mapping of look-alike Cyrillic/Greek letters
    and of accents — for the patient's own identifiers read from the patient record (names and names
    written together, German ae/oe/ue spellings; letter-and-digit record numbers with up to three
    separator characters between characters; all-digit record numbers and the digits of a prefixed one
    as a whole number not part of a decimal number nor followed by a unit; birth date by
    its day, month and year parts in many forms; phone numbers with and without country code and
    trunk 0; e-mail; city; street) and for generic identifier patterns (e-mail, dates with a year,
    phone-like numbers, long or ID-like numbers, titled names). Any finding:
    nothing is sent. Words of the device's own fixed text and vocabulary are never reported on their
    own (a patient named White does not stop "Deep White Matter"), nor two such words in the order the
    device's own text has them ("Deep White"); such a name is still found next to the other names of the
    patient. The scanned text is capped and every pattern is linear.

@module services.report_payload_guard
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Errors — nothing may be sent to the model provider
# ─────────────────────────────────────────────────────────────────────────────
class ProviderGuardError(Exception):
    """Nothing may be sent to the model provider. Messages name categories, never an identifier."""


class PatientRecordUnavailable(ProviderGuardError):
    """The patient record needed for the check is missing, unreadable or incomplete."""


class IdentifierInPrompt(ProviderGuardError):
    """The tripwire found an identifier in the text prepared for the provider."""


class ImplausibleMeasurement(ProviderGuardError):
    """A number is outside the physical range of its field: a date, a record number or a phone number put
    into a number field cannot be told from a measurement, so nothing is sent."""


FREE_TEXT_FIELDS = ("clinical_indication", "technique", "additional_observations")
UNLISTED = "[unlisted label]"
MAX_SCANNED_CHARS = 400_000


class NotAvailable(str):
    """A value the device did not supply as a number: printed "not available" whatever the format asked
    for, so a missing or malformed measurement is never reported as 0."""

    def __format__(self, spec: str) -> str:
        return str(self)


NOT_AVAILABLE = NotAvailable("not available")
# The DIS evaluation states of PR #68 (PRB-003, `dis_review_gate.EVALUATED` / `NOT_EVALUATED`).
DIS_EVALUATED, DIS_NOT_EVALUATED = "evaluated", "not_evaluated"

# Physical range of each number that is printed. Counts stay below 7 digits; voxel counts below 16 million
# (a brain imaged at 0.46 mm isotropic), which also excludes every date written YYYYMMDD from 1900 on;
# volumes below the largest intracranial volume; centroids inside a 4096-voxel volume.
_COUNT_MAX = 100_000
_VOXELS_MAX = 16_000_000
_LESION_MM3_MAX = 2_500_000
_LESION_ML_MAX = 2_500
_ANOMALY_MM3_MAX = 3_000_000
_VOLUMETRY_ML_MAX = 3_000
_CENTROID_MAX = 4_096
_DELTA_PERCENT = (-100, 999_999)

_MEASUREMENT_BLOCKS = ("lesion_analysis", "dis_assessment", "longitudinal", "zone_stats",
                       "segmentation_labels", "anomalies")
_KNOWN_FIELDS = frozenset(FREE_TEXT_FIELDS + _MEASUREMENT_BLOCKS + ("patient_age", "patient_sex"))


# ─────────────────────────────────────────────────────────────────────────────
# RC-064 — the device's fixed label vocabulary and the structured payload
# ─────────────────────────────────────────────────────────────────────────────
_EXTRA_LABELS = ("Unknown", "Lesion", "Background", "small", "medium", "large", "atrophy", "enlargement")
# Label names of the application's label presets that no backend service defines (frontend
# src/types/segmentation.ts default preset, src/services/flames/draft.ts, the short SynthSeg names of
# src/types/ai.ts BRAIN_STRUCTURE_LABELS). The backend's SynthSeg names are imported below. A test reads
# every preset of the application and checks that each name is in the vocabulary.
_SHORT_STRUCTURES = ("Cerebral WM", "Cerebral Cortex", "Lateral Ventricle", "Inf Lat Ventricle", "Cerebellum WM",
                     "Cerebellum Cortex", "Thalamus", "Caudate", "Putamen", "Pallidum", "Hippocampus", "Amygdala",
                     "Accumbens", "VentralDC")
APP_LABEL_NAMES = ("MS Lesion (Active)", "MS Lesion (Chronic)", "T2/FLAIR Hyperintensity", "Black Hole (T1)",
                   "Active (Gd+)", "Lesion (AI draft, unreviewed)") + tuple(
                       f"{side} {name}" for side in ("L", "R") for name in _SHORT_STRUCTURES)
_LABEL_PATTERNS = (re.compile(r"Structure \d{1,4}"), re.compile(r"Label \d{1,3}"))


@lru_cache(maxsize=1)
def label_vocabulary() -> Dict[str, str]:
    """casefolded label -> label, from the services that produce the labels (single source of truth)."""
    from app.services.ai_segmentation_service import SYNTHSEG_LABELS
    from app.services.brain_volumetry_service import STRUCTURE_NAMES
    from app.services.lesion_analysis_service import MAGNIMS_REGIONS
    from app.services.ms_region_classifier import REGION_NAMES
    labels = set(MAGNIMS_REGIONS.values()) | set(REGION_NAMES.values()) | set(STRUCTURE_NAMES.values())
    labels |= {name for name, _color in SYNTHSEG_LABELS.values()}
    labels |= set(_EXTRA_LABELS) | set(APP_LABEL_NAMES)
    return {label.casefold(): label for label in labels}


def vocabulary_label(value: Any) -> Optional[str]:
    """The canonical label when `value` is one of the device's labels, otherwise None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if any(p.fullmatch(text) for p in _LABEL_PATTERNS):
        return text
    return label_vocabulary().get(text.casefold())


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def age_band(value: Any) -> Optional[str]:
    """5-year band of an age in years ("45-49"); "90 or older" from 90. None when not an age."""
    if isinstance(value, str) and re.fullmatch(r"\s*\d{1,3}(?:\.\d{1,3})?\s*", value):
        value = float(value)
    n = _number(value)
    if n is None or n < 0 or n > 130:
        return None
    years = int(n)
    if years >= 90:
        return "90 or older"
    low = years - years % 5
    return f"{low}-{low + 4}"


@dataclass
class ProviderPayload:
    findings: Dict[str, Any]
    volumetry: Optional[Dict[str, Any]]
    withheld: Dict[str, int] = field(default_factory=dict)
    unlisted: Dict[str, str] = field(default_factory=dict)    # placeholder -> label as written (never sent)


class _Projector:
    def __init__(self):
        self.counts: Counter = Counter()
        self.unlisted: Dict[str, str] = {}      # label as written -> its placeholder

    def label(self, value: Any, allowed: Optional[Iterable[str]] = None) -> str:
        """The device's label, or a numbered placeholder: the same label always gets the same number, in
        groups and in rows. Nothing of a label outside the vocabulary enters the payload."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return NOT_AVAILABLE
        label = vocabulary_label(value)
        if label is not None and (allowed is None or label in allowed):
            return label
        self.counts["unlisted_labels"] += 1
        written = value.strip() if isinstance(value, str) else repr(value)
        if written not in self.unlisted:
            self.unlisted[written] = f"[unlisted label {len(self.unlisted) + 1}]"
        return self.unlisted[written]

    def keyed(self, mapping: Any) -> List[Tuple[str, dict]]:
        """(label, value) pairs of a dict keyed by labels; a label met again is numbered among its own
        repeats only ("Periventricular (2)")."""
        out, times = [], Counter()
        for key, value in (mapping.items() if isinstance(mapping, dict) else ()):
            if not isinstance(value, dict):
                continue
            label = self.label(key)
            times[label] += 1
            out.append((label if times[label] == 1 else f"{label} ({times[label]})", value))
        return out

    @staticmethod
    def put(target: dict, key: str, value: Any) -> None:
        if value is not None:
            target[key] = value

    def number(self, value: Any, name: str, low: float, high: float, required: bool = True) -> Any:
        """The number; NOT_AVAILABLE (None when optional) when it is not a number; refuses outside [low, high]."""
        n = _number(value)
        if n is None:
            if value is not None:
                self.counts["values_not_numbers"] += 1
            return NOT_AVAILABLE if required else None
        if not low <= n <= high:
            raise ImplausibleMeasurement(f"a measurement is outside its plausible range: {name}")
        return n

    def count(self, value: Any, name: str, high: int = _COUNT_MAX, required: bool = True) -> Any:
        n = self.number(value, name, 0, high, required)
        if isinstance(n, float):
            if n != int(n):                       # a count with a fraction is not a count
                self.counts["values_not_numbers"] += 1
                return NOT_AVAILABLE if required else None
            n = int(n)
        return n

    def lesion_analysis(self, la: dict) -> dict:
        o: dict = {"total_count": self.count(la.get("total_count"), "total_count"),
                   "total_burden_mm3": self.number(la.get("total_burden_mm3"), "total_burden_mm3", 0, _LESION_MM3_MAX),
                   "total_burden_ml": self.number(la.get("total_burden_ml"), "total_burden_ml", 0, _LESION_ML_MAX)}
        regions = {}
        for label, info in self.keyed(la.get("regions")):
            regions[label] = {
                "lesion_count": self.count(info.get("lesion_count"), "lesion_count"),
                "total_volume_mm3": self.number(info.get("total_volume_mm3"), "total_volume_mm3", 0, _LESION_MM3_MAX),
                "total_volume_ml": self.number(info.get("total_volume_ml"), "total_volume_ml", 0, _LESION_ML_MAX)}
        if regions:
            o["regions"] = regions
        sd = la.get("size_distribution")
        if isinstance(sd, dict) and sd:
            o["size_distribution"] = {k: self.count(sd.get(k), "size_distribution") for k in ("small", "medium", "large")}
        lesions = []
        for i, les in enumerate(la.get("lesions") or []):
            if not isinstance(les, dict):
                continue
            ctr = les.get("centroid") if isinstance(les.get("centroid"), dict) else {}
            lesions.append({
                "id": self.count(les.get("id"), "lesion_id", required=False) or i + 1,
                "region": self.label(les.get("region")),
                "volume_mm3": self.number(les.get("volume_mm3"), "volume_mm3", 0, _LESION_MM3_MAX),
                "volume_ml": self.number(les.get("volume_ml"), "volume_ml", 0, _LESION_ML_MAX),
                "size_category": self.label(les.get("size_category"), ("small", "medium", "large")),
                "centroid": {k: self.number(ctr.get(k), "centroid", 0, _CENTROID_MAX) for k in ("z", "y", "x")}})
        if lesions:
            o["lesions"] = lesions
        return o

    def dis_assessment(self, dis: dict) -> dict:
        """The DIS block, with its evaluation state kept (PR #68, PRB-003). Not evaluated, an unknown state or no
        yes/no conclusion: only the state "not_evaluated" — no conclusion, region presence or count — so the
        model is never told "NOT MET" for a DIS that was not evaluated (as "not available", never 0)."""
        state = dis.get("evaluation_status")
        if state not in (None, DIS_EVALUATED) or not isinstance(dis.get("dis_met"), bool):
            return {"evaluation_status": DIS_NOT_EVALUATED}
        o: dict = {"dis_met": dis.get("dis_met") is True,
                   "regions_with_lesions": self.count(dis.get("regions_with_lesions"), "regions_with_lesions"),
                   "total_dis_regions": self.count(dis.get("total_dis_regions"), "total_dis_regions")}
        details = {label: {"present": info.get("present") is True} for label, info in self.keyed(dis.get("region_details"))}
        if details:
            o["region_details"] = details
        o["has_active_lesions"] = dis.get("has_active_lesions") is True
        o["active_voxels"] = self.count(dis.get("active_voxels"), "active_voxels", _VOXELS_MAX)
        o["has_black_holes"] = dis.get("has_black_holes") is True
        o["black_hole_voxels"] = self.count(dis.get("black_hole_voxels"), "black_hole_voxels", _VOXELS_MAX)
        if state == DIS_EVALUATED:
            o["evaluation_status"] = DIS_EVALUATED     # kept as received; never invented for a block without it
        return o

    def longitudinal(self, lng: dict) -> dict:
        if lng.get("abstained") is True:
            return {"abstained": True}
        o: dict = {key: self.number(lng.get(key), key, 0, _LESION_ML_MAX) for key in ("burden_tp1_ml", "burden_tp2_ml")}
        for key in ("total_lesions_tp1", "total_lesions_tp2"):
            o[key] = self.count(lng.get(key), key)
        self.put(o, "burden_delta_percent",
                 self.number(lng.get("burden_delta_percent"), "burden_delta_percent", *_DELTA_PERCENT, required=False))
        sc = lng.get("status_counts") if isinstance(lng.get("status_counts"), dict) else {}
        o["status_counts"] = {k: self.count(sc.get(k), "status_counts")
                              for k in ("new", "enlarged", "resolved", "shrunk", "stable")}
        return o

    def zone_stats(self, zs: dict) -> dict:
        o: dict = {"total_brain_voxels": self.count(zs.get("total_brain_voxels"), "total_brain_voxels", _VOXELS_MAX)}
        zones = {label: {"voxel_count": self.count(info.get("voxel_count"), "voxel_count", _VOXELS_MAX),
                         "percentage": self.number(info.get("percentage"), "percentage", 0, 100)}
                 for label, info in self.keyed(zs.get("zones"))}
        if zones:
            o["zones"] = zones
        return o

    def anomalies(self, items: Any) -> list:
        out = []
        for a in items if isinstance(items, list) else []:
            if not isinstance(a, dict):
                continue
            item = {"type": self.label(a.get("type"))}
            if a.get("location") is not None:
                item["location"] = self.label(a.get("location"))
            self.put(item, "confidence", self.number(a.get("confidence"), "confidence", 0, 1, required=False))
            self.put(item, "volume_mm3", self.number(a.get("volume_mm3"), "volume_mm3", 0, _ANOMALY_MM3_MAX,
                                                     required=False))
            out.append(item)
        return out

    def volumetry(self, vol: dict) -> dict:
        o: dict = {}
        for key in ("total_brain_volume_ml", "intracranial_volume_ml"):
            self.put(o, key, self.number(vol.get(key), key, 0, _VOLUMETRY_ML_MAX, required=False))
        structures = []
        for s in vol.get("structures") or []:
            if not isinstance(s, dict):
                continue
            volume = self.number(s.get("volume_ml"), "volume_ml", 0, _VOLUMETRY_ML_MAX, required=False)
            if volume is None:
                continue
            item = {"structure_name": self.label(s.get("structure_name")), "volume_ml": volume,
                    "is_abnormal": s.get("is_abnormal") is True}
            self.put(item, "normative_percentile",
                     self.number(s.get("normative_percentile"), "normative_percentile", 0, 100, required=False))
            if s.get("abnormality_type"):
                item["abnormality_type"] = self.label(s.get("abnormality_type"), ("atrophy", "enlargement"))
            structures.append(item)
        o["structures"] = structures
        return o


def provider_payload(findings: Optional[Dict[str, Any]], volumetry: Optional[Dict[str, Any]]) -> ProviderPayload:
    """RC-064: the structured payload the provider may receive. The inputs are not modified.

    Raises ImplausibleMeasurement when a number is outside the physical range of its field.
    """
    f = findings if isinstance(findings, dict) else {}
    p = _Projector()
    p.counts["free_text_fields"] = sum(1 for k in FREE_TEXT_FIELDS if f.get(k))
    p.counts["unknown_fields"] = sum(1 for k in f if k not in _KNOWN_FIELDS)
    out: Dict[str, Any] = {}
    if any(isinstance(f.get(k), str) and f[k].strip() for k in FREE_TEXT_FIELDS):
        out["clinician_entry"] = True       # a flag only: the text itself is added to the draft by the route
    band = age_band(f.get("patient_age"))
    if band:
        out["patient_age"] = band
    if f.get("patient_sex") in ("M", "F"):
        out["patient_sex"] = f["patient_sex"]
    for key, build in (("lesion_analysis", p.lesion_analysis), ("dis_assessment", p.dis_assessment),
                       ("longitudinal", p.longitudinal), ("zone_stats", p.zone_stats)):
        if isinstance(f.get(key), dict) and f[key]:
            out[key] = build(f[key])
    if isinstance(f.get("segmentation_labels"), list) and f["segmentation_labels"]:
        out["segmentation_labels"] = [p.label(v) for v in f["segmentation_labels"]]
    if f.get("anomalies"):
        out["anomalies"] = p.anomalies(f["anomalies"])
    vol = p.volumetry(volumetry) if isinstance(volumetry, dict) and volumetry else None
    return ProviderPayload(findings=out, volumetry=vol, withheld={k: v for k, v in sorted(p.counts.items())},
                           unlisted={placeholder: written for written, placeholder in p.unlisted.items()})


# ─────────────────────────────────────────────────────────────────────────────
# RC-065 — normalisation used by the tripwire
# ─────────────────────────────────────────────────────────────────────────────
_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s",
    "ԁ": "d", "ӏ": "l", "к": "k", "м": "m", "н": "h", "т": "t", "в": "b", "А": "A", "Е": "E", "О": "O",
    "Р": "P", "С": "C", "У": "Y", "Х": "X", "І": "I", "К": "K", "М": "M", "Н": "H", "Т": "T", "В": "B",
    "ο": "o", "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ρ": "p", "τ": "t", "υ": "u", "χ": "x",
    "Ο": "O", "Α": "A", "Ε": "E", "Ι": "I", "Κ": "K", "Ν": "N", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
})


def normalise(text: str) -> str:
    """NFKC, format characters removed, look-alikes mapped, accents removed, casefolded."""
    t = unicodedata.normalize("NFKC", text)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Cf")
    t = t.translate(_CONFUSABLES)
    t = unicodedata.normalize("NFKD", t)
    return "".join(ch for ch in t if not unicodedata.combining(ch)).casefold()


_WORD = re.compile(r"[^\W\d_]+")


def words_of(text: str) -> List[str]:
    return _WORD.findall(normalise(text))


def _spellings(original: str) -> Set[str]:
    """Normalised spellings of a name part: as written, with ä/ö/ü spelt ae/oe/ue, and the reverse."""
    low = unicodedata.normalize("NFKC", original).casefold()
    expanded = low.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    base = normalise(low)
    return {s for s in (base, normalise(expanded), base.replace("ae", "a").replace("oe", "o").replace("ue", "u")) if s}


_PARTICLES = frozenset({"de", "del", "la", "las", "los", "y", "e", "da", "das", "do", "dos", "di", "du", "van",
                        "von", "der", "den", "zu", "le", "el", "al", "bin", "ibn", "st", "san", "santa"})


def _parts(name: str) -> List[str]:
    """Parts of a name; particles are dropped only when the name has other parts (so "Do" stays)."""
    parts = [p for p in re.split(r"[\s\-,.'’]+", name.strip()) if p]
    kept = [p for p in parts if normalise(p) not in _PARTICLES]
    return kept or parts


# ─────────────────────────────────────────────────────────────────────────────
# The patient's own identifiers, from the record the server holds
# ─────────────────────────────────────────────────────────────────────────────
def _digits(text: str) -> str:
    return "".join(c for c in text if c.isdigit() and c.isascii())


def _alnum(text: str) -> str:
    return "".join(c for c in text if c.isascii() and c.isalnum())


def _field(record: Any, name: str) -> Any:
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value)).strip()


@dataclass(frozen=True)
class PatientIdentifiers:
    """What must never reach the provider for this patient, read from the patient record."""

    given: FrozenSet[str]               # spellings of given and middle name parts
    family: FrozenSet[str]              # spellings of family name parts
    other_names: FrozenSet[str]         # emergency contact, city, street words
    record_numbers: Tuple[str, ...]     # alphanumeric characters of MRN / insurance number, and their digits
    birth_date: date
    phones: FrozenSet[str]              # digit strings: with and without country code and trunk 0
    emails: Tuple[str, ...]

    @classmethod
    def from_record(cls, record: Any) -> "PatientIdentifiers":
        """RC-065: a missing record, or one without record number, given name, family name or birth
        date, cannot be used — raises PatientRecordUnavailable."""
        if record is None:
            raise PatientRecordUnavailable("the patient's record could not be read")
        mrn, given, family = (_text(_field(record, k)) for k in ("mrn", "given_name", "family_name"))
        birth = _field(record, "birth_date")
        if isinstance(birth, str):
            try:
                birth = date.fromisoformat(birth[:10])
            except ValueError:
                birth = None
        elif hasattr(birth, "date") and callable(birth.date):
            birth = birth.date()
        if not (mrn and given and family and isinstance(birth, date)):
            raise PatientRecordUnavailable(
                "the patient's record lacks its record number, given name, family name or birth date")

        def spell(*names: str) -> FrozenSet[str]:
            return frozenset(s for n in names if n for p in _parts(n) for s in _spellings(p) if len(s) >= 2)

        middle = _text(_field(record, "middle_name"))
        street = " ".join(_text(_field(record, k)) for k in ("address_line1", "address_line2"))
        street_words = frozenset(s for p in re.split(r"[^\w]+", street) if len(p) >= 4 and not p.isdigit()
                                 for s in _spellings(p))
        others = spell(_text(_field(record, "emergency_contact_name")), _text(_field(record, "city"))) | street_words
        numbers = [n for n in (_alnum(normalise(_text(_field(record, k))))
                               for k in ("mrn", "insurance_policy_number")) if n]
        # the digits of a prefixed number on their own ("MRN-2025-0042" also as "20250042")
        numbers += [d for n in list(numbers) if not n.isdigit() and len(d := _digits(n)) >= 6 and d not in numbers]
        phones: Set[str] = set()
        for key in ("phone_mobile", "phone_home", "phone_work", "emergency_contact_phone"):
            raw = _text(_field(record, key))
            digits = _digits(raw)
            if not digits:
                continue
            international = raw.startswith("+") or digits.startswith("00")
            if digits.startswith("00"):
                digits = digits[2:]
            if international:
                phones.add(digits)
                for cc in (1, 2, 3):
                    national = digits[cc:]
                    phones.update((national, "0" + national))
            else:
                phones.update((digits, digits[1:] if digits.startswith("0") else digits))
        emails = tuple(normalise(e) for e in (_text(_field(record, "email")),) if "@" in e)
        return cls(given=spell(given, middle), family=spell(family), other_names=others, record_numbers=tuple(numbers),
                   birth_date=birth, phones=frozenset(p for p in phones if len(p) >= 7), emails=emails)


# ─────────────────────────────────────────────────────────────────────────────
# RC-065 — patterns (all linear: bounded repetitions, anchored starts)
# ─────────────────────────────────────────────────────────────────────────────
_MONTHS = {
    1: ("january", "jan", "enero", "ene", "januar", "janner", "jaenner"),
    2: ("february", "feb", "febrero", "februar"),
    3: ("march", "mar", "marzo", "marz", "maerz", "mrz"),
    4: ("april", "apr", "abril", "abr"),
    5: ("may", "mayo", "mai"),
    6: ("june", "jun", "junio", "juni"),
    7: ("july", "jul", "julio", "juli"),
    8: ("august", "aug", "agosto", "ago"),
    9: ("september", "sept", "sep", "septiembre", "setiembre"),
    10: ("october", "oct", "octubre", "oktober", "okt"),
    11: ("november", "nov", "noviembre"),
    12: ("december", "dec", "diciembre", "dic", "dezember", "dez"),
}
_ROMAN = {1: "i", 2: "ii", 3: "iii", 4: "iv", 5: "v", 6: "vi", 7: "vii", 8: "viii", 9: "ix", 10: "x", 11: "xi", 12: "xii"}
_ALL_MONTHS = "|".join(sorted({n for names in _MONTHS.values() for n in names}, key=len, reverse=True))
_SEP = r"[\s.,/\-]{0,3}(?:(?:de|del|of|the)[\s.,/\-]{1,3})?"
_ORD = r"(?:st|nd|rd|th|er|o)?\.?"
_BIRTH = r"(?<![a-z])(?:born|dob|d\.o\.b|birth|geb|geboren|geburtsdatum|nacid[oa]|nacimiento|f\.\s?nac|naissance|nee)"

_GENERIC = {
    "email": re.compile(r"(?<![a-z0-9._%+\-])[a-z0-9._%+\-]{1,64}@[a-z0-9\-]{1,63}(?:\.[a-z0-9\-]{1,63}){0,8}"
                        r"\.[a-z]{2,24}(?![a-z])"),
    "date": re.compile(
        r"(?<!\d)\d{1,2}\s?[./\-]\s?\d{1,2}\s?[./\-]\s?(?:19|20)\d{2}(?!\d)"
        r"|(?<!\d)(?:19|20)\d{2}[./\-]\d{1,2}[./\-]\d{1,2}(?!\d)"
        rf"|(?<!\d)\d{{1,2}}{_ORD}[\s.\-/]{{0,3}}(?:de\s)?(?:{_ALL_MONTHS})\.?[\s,.\-/]{{0,3}}(?:de\s)?(?:19|20)\d{{2}}(?!\d)"
        rf"|(?<![a-z])(?:{_ALL_MONTHS})\.?[\s\-]{{1,2}}\d{{1,2}}(?:st|nd|rd|th)?,?\s(?:19|20)\d{{2}}(?!\d)"
        r"|(?<!\d)\d{1,2}\.\s?(?:xii|xi|x|ix|viii|vii|vi|v|iv|iii|ii|i)\.\s?(?:19|20)\d{2}(?!\d)"),
    "phone": re.compile(r"\+\s?\d[\d\s().\-/]{6,24}\d"),
    "titled_name": re.compile(r"(?<![a-z])(?:dr|dra|prof|profa|herr|frau|mrs|mr|sra|sr)\.?\s{1,3}[a-z]{2,}"),
}
_DIGIT_RUN = re.compile(r"\d[\d\s().\-/]*")
_DIGIT_GROUP = re.compile(r"\d+")
_ASCII_DIGITS = re.compile(r"[0-9]+")
_ALNUM = re.compile(r"[a-z0-9]+")
_NUMBER_WITH_UNIT = re.compile(r"\d+(?:mm3|mm2|mm|cm3|cm2|cm|ml|ul|ms|mg|kg|g|t|th|st|nd|rd)")


def _birth_patterns(b: date) -> List["re.Pattern[str]"]:
    d, m, y = b.day, b.month, b.year
    day = rf"0?{d}" if d < 10 else str(d)
    num_month = rf"0?{m}" if m < 10 else str(m)
    names = "|".join(sorted(_MONTHS[m], key=len, reverse=True))
    month = rf"(?:{num_month}|{_ROMAN[m]}|{names})"
    year = rf"(?:{y}|'?{y % 100:02d})"
    return [re.compile(p) for p in (
        rf"(?<![\d]){day}{_ORD}{_SEP}{month}\.?{_SEP}{year}(?!\d)",              # 9.11.1975, 9-Nov-75, 9.XI.1975
        rf"(?<![a-z])(?:{names})\.?{_SEP}{day}{_ORD},?{_SEP}{year}(?!\d)",        # November 9, 1975
        rf"(?<!\d){num_month}{_SEP}{day}{_SEP}{year}(?!\d)",                      # 11/9/1975 (month first)
        rf"(?<!\d){y}{_SEP}{month}{_SEP}{day}(?!\d)",                             # 1975-11-09
        rf"{_BIRTH}[^\n\d]{{0,25}}(?<!\d){day}{_ORD}{_SEP}{month}(?![\d])",        # geb. 9.11. / nacido el 9/11
        rf"{_BIRTH}[^\n\d]{{0,25}}(?<!\d)'?(?:{y}|{y % 100:02d})(?!\d)",            # born in 1975 / born '75
    )]


_UNIT_AFTER = r"(?:mm3|mm2|mm|cm3|cm|ml|ul|voxels?|lesions?|regions?|years?|th|st|nd|rd)(?![a-z])|%"


def _record_number_pattern(chars: str) -> Optional["re.Pattern[str]"]:
    if chars.isdigit():
        if len(chars) < 6:
            return None     # a short all-digit number cannot be told from a measurement
        # The whole number only: not part of a decimal number and not followed by a unit, so that the digits
        # of a measurement ("12345.67 mm³", "123456 voxels") are not taken for the record number.
        return re.compile(rf"(?<![\w.,]){chars}(?!\w|[.,]\d|\s?(?:{_UNIT_AFTER}))")
    if len(chars) < 4:
        return None
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-./_#:]{0,3}".join(re.escape(c) for c in chars) + r"(?![a-z0-9])")


def find_identifiers(text: str, ids: PatientIdentifiers, safe_words: FrozenSet[str] = frozenset(),
                     safe_pairs: FrozenSet[Tuple[str, str]] = frozenset()) -> List[str]:
    """Categories of identifiers found in `text` (empty list: nothing found). Never edits the text.

    `safe_words`: words of the device's own text; `safe_pairs`: two such words in the order the device's
    own text has them ("deep", "white"). Neither is reported as a name.
    """
    if len(text) > MAX_SCANNED_CHARS:
        return ["text_too_long_to_check"]
    norm = normalise(text)
    words = _WORD.findall(norm)
    unique = set(words)
    found: List[str] = []

    # The patient's names (and contact, city, street): alone unless the word is the device's own.
    for category, spellings in (("name", ids.given | ids.family), ("contact_or_address", ids.other_names)):
        for s in spellings:
            if s in safe_words:
                continue
            if s in unique or (len(s) >= 4 and any(s in w for w in unique if w not in safe_words)):
                found.append(category)
                break
    # Given and family name together, in either order, also written as one word — unless the device's own
    # text has exactly those words together (a patient named Deep White and the label "Deep White Matter").
    pairs = {(g, f) for g in ids.given for f in ids.family} | {(f, g) for g in ids.given for f in ids.family}
    joined = {a + b for a, b in pairs}
    if "name" not in found and (any(w in joined and w not in safe_words for w in unique)
                                or any((a, b) in pairs and (a, b) not in safe_pairs
                                       for a, b in zip(words, words[1:]))):
        found.append("name")

    for chars in ids.record_numbers:
        pattern = _record_number_pattern(chars)
        if pattern and pattern.search(norm):
            found.append("record_number")
            break
    if any(p.search(norm) for p in _birth_patterns(ids.birth_date)):
        found.append("birth_date")
    if any(e in norm for e in ids.emails):
        found.append("email")

    # Digit runs are found once. Their ASCII digits, joined by "|" (a phone number cannot span two runs), are
    # searched once per phone, so the time grows with the length of the text only.
    run_texts = [r.group(0) for r in _DIGIT_RUN.finditer(norm)]
    if ids.phones:
        blob = "|".join("".join(_ASCII_DIGITS.findall(run)) for run in run_texts)
        if any(p in blob for p in ids.phones):
            found.append("phone")

    for category, pattern in _GENERIC.items():
        if pattern.search(norm):
            found.append(category)
    for run in run_texts:
        run = run.strip()
        groups = _DIGIT_GROUP.findall(run)
        digits = sum(map(len, groups))
        if digits >= 9 and (len(groups) == 1 or len(groups) >= 3 or run.startswith("0")):
            found.append("long_or_phone_like_number")
            break
    for token in _ALNUM.findall(norm):
        if (len(token) <= 40 and sum(c.isdigit() for c in token) >= 5 and any(c.isalpha() for c in token)
                and not _NUMBER_WITH_UNIT.fullmatch(token)):
            found.append("id_like_number")
            break
    return sorted(set(found))


def assert_no_identifiers(text: str, ids: PatientIdentifiers, safe_words: FrozenSet[str] = frozenset(),
                          safe_pairs: FrozenSet[Tuple[str, str]] = frozenset()) -> None:
    """RC-065: raise IdentifierInPrompt when the tripwire finds anything; the message names categories only."""
    found = find_identifiers(text, ids, safe_words, safe_pairs)
    if found:
        raise IdentifierInPrompt("identifier check failed (" + ", ".join(found) + ")")
