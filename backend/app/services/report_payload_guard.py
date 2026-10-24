"""What the AI report draft may send to the model provider, and the check before it leaves — CAPA-014.

Redesign after the independent review of PR #67 (ISO 14971 §7.1: inherent safety by design first).
Part of the Class C report software item; called only by ``brain_report_service.py``.

RC-064 — structured payload only (inherent safety by design), ``provider_payload``:
    The request is built from the device's measurements (numbers), labels from the device's fixed
    vocabulary (MAGNIMS regions, zone names, volumetry structure names, size classes, abnormality
    types), sex (M or F) and a 5-year age band ("90 or older" from 90). Nothing else is copied:
    no free-text or user-typed field, no unknown field; a label outside the vocabulary becomes
    "[unlisted label]"; a value where a number is expected is dropped unless it is a number.
    The clinician's typed text is merged into the draft by the route, after the model returns.

RC-065 — detection-only tripwire on the final prompt, ``find_identifiers``:
    It never edits text. Before the call it looks — after NFKC normalisation, removal of format
    characters (soft hyphen, zero-width characters, BOM), mapping of look-alike Cyrillic/Greek letters
    and of accents — for the patient's own identifiers read from the patient record (names and names
    written together, German ae/oe/ue spellings; record numbers with any separators; birth date by
    its day, month and year parts in many forms; phone numbers with and without country code and
    trunk 0; e-mail; city; street) and for generic identifier patterns (e-mail, dates with a year,
    phone-like numbers, long or ID-like numbers, titled names). Any finding:
    nothing is sent. Words of the device's own fixed text and vocabulary are never reported on their
    own (a patient named White does not stop "Deep White Matter"); such a name is still found next
    to the other names of the patient. The scanned text is capped and every pattern is linear.

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


FREE_TEXT_FIELDS = ("clinical_indication", "technique", "additional_observations")
UNLISTED = "[unlisted label]"
MAX_SCANNED_CHARS = 400_000

_MEASUREMENT_BLOCKS = ("lesion_analysis", "dis_assessment", "longitudinal", "zone_stats",
                       "segmentation_labels", "anomalies")
_KNOWN_FIELDS = frozenset(FREE_TEXT_FIELDS + _MEASUREMENT_BLOCKS + ("patient_age", "patient_sex"))


# ─────────────────────────────────────────────────────────────────────────────
# RC-064 — the device's fixed label vocabulary and the structured payload
# ─────────────────────────────────────────────────────────────────────────────
_EXTRA_LABELS = ("Unknown", "Lesion", "Background", "small", "medium", "large", "atrophy", "enlargement")
_LABEL_PATTERNS = (re.compile(r"Structure \d{1,4}"), re.compile(r"Label \d{1,3}"))


@lru_cache(maxsize=1)
def label_vocabulary() -> Dict[str, str]:
    """casefolded label -> label, from the services that produce the labels (single source of truth)."""
    from app.services.brain_volumetry_service import STRUCTURE_NAMES
    from app.services.lesion_analysis_service import MAGNIMS_REGIONS
    from app.services.ms_region_classifier import REGION_NAMES
    labels = set(MAGNIMS_REGIONS.values()) | set(REGION_NAMES.values()) | set(STRUCTURE_NAMES.values())
    labels |= set(_EXTRA_LABELS)
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


def _count(value: Any) -> Optional[int]:
    n = _number(value)
    return int(n) if n is not None and n >= 0 else None


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


class _Projector:
    def __init__(self):
        self.counts: Counter = Counter()

    def label(self, value: Any, allowed: Optional[Iterable[str]] = None) -> str:
        label = vocabulary_label(value)
        if label is not None and (allowed is None or label in allowed):
            return label
        self.counts["unlisted_labels"] += 1
        return UNLISTED

    def keyed(self, mapping: Any) -> List[Tuple[str, dict]]:
        """(label, value) pairs of a dict keyed by labels; repeated unlisted keys stay distinct."""
        out, seen = [], set()
        for key, value in (mapping.items() if isinstance(mapping, dict) else ()):
            if not isinstance(value, dict):
                continue
            label = self.label(key)
            if label in seen:
                label = f"{label} ({len(seen) + 1})"
            seen.add(label)
            out.append((label, value))
        return out

    @staticmethod
    def put(target: dict, key: str, value: Any) -> None:
        if value is not None:
            target[key] = value

    def lesion_analysis(self, la: dict) -> dict:
        o: dict = {}
        self.put(o, "total_count", _count(la.get("total_count")))
        self.put(o, "total_burden_mm3", _number(la.get("total_burden_mm3")))
        self.put(o, "total_burden_ml", _number(la.get("total_burden_ml")))
        regions = {}
        for label, info in self.keyed(la.get("regions")):
            r: dict = {}
            self.put(r, "lesion_count", _count(info.get("lesion_count")))
            self.put(r, "total_volume_mm3", _number(info.get("total_volume_mm3")))
            self.put(r, "total_volume_ml", _number(info.get("total_volume_ml")))
            regions[label] = r
        if regions:
            o["regions"] = regions
        sd = la.get("size_distribution")
        if isinstance(sd, dict):
            o["size_distribution"] = {k: v for k in ("small", "medium", "large")
                                      if (v := _count(sd.get(k))) is not None}
        lesions = []
        for i, les in enumerate(la.get("lesions") or []):
            if not isinstance(les, dict):
                continue
            item: dict = {"id": _count(les.get("id")) or i + 1}
            item["region"] = self.label(les.get("region"))
            self.put(item, "volume_mm3", _number(les.get("volume_mm3")))
            self.put(item, "volume_ml", _number(les.get("volume_ml")))
            item["size_category"] = self.label(les.get("size_category"), ("small", "medium", "large"))
            ctr = les.get("centroid")
            if isinstance(ctr, dict):
                item["centroid"] = {k: v for k in ("z", "y", "x") if (v := _number(ctr.get(k))) is not None}
            lesions.append(item)
        if lesions:
            o["lesions"] = lesions
        return o

    def dis_assessment(self, dis: dict) -> dict:
        o: dict = {"dis_met": dis.get("dis_met") is True}
        self.put(o, "regions_with_lesions", _count(dis.get("regions_with_lesions")))
        self.put(o, "total_dis_regions", _count(dis.get("total_dis_regions")))
        details = {label: {"present": info.get("present") is True} for label, info in self.keyed(dis.get("region_details"))}
        if details:
            o["region_details"] = details
        o["has_active_lesions"] = dis.get("has_active_lesions") is True
        self.put(o, "active_voxels", _count(dis.get("active_voxels")))
        o["has_black_holes"] = dis.get("has_black_holes") is True
        self.put(o, "black_hole_voxels", _count(dis.get("black_hole_voxels")))
        return o

    def longitudinal(self, lng: dict) -> dict:
        if lng.get("abstained") is True:
            return {"abstained": True}
        o: dict = {}
        for key in ("burden_tp1_ml", "burden_tp2_ml", "burden_delta_percent"):
            self.put(o, key, _number(lng.get(key)))
        for key in ("total_lesions_tp1", "total_lesions_tp2"):
            self.put(o, key, _count(lng.get(key)))
        sc = lng.get("status_counts")
        if isinstance(sc, dict):
            o["status_counts"] = {k: v for k in ("new", "enlarged", "resolved", "shrunk", "stable")
                                  if (v := _count(sc.get(k))) is not None}
        return o or {"status_counts": {}}

    def zone_stats(self, zs: dict) -> dict:
        o: dict = {}
        self.put(o, "total_brain_voxels", _count(zs.get("total_brain_voxels")))
        zones = {}
        for label, info in self.keyed(zs.get("zones")):
            z: dict = {}
            self.put(z, "voxel_count", _count(info.get("voxel_count")))
            self.put(z, "percentage", _number(info.get("percentage")))
            zones[label] = z
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
            conf = _number(a.get("confidence"))
            if conf is not None and 0 <= conf <= 1:
                item["confidence"] = conf
            self.put(item, "volume_mm3", _number(a.get("volume_mm3")))
            out.append(item)
        return out

    def volumetry(self, vol: dict) -> dict:
        o: dict = {}
        self.put(o, "total_brain_volume_ml", _number(vol.get("total_brain_volume_ml")))
        self.put(o, "intracranial_volume_ml", _number(vol.get("intracranial_volume_ml")))
        structures = []
        for s in vol.get("structures") or []:
            if not isinstance(s, dict) or _number(s.get("volume_ml")) is None:
                continue
            item = {"structure_name": self.label(s.get("structure_name")), "volume_ml": _number(s.get("volume_ml")),
                    "is_abnormal": s.get("is_abnormal") is True}
            pct = _number(s.get("normative_percentile"))
            if pct is not None:
                item["normative_percentile"] = pct
            if s.get("abnormality_type"):
                item["abnormality_type"] = self.label(s.get("abnormality_type"), ("atrophy", "enlargement"))
            structures.append(item)
        o["structures"] = structures
        return o


def provider_payload(findings: Optional[Dict[str, Any]], volumetry: Optional[Dict[str, Any]]) -> ProviderPayload:
    """RC-064: the structured payload the provider may receive. The inputs are not modified."""
    f = findings if isinstance(findings, dict) else {}
    p = _Projector()
    p.counts["free_text_fields"] = sum(1 for k in FREE_TEXT_FIELDS if f.get(k))
    p.counts["unknown_fields"] = sum(1 for k in f if k not in _KNOWN_FIELDS)
    out: Dict[str, Any] = {}
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
    return ProviderPayload(findings=out, volumetry=vol, withheld={k: v for k, v in sorted(p.counts.items())})


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
    record_numbers: Tuple[str, ...]     # alphanumeric characters of MRN / insurance number
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
        numbers = tuple(n for n in (_alnum(normalise(_text(_field(record, k))))
                                    for k in ("mrn", "insurance_policy_number")) if n)
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
        return cls(given=spell(given, middle), family=spell(family), other_names=others, record_numbers=numbers,
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


def _record_number_pattern(chars: str) -> Optional["re.Pattern[str]"]:
    if len(chars) < 4 or (chars.isdigit() and len(chars) < 6):
        return None     # a short all-digit number cannot be told from a measurement
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-./_#:]{0,3}".join(re.escape(c) for c in chars) + r"(?![a-z0-9])")


def find_identifiers(text: str, ids: PatientIdentifiers, safe_words: FrozenSet[str] = frozenset()) -> List[str]:
    """Categories of identifiers found in `text` (empty list: nothing found). Never edits the text."""
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
    # Given and family name together, in either order, also written as one word.
    pairs = {(g, f) for g in ids.given for f in ids.family} | {(f, g) for g in ids.given for f in ids.family}
    joined = {a + b for a, b in pairs}
    if "name" not in found and (any(w in joined for w in unique)
                                or any((a, b) in pairs for a, b in zip(words, words[1:]))):
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

    runs = [_digits(r.group(0)) for r in _DIGIT_RUN.finditer(norm)]
    if ids.phones and any(p in digits for digits in runs for p in ids.phones):
        found.append("phone")

    for category, pattern in _GENERIC.items():
        if pattern.search(norm):
            found.append(category)
    for r in _DIGIT_RUN.finditer(norm):
        run = r.group(0).strip()
        groups = re.findall(r"\d+", run)
        digits = sum(len(g) for g in groups)
        if digits >= 9 and (len(groups) == 1 or len(groups) >= 3 or run.startswith("0")):
            found.append("long_or_phone_like_number")
            break
    for token in _ALNUM.findall(norm):
        if (len(token) <= 40 and sum(c.isdigit() for c in token) >= 5 and any(c.isalpha() for c in token)
                and not _NUMBER_WITH_UNIT.fullmatch(token)):
            found.append("id_like_number")
            break
    return sorted(set(found))


def assert_no_identifiers(text: str, ids: PatientIdentifiers, safe_words: FrozenSet[str] = frozenset()) -> None:
    """RC-065: raise IdentifierInPrompt when the tripwire finds anything; the message names categories only."""
    found = find_identifiers(text, ids, safe_words)
    if found:
        raise IdentifierInPrompt("identifier check failed (" + ", ".join(found) + ")")
