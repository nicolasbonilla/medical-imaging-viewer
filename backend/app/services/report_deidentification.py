"""De-identification of everything the AI report draft sends to the model provider — CAPA-014.

Risk controls RC-064 (removal), RC-065 (fail closed) and RC-066 (records) for HAZ-016;
REQ-SEC-021, REQ-SEC-022, REQ-SEC-023. Part of the Class C report software item: it is called only
by ``brain_report_service.py`` (Class C), immediately before the prompt is built, and the service
refuses to call the provider without it.

WHAT IS REMOVED (from every string of the findings and the volumetry: values and dictionary keys)
1. The patient's own identifiers, read from the patient record the server holds — never from the
   request: given, middle and family names (each name and each whole name, case- and
   accent-insensitive, German ae/oe/ue spellings included; particles such as "de", "la", "von"
   are not removed on their own), the emergency contact's name, the record number (MRN) and the
   insurance policy number (separators optional), phone numbers, address lines, city, postal code,
   and the birth date in any written form.
2. By pattern: e-mail addresses; phone numbers; numbers introduced by an identifier word (MRN,
   accession, DNI, CC, Fallnummer ...); any other number of 6 or more digits (unless followed by a
   measurement unit); dates — the birth date becomes "[birth date removed]", any other exact date
   becomes an interval to the first date met ("[date 2 = date 1 + 11 months]"), a day and month
   without year becomes "[date removed]"; person names after a title (Dr., Prof., Herr, Sra. ...);
   institution names around Hospital / Klinikum / Clínica / Instituto ...; street addresses.
3. The age field becomes a 5-year band ("45-49", "15-17" and "18-19" around the age of majority,
   "90 or older"); the patient's own age in the text ("48-year-old") and any explicit age phrase
   become the band. No drafting rule needs the exact age: the templates use age only to qualify
   atrophy and burden, and volumetry percentiles are computed by the device, not by the model.

WHAT STILL REACHES THE PROVIDER (recorded in CAPA-014 §6 for the data-processing agreement)
The measurements (lesion counts, volumes, regions, voxel positions, DIS items, longitudinal and
volumetry figures), sex, the 5-year age band, the template and language, and the clinician's text
after the removal above. The text can still carry indirect identifiers the rules cannot recognise
(other people's names without a title, institution names without one of the words above, rare
history details, years). The result is pseudonymised health data, not anonymous data.

Numbers are never altered: the prompt builder formats the measurements itself, so only strings pass
through the rules.

@module services.report_deidentification
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Errors — RC-065: nothing may be sent to the model provider
# ─────────────────────────────────────────────────────────────────────────────
class DeidentificationError(Exception):
    """De-identification could not be assured; nothing may be sent to the model provider.

    Messages are fixed texts that name at most a category, never an identifier.
    """


class DeidentificationUnavailable(DeidentificationError):
    """The patient record needed for the removal is missing, unreadable or incomplete."""


class DeidentificationFailed(DeidentificationError):
    """An identifier of the patient remained in the text prepared for the provider."""


# ─────────────────────────────────────────────────────────────────────────────
# Placeholders written in place of what is removed
# ─────────────────────────────────────────────────────────────────────────────
NAME = "[name removed]"
RECORD_NUMBER = "[record number removed]"
BIRTH_DATE = "[birth date removed]"
PHONE = "[phone removed]"
EMAIL = "[e-mail removed]"
ADDRESS = "[address removed]"
ID_NUMBER = "[ID number removed]"
PERSON = "[person name removed]"
INSTITUTION = "[institution removed]"
DATE_REMOVED = "[date removed]"

FREE_TEXT_KEYS = ("clinical_indication", "technique", "additional_observations")

# Words that are part of names but are never removed on their own.
NAME_PARTICLES = frozenset({
    "de", "del", "la", "las", "los", "y", "e", "da", "das", "do", "dos", "di", "du", "van", "von", "der",
    "den", "zu", "le", "el", "al", "bin", "ibn", "st", "san", "santa", "dr", "mr", "mrs", "ms", "jr", "sr",
})


# ─────────────────────────────────────────────────────────────────────────────
# Case- and accent-insensitive matching on a folded copy, mapped back to the original
# ─────────────────────────────────────────────────────────────────────────────
def _fold_char(ch: str) -> str:
    decomposed = unicodedata.normalize("NFKD", ch)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _folded(text: str) -> Tuple[str, List[int]]:
    """The folded text and, for each folded character, the index of its original character."""
    out, origin = [], []
    for i, ch in enumerate(text):
        f = _fold_char(ch)
        out.append(f)
        origin.extend([i] * len(f))
    return "".join(out), origin


def fold(text: str) -> str:
    return _folded(text)[0]


Replacement = Optional[Tuple[str, str]]       # (text written instead, category), or None = keep


def _substitute(text: str, pattern: "re.Pattern[str]", repl: Callable[["re.Match[str]"], Replacement],
                counts: Counter, group: Any = 0, folded: bool = True) -> str:
    """Replace the matches of `pattern` (found on the folded text when `folded`) in the original text."""
    if folded:
        haystack, origin = _folded(text)
    else:
        haystack, origin = text, list(range(len(text)))
    spans = []
    for m in pattern.finditer(haystack):
        if m.end(group) <= m.start(group):
            continue
        r = repl(m)
        if r is not None:
            spans.append((origin[m.start(group)], origin[m.end(group) - 1] + 1, r))
    if not spans:
        return text
    out, last = [], 0
    for start, end, (new, category) in spans:
        if start < last:            # overlapping once mapped back: the first one wins
            continue
        out.append(text[last:start])
        out.append(new)
        counts[category] += 1
        last = end
    out.append(text[last:])
    return "".join(out)


def _fixed(new: str, category: str) -> Callable[["re.Match[str]"], Replacement]:
    return lambda m: (new, category)


# ─────────────────────────────────────────────────────────────────────────────
# Pattern rules (on folded text unless stated)
# ─────────────────────────────────────────────────────────────────────────────
# A number followed by a unit is a measurement, never an identifier.
_UNIT = (r"(?:mm3|mm2|mm|cm3|cm2|cm|ml|μl|ul|l|cc|voxels?|voxeles|vox|%|t|ms|s|mg|g|kg|years?|yrs?|months?|"
         r"weeks?|days?|anos?|meses|mes|semanas?|dias?|jahren?|jahre|monaten?|monate|wochen?|tagen?|tage|"
         r"lesions?|lesiones|lasionen|percentile|th)")
_NOT_A_MEASUREMENT = rf"(?!\s*{_UNIT}(?![a-z0-9]))"
_UNIT_AHEAD = re.compile(rf"\s*{_UNIT}(?![a-z0-9])")
_YEARS_ONLY = re.compile(r"(?:19|20)\d{2}(?:\W+(?:19|20)\d{2})*")

EMAIL_RE = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}")

_ID_WORDS = (
    r"mrn|nhc|hc|historia clinica|historia|medical record(?: number)?|record number|accession(?: number)?|"
    r"acc(?:ession)?\s?no\.?|patient id|patienten-?id|pid|dni|c\.c\.|cc|cedula(?: de ciudadania)?|"
    r"passport|pasaporte|ssn|nhs(?: number)?|svnr|kvnr|versichertennummer|versicherungsnummer|fallnummer|"
    r"fall-?nr\.?|auftragsnummer|policy(?: number)?|poliza|insurance number|case number|numero de caso|"
    r"study id|id"
)
ID_WORD_RE = re.compile(rf"(?<![a-z])(?:{_ID_WORDS})(?![a-z])\s*(?:number|no\.?|nr\.?|n°|nº|#)?\s*[:#]?\s*"
                        rf"(?P<val>[a-z0-9][a-z0-9.\-]{{2,}}[a-z0-9])")
# Tokens of digits and letters joined by "-" or "." (never "/": parameter lists such as 4800/120/1650).
ID_TOKEN_RE = re.compile(r"(?<![\w.\-])[a-z0-9]+(?:[.\-][a-z0-9]+)*(?![\w\-]|\.[a-z0-9])")
# Not inside a longer token ("A-20251012-0042" is an ID, not a phone).
PHONE_RE = re.compile(r"(?<![\w+.\-])\+?\(?\d[\d\s().\-/]{5,20}\d(?![\w])")

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
    "nov": 11, "dec": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "ene": 1, "abr": 4, "ago": 8, "dic": 12,
    "januar": 1, "janner": 1, "februar": 2, "marz": 3, "mai": 5, "juni": 6, "juli": 7,
    "oktober": 10, "dezember": 12, "mrz": 3, "okt": 10, "dez": 12,
}
# Day and month without a year: full month names only, and never "may" (an English verb).
_FULL_MONTHS = ("january", "february", "march", "april", "june", "july", "august", "september", "october",
                "november", "december", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                "septiembre", "setiembre", "octubre", "noviembre", "diciembre", "januar", "janner", "februar",
                "marz", "mai", "juni", "juli", "oktober", "dezember")
_M = "|".join(sorted(_MONTHS, key=len, reverse=True))
_MF = "|".join(sorted(_FULL_MONTHS, key=len, reverse=True))
_Y = r"(?:19|20)\d{2}"
DATE_RE = re.compile(
    r"(?<![0-9a-z])(?:"
    rf"(?P<iy>{_Y})[-/.](?P<im>\d{{1,2}})[-/.](?P<id>\d{{1,2}})"
    rf"|(?P<nd>\d{{1,2}})[./-](?P<nm>\d{{1,2}})[./-](?P<ny>{_Y}|\d{{2}})"
    rf"|(?P<cy>{_Y})(?P<cm>0[1-9]|1[0-2])(?P<cd>0[1-9]|[12]\d|3[01])"
    rf"|(?P<wd>\d{{1,2}})(?:st|nd|rd|th|\.)?\s*(?:de\s+)?(?P<wm>{_M})\.?,?\s*(?:de\s+|del\s+)?(?P<wy>{_Y})"
    rf"|(?P<vm>{_M})\.?\s+(?P<vd>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<vy>{_Y})"
    rf"|(?P<um>{_M})\.?\s*(?:de\s+|del\s+)?(?P<uy>{_Y})"
    rf"|(?P<mm>0?[1-9]|1[0-2])[/.-](?P<my>{_Y})"
    rf"|(?P<xd>\d{{1,2}})(?:st|nd|rd|th|\.)?\s*(?:de\s+|of\s+)?(?P<xm>{_MF})"
    rf"|(?P<ym>{_MF})\s+(?P<yd>\d{{1,2}})(?:st|nd|rd|th)?"
    r")(?![0-9a-z])(?![./\-]\d)" + _NOT_A_MEASUREMENT
)
_BIRTH_WORDS = (r"born|dob|d\.o\.b\.|date of birth|birth ?date|nacid[oa]|fecha de nacimiento|f\. ?nac\.?|"
                r"geboren|geburtsdatum|geb\.")
BIRTH_CONTEXT_RE = re.compile(
    rf"(?<![a-z])(?:{_BIRTH_WORDS})\s*(?:on|in|el|en|am|im|the|:|-)?\s*(?:the\s+)?"
    rf"(?P<when>\d{{1,2}}[./-]\d{{1,2}}[./-](?:{_Y}|\d{{2}})|{_Y}[-/.]\d{{1,2}}[-/.]\d{{1,2}}|"
    rf"\d{{1,2}}(?:st|nd|rd|th|\.)?\s*(?:de\s+)?(?:{_M})\.?,?\s*(?:de\s+)?{_Y}|(?:{_M})\.?\s+\d{{1,2}},?\s+{_Y}|"
    rf"(?:{_M})\.?\s*(?:de\s+)?{_Y}|{_Y})(?![0-9])"
)
_AGE_PHRASE = (r"(?:\s*-\s*|\s+)(?:years?[\s-]+old|year-old|yo\b|y/o|anos de edad|jahre alt|jahrige?[nrms]?\b|"
               r"jahrig)|-jahrige?[nrms]?\b|-jahrig")
AGE_PHRASE_RE = re.compile(rf"(?<![\d.,\-])(?P<age>\d{{1,3}})(?={_AGE_PHRASE})")

# Case-sensitive rules, on the original text.
_CAP = r"[A-ZÁÉÍÓÚÑÄÖÜÇÀÈÌÒÙÂÊÎÔÛ]"
_PROPER = rf"{_CAP}[\w'’\-]*"           # no trailing dot: a sentence end stops the name
_TITLE = (r"(?:Dr|Dra|Drs|Prof|Profa|Herr|Frau|Mr|Mrs|Sr|Sra|Srta|Señor|Señora|Doña|Doctor|Doctora|Professor|"
          r"Profesor|Profesora)")
# A title, more titles or degrees ("Prof. Dr. med."), up to two names or initials, then the surname.
TITLED_PERSON_RE = re.compile(
    rf"\b{_TITLE}\.?(?:\s+(?:{_TITLE}\.?|med\.|rer\.\s*nat\.|h\.\s*c\.|dent\.))*"
    rf"(?:\s+(?:{_CAP}\.|{_PROPER})){{0,2}}\s+{_CAP}[\w'’\-]+"
)
_INSTITUTION_WORDS = (r"Universitätsklinikum|Universitätsspital|Hospital|Hôpital|Clínica|Clinica|Klinikum|Uniklinik|"
                      r"Spital|Krankenhaus|Clinic|Medical Cent(?:er|re)|Centro Médico|Centro Medico|Fundación|"
                      r"Fundacion|Instituto|Institut|Sanatorio")
_CONNECTOR = r"(?:de|del|la|las|los|el|y|der|die|das|des|am|an|im|in|rechts|links|of|the|and|for|und|für|San|Santa|St\.?)"
INSTITUTION_AFTER_RE = re.compile(rf"\b(?:{_INSTITUTION_WORDS})(?:\s+(?:{_CONNECTOR}\s+)*{_PROPER})+")
INSTITUTION_BEFORE_RE = re.compile(rf"(?:\b{_CAP}[\w'’\-]+\s+){{1,3}}(?:{_INSTITUTION_WORDS})\b")
STREET_RE = re.compile(
    r"\b(?:Calle|Cl|Carrera|Cra|Kr|Avenida|Av|Avda|Diagonal|Dg|Transversal|Tv)\.?\s+\d{1,3}\s?[A-Za-z]?"
    r"(?:\s*(?:bis)?\s*(?:#|No\.?|N[°º])\s*\d{1,3}\s?[A-Za-z]?(?:\s*-\s*\d{1,3})?)?"
    r"|\b[A-ZÄÖÜ][a-zäöüß]+(?:straße|strasse|str\.|weg|allee|platz|gasse)\s+\d{1,4}\s?[a-z]?\b"
    r"|\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,3}(?:Street|St\.|Avenue|Ave\.?|Road|Rd\.|Boulevard|Blvd\.?|Lane|Ln\.|"
    r"Drive|Way|Court|Ct\.)"
)
_COLLAPSE = {p: re.compile(re.escape(p) + r"(?:[\s,;\-]+" + re.escape(p) + r")+")
             for p in (NAME, ADDRESS, PERSON, INSTITUTION)}


# ─────────────────────────────────────────────────────────────────────────────
# Dates and ages
# ─────────────────────────────────────────────────────────────────────────────
def _year(raw: str) -> int:
    y = int(raw)
    if len(raw) == 2:
        y += 2000 if y <= date.today().year % 100 else 1900
    return y


def _date_of(m: "re.Match[str]") -> Optional[Tuple[str, date]]:
    """(precision, date) of a DATE_RE match — precision 'day', 'month' or 'noyear' — or None."""
    g = m.groupdict()
    try:
        if g["iy"]:
            return "day", date(int(g["iy"]), int(g["im"]), int(g["id"]))
        if g["nd"]:
            a, b, y = int(g["nd"]), int(g["nm"]), _year(g["ny"])
            day, month = (b, a) if b > 12 >= a else (a, b)     # day first, unless impossible
            return "day", date(y, month, day)
        if g["cy"]:
            return "day", date(int(g["cy"]), int(g["cm"]), int(g["cd"]))
        if g["wd"]:
            return "day", date(int(g["wy"]), _MONTHS[g["wm"]], int(g["wd"]))
        if g["vm"]:
            return "day", date(int(g["vy"]), _MONTHS[g["vm"]], int(g["vd"]))
        if g["um"]:
            return "month", date(int(g["uy"]), _MONTHS[g["um"]], 1)
        if g["mm"]:
            return "month", date(int(g["my"]), int(g["mm"]), 1)
        if g["xd"]:
            return "noyear", date(2000, _MONTHS[g["xm"]], int(g["xd"]))
        if g["ym"]:
            return "noyear", date(2000, _MONTHS[g["ym"]], int(g["yd"]))
    except (ValueError, KeyError):
        return None
    return None


def _is_birth_date(precision: str, d: date, birth: date) -> bool:
    if precision == "day":
        return d == birth
    if precision == "month":
        return (d.year, d.month) == (birth.year, birth.month)
    return (d.month, d.day) == (birth.month, birth.day)


def find_dates(text: str) -> List[Tuple[str, date]]:
    """Every date written in `text`, in any form DATE_RE knows."""
    return [r for r in (_date_of(m) for m in DATE_RE.finditer(fold(text))) if r]


def age_band(value: Any) -> Optional[str]:
    """5-year band of an age in years: '45-49'; '15-17' and '18-19' keep the age of majority;
    '90 or older' (HIPAA Safe Harbor aggregation). None when the value is not an age."""
    try:
        years = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    if years < 0 or years > 130:
        return None
    if years >= 90:
        return "90 or older"
    if 15 <= years <= 17:
        return "15-17"
    if 18 <= years <= 19:
        return "18-19"
    low = years - years % 5
    return f"{low}-{low + 4}"


# ─────────────────────────────────────────────────────────────────────────────
# The patient's own identifiers, from the record the server holds
# ─────────────────────────────────────────────────────────────────────────────
def _field(record: Any, name: str) -> Any:
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value)).strip()


def _name_tokens(*values: str) -> Tuple[str, ...]:
    out = set()
    for v in values:
        for t in re.split(r"[\s\-,.']+", v):
            if len(fold(t)) >= 2 and fold(t) not in NAME_PARTICLES:
                out.add(t)
    return tuple(sorted(out))


@dataclass(frozen=True)
class PatientIdentifiers:
    """What must not leave the server for this patient, read from the patient record."""

    names: Tuple[str, ...]                 # whole names (given, middle, family, full, contact)
    name_tokens: Tuple[str, ...]           # their parts, particles excluded
    given_tokens: Tuple[str, ...]
    family_tokens: Tuple[str, ...]
    record_numbers: Tuple[str, ...]        # MRN, insurance policy number
    birth_date: date
    phones: Tuple[str, ...]                # last 10 digits
    emails: Tuple[str, ...]
    address_parts: Tuple[str, ...]         # address lines, city, postal code
    age_years: Optional[int] = None

    @classmethod
    def from_record(cls, record: Any) -> "PatientIdentifiers":
        """Build from a patient record (PatientResponse or dict). RC-065: a missing record, or one
        without record number, given name, family name or birth date, cannot be used — raises
        DeidentificationUnavailable."""
        if record is None:
            raise DeidentificationUnavailable("The patient's record could not be read")
        mrn = _text(_field(record, "mrn"))
        given = _text(_field(record, "given_name"))
        family = _text(_field(record, "family_name"))
        birth = _field(record, "birth_date")
        if isinstance(birth, str):
            try:
                birth = date.fromisoformat(birth[:10])
            except ValueError:
                birth = None
        elif hasattr(birth, "date") and callable(birth.date):
            birth = birth.date()
        if not (mrn and given and family and isinstance(birth, date)):
            raise DeidentificationUnavailable(
                "The patient's record lacks a field the removal needs (record number, given name, "
                "family name or birth date)")
        middle = _text(_field(record, "middle_name"))
        contact = _text(_field(record, "emergency_contact_name"))
        full = _text(_field(record, "full_name"))
        names = tuple(sorted({n for n in (given, middle, family, full, contact,
                                          " ".join(x for x in (given, middle, family) if x)) if n}))
        phones = []
        for key in ("phone_mobile", "phone_home", "phone_work", "emergency_contact_phone"):
            digits = re.sub(r"\D", "", _text(_field(record, key)))
            if len(digits) >= 7:
                phones.append(digits[-10:])
        emails = tuple(e for e in (_text(_field(record, "email")),) if "@" in e)
        address = tuple(a for a in (_text(_field(record, k)) for k in
                                    ("address_line1", "address_line2", "city", "postal_code")) if a)
        numbers = tuple(n for n in (mrn, _text(_field(record, "insurance_policy_number"))) if n)
        age = _field(record, "age")
        if not isinstance(age, int) or isinstance(age, bool):
            today = date.today()
            age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        return cls(names=names, name_tokens=_name_tokens(given, middle, family, contact),
                   given_tokens=_name_tokens(given, middle), family_tokens=_name_tokens(family),
                   record_numbers=numbers, birth_date=birth, phones=tuple(phones), emails=emails,
                   address_parts=address, age_years=age)


def _sequence(value: str, max_gap: int = 3) -> Optional[str]:
    """Regex (folded) for a multi-word value with flexible separators between its words."""
    parts = re.findall(r"[^\W_]+", fold(value))
    if not parts or (len(parts) == 1 and len(parts[0]) < 3):
        return None
    return (r"[\W_]{1,%d}" % max_gap).join(re.escape(p) for p in parts)


def _spelling_variants(word: str) -> List[str]:
    """Folded spellings of a name part: as written, with ä/ö/ü/ß spelt ae/oe/ue/ss, and the reverse."""
    low = word.lower()
    variants = {fold(low),
                fold(low.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")),
                fold(low).replace("ae", "a").replace("oe", "o").replace("ue", "u")}
    return sorted(v for v in variants if v)


def _tolerant(value: str, min_digits_if_numeric: int = 4) -> Optional[str]:
    """Regex (folded) for an identifier whose separators are optional ('MRN-2025-0042' = 'mrn 2025 0042').
    No '.' between characters, so that it never matches inside a decimal number."""
    chars = [c for c in fold(value) if c.isalnum()]
    if len(chars) < 4 or (all(c.isdigit() for c in chars) and len(chars) < min_digits_if_numeric):
        return None
    return r"[\s\-/_#:]{0,2}".join(re.escape(c) for c in chars)


@dataclass
class _Compiled:
    names: Optional["re.Pattern[str]"]
    record_numbers: Optional["re.Pattern[str]"]
    phones: Optional["re.Pattern[str]"]
    address: Optional["re.Pattern[str]"]
    age: Optional["re.Pattern[str]"]
    residual_name: Optional["re.Pattern[str]"]
    residual_record_numbers: Optional["re.Pattern[str]"]


def _either(alternatives: List[str], before: str, after: str) -> Optional["re.Pattern[str]"]:
    alternatives = sorted(set(a for a in alternatives if a), key=len, reverse=True)
    return re.compile(before + "(?:" + "|".join(alternatives) + ")" + after) if alternatives else None


def _compile(ids: PatientIdentifiers) -> _Compiled:
    names = [_sequence(n) for n in ids.names]
    names += [re.escape(v) for t in ids.name_tokens for v in _spelling_variants(t)]
    numbers = [_tolerant(n) for n in ids.record_numbers]
    # The residual check runs on the final prompt, which also holds the formatted measurements: only
    # record numbers that cannot be mistaken for a measurement (a letter, or at least 6 digits).
    strict_numbers = [_tolerant(n, 6) for n in ids.record_numbers]
    phones = [r"[\s\-./()]{0,2}".join(re.escape(c) for c in p) for p in ids.phones]
    address = [re.escape(fold(a)) if re.fullmatch(r"\d{4,}", fold(a)) else _sequence(a) for a in ids.address_parts]
    pairs = []
    for g in ids.given_tokens:
        for f in ids.family_tokens:
            for gv in _spelling_variants(g):
                for fv in _spelling_variants(f):
                    pairs += [rf"{re.escape(gv)}[\W_]{{1,3}}{re.escape(fv)}", rf"{re.escape(fv)}[\W_]{{1,3}}{re.escape(gv)}"]
    age = None
    if ids.age_years is not None:
        age = re.compile(rf"(?<![\d.,\-])(?P<age>{ids.age_years})(?=\s*-?\s*(?:years?|yrs?\b|anos?\b|jahre?n?\b|j\.))")
    return _Compiled(
        names=_either(names, r"(?<!\w)", r"(?!\w)"),
        record_numbers=_either(numbers, r"(?<![a-z0-9.,])", r"(?![a-z0-9]|[.,]\d)" + _NOT_A_MEASUREMENT),
        phones=_either(phones, r"(?:\+\d{1,3}[\s\-.]*)?\(?(?:0\)?[\s\-.]*)?", r"(?!\d)"),
        address=_either(address, r"(?<!\w)", r"(?!\w)"),
        age=age,
        residual_name=_either(pairs, r"(?<!\w)", r"(?!\w)"),
        residual_record_numbers=_either(strict_numbers, r"(?<![a-z0-9.,])", r"(?![a-z0-9]|[.,]\d)"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# The single de-identification step — RC-064
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class DeidentifiedInput:
    findings: Dict[str, Any]
    volumetry: Optional[Dict[str, Any]]
    redactions: Dict[str, int] = field(default_factory=dict)


class _Scrubber:
    def __init__(self, ids: PatientIdentifiers):
        self.ids = ids
        self.c = _compile(ids)
        self.counts: Counter = Counter()
        self.dates: List[Tuple[str, date]] = []       # in order of first appearance; [0] is "date 1"

    # -- dates and ages ---------------------------------------------------------
    def _date_label(self, precision: str, d: date) -> str:
        key = (precision, d)
        if key not in self.dates:
            self.dates.append(key)
        index = self.dates.index(key) + 1
        if index == 1:
            return "[date 1]"
        ref_precision, ref = self.dates[0]
        if "month" in (precision, ref_precision):
            months = (d.year - ref.year) * 12 + (d.month - ref.month)
            sign, amount, unit = ("+" if months >= 0 else "-"), abs(months), "months"
        else:
            days = (d - ref).days
            sign = "+" if days >= 0 else "-"
            amount, unit = (abs(days), "days") if abs(days) < 61 else (round(abs(days) / 30.4375), "months")
        return f"[date {index} = date 1 {sign} {amount} {unit}]"

    def _date(self, m: "re.Match[str]") -> Replacement:
        parsed = _date_of(m)
        if parsed is None:
            return None
        precision, d = parsed
        if _is_birth_date(precision, d, self.ids.birth_date):
            return BIRTH_DATE, "birth_date"
        if precision == "noyear":
            return DATE_REMOVED, "date"
        return self._date_label(precision, d), "date"

    @staticmethod
    def _age(m: "re.Match[str]") -> Replacement:
        band = age_band(m.group("age"))
        return (band, "age") if band else None

    # -- numbers ----------------------------------------------------------------
    @staticmethod
    def _id_token(m: "re.Match[str]") -> Replacement:
        token = m.group(0)
        if sum(ch.isdigit() for ch in token) < 6 or _UNIT_AHEAD.match(m.string, m.end()):
            return None                        # short, or a measurement
        whole = DATE_RE.fullmatch(token)
        if whole is not None and _date_of(whole) is not None:
            return None                        # a date: the date rule turns it into an interval
        if _YEARS_ONLY.fullmatch(token):
            return None                        # a year range ("2019-2021"): clinical history
        return ID_NUMBER, "id_number"

    @staticmethod
    def _id_word(m: "re.Match[str]") -> Replacement:
        value = m.group("val")
        if sum(ch.isdigit() for ch in value) < 2 or _UNIT_AHEAD.match(m.string, m.end("val")):
            return None
        return ID_NUMBER, "id_number"

    @staticmethod
    def _phone(m: "re.Match[str]") -> Replacement:
        s = m.group(0)
        groups = re.findall(r"\d+", s)
        digits = sum(len(g) for g in groups)
        if not 7 <= digits <= 15 or len(groups) < 2 or _UNIT_AHEAD.match(m.string, m.end()):
            return None
        if DATE_RE.search(s):
            return None                        # a date: the date rule turns it into an interval
        if _YEARS_ONLY.fullmatch(s.strip()):
            return None                        # a list of years: clinical history
        if set(re.sub(r"[\d()+\s]", "", s)) == {"/"} and not s.startswith("0"):
            return None                        # a parameter list (4800/120/1650), not a phone
        if len(groups) == 2 and "." in s:
            return None                        # a decimal number
        plausible = (s.startswith("+") or "(" in s
                     or (len(groups) >= 3 and sum(len(g) >= 3 for g in groups) >= 2)
                     or (len(groups) == 2 and digits >= 9)
                     or (s.startswith("0") and max(len(g) for g in groups) >= 4))
        return (PHONE, "phone") if plausible else None

    # -- one string -------------------------------------------------------------
    def text(self, s: str) -> str:
        c, n = self.c, self.counts
        s = _substitute(s, EMAIL_RE, _fixed(EMAIL, "email"), n)
        if c.record_numbers:
            s = _substitute(s, c.record_numbers, _fixed(RECORD_NUMBER, "record_number"), n)
        if c.phones:
            s = _substitute(s, c.phones, _fixed(PHONE, "phone"), n)
        if c.address:
            s = _substitute(s, c.address, _fixed(ADDRESS, "address"), n)
        s = _substitute(s, ID_WORD_RE, self._id_word, n, group="val")
        s = _substitute(s, PHONE_RE, self._phone, n)
        s = _substitute(s, ID_TOKEN_RE, self._id_token, n)
        s = _substitute(s, BIRTH_CONTEXT_RE, _fixed(BIRTH_DATE, "birth_date"), n, group="when")
        s = _substitute(s, DATE_RE, self._date, n)
        if c.age:
            s = _substitute(s, c.age, self._age, n, group="age")
        s = _substitute(s, AGE_PHRASE_RE, self._age, n, group="age")
        if c.names:
            s = _substitute(s, c.names, _fixed(NAME, "name"), n)
        s = _substitute(s, TITLED_PERSON_RE, _fixed(PERSON, "person_name"), n, folded=False)
        s = _substitute(s, INSTITUTION_AFTER_RE, _fixed(INSTITUTION, "institution"), n, folded=False)
        s = _substitute(s, INSTITUTION_BEFORE_RE, _fixed(INSTITUTION, "institution"), n, folded=False)
        s = _substitute(s, STREET_RE, _fixed(ADDRESS, "address"), n, folded=False)
        for placeholder, pattern in _COLLAPSE.items():
            s = pattern.sub(placeholder, s)
        return s

    # -- any JSON-like value ----------------------------------------------------
    def value(self, v: Any) -> Any:
        if isinstance(v, str):
            return self.text(v)
        if isinstance(v, dict):
            return {self.text(k) if isinstance(k, str) else k: self.value(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [self.value(x) for x in v]
        return v


def deidentify_report_input(findings: Optional[Dict[str, Any]], volumetry: Optional[Dict[str, Any]],
                            identifiers: PatientIdentifiers) -> DeidentifiedInput:
    """RC-064: the findings and volumetry with every identifier removed, and the number of items
    removed per category (for the log, RC-066). The inputs are not modified."""
    if not isinstance(identifiers, PatientIdentifiers):
        raise DeidentificationUnavailable("No patient identifiers were supplied for the removal")
    scrub = _Scrubber(identifiers)
    findings = dict(findings or {})
    cleaned: Dict[Any, Tuple[Any, Any]] = {}
    # Free text first, so that the first date the clinician wrote is "date 1".
    for key in [k for k in FREE_TEXT_KEYS if k in findings] + [k for k in findings if k not in FREE_TEXT_KEYS]:
        value = findings[key]
        if key == "patient_age":
            band = age_band(value)
            scrub.counts["age"] += 1
            if band is not None:
                cleaned[key] = (key, band)
            continue
        cleaned[key] = (scrub.text(key) if isinstance(key, str) else key, scrub.value(value))
    ordered = dict(cleaned[k] for k in findings if k in cleaned)      # original key order
    clean_volumetry = scrub.value(volumetry) if volumetry is not None else None
    return DeidentifiedInput(findings=ordered, volumetry=clean_volumetry,
                             redactions={k: v for k, v in sorted(scrub.counts.items()) if v})


# ─────────────────────────────────────────────────────────────────────────────
# Residual check on the final prompt — RC-065 (defence in depth)
# ─────────────────────────────────────────────────────────────────────────────
def residual_identifier_categories(text: str, identifiers: PatientIdentifiers) -> List[str]:
    """Categories of the patient's own identifiers still present in `text` (empty when none)."""
    c = _compile(identifiers)
    folded = fold(text)
    found = []
    if c.residual_name and c.residual_name.search(folded):
        found.append("name")
    if c.residual_record_numbers and c.residual_record_numbers.search(folded):
        found.append("record_number")
    if any(_is_birth_date(p, d, identifiers.birth_date) for p, d in find_dates(text) if p != "noyear"):
        found.append("birth_date")
    if any(fold(e) in folded for e in identifiers.emails):
        found.append("email")
    if c.phones and c.phones.search(folded):
        found.append("phone")
    return found


def assert_no_residual_identifiers(text: str, identifiers: PatientIdentifiers) -> None:
    """RC-065: raise DeidentificationFailed when the patient's own identifiers remain in `text`."""
    found = residual_identifier_categories(text, identifiers)
    if found:
        raise DeidentificationFailed(
            "An identifier of the patient (" + ", ".join(found) + ") remained in the text prepared for the "
            "AI provider; nothing was sent")
