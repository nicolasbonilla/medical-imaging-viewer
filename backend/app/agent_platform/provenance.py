"""
AI-text provenance: every unit of text a model wrote is marked, for the signed report and the UI.

REQ-AGT-006; risk control RC-119; hazard HAZ-024 (text written by a model is not told apart from text
computed by the software or written by the clinician, so a reader trusts or signs it as their own).
DRAFT, PENDING owner approval. Serves the AI Act Art. 50 machine-readable marking and the CHAI
"AI-added data points clearly marked" practice.

A report is a sequence of ``Segment`` s — a heading, a sentence, a list item or a table row — each with its
author (``software``, ``model`` or ``clinician``), the exact model id, agent id and trace id for a model
segment, and the SHA-256 of its text. Concatenating the segments gives the report text back exactly
(``verify_document``), so the record and the signed text cannot drift apart unnoticed.

Rules:
- Everything a model returned is ``model``, headings included: a heading can carry a claim, and marking
  too much is safe where marking too little is the hazard.
- ``reconcile`` maps a clinician's edited text onto the record: a unit kept word for word keeps its author;
  a changed unit becomes ``clinician`` with ``edited_from_model`` set; a new unit is ``clinician``.
- ``render_text`` (signed report) puts ``TEXT_MARK`` before each model unit and ends with a legend that
  names the model; ``render_html`` (UI) wraps each unit in a span with ``data-author`` / ``data-model``
  and escapes every character of the text.

@module agent_platform.provenance
"""

from __future__ import annotations

import difflib
import html
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.agent_platform.hashing import sha256_text as _sha

SCHEMA = "mstool.ai-provenance/1"
AUTHORS = ("software", "model", "clinician")
TEXT_MARK = "[AI]"
TEXT_MARK_EDITED = "[AI, edited]"       # a unit the model wrote and the clinician then changed

# Words after which a full stop does not end a sentence (English, Spanish, German report language).
ABBREVIATIONS = frozenset({
    "e.g.", "i.e.", "approx.", "aprox.", "ca.", "cf.", "vs.", "etc.", "dr.", "dra.", "drs.", "prof.", "fig.", "figs.",
    "no.", "nr.", "núm.", "sr.", "sra.", "st.", "max.", "min.", "bzw.", "ggf.", "evtl.", "vgl.", "usw.", "inkl.",
    "zzgl.", "sog.", "resp.", "incl.", "ref.", "vol.", "pág.", "p.ej.", "z.b.", "u.a.", "d.h.",
})
ABBREVIATION_PAIRS = (("z.", "b."), ("p.", "ej."), ("u.", "a."), ("d.", "h."))

_HEADING = re.compile(r"\s*(#{1,6}\s|\*\*[^*]{1,80}\*\*\s*:?\s*$)")
_LIST = re.compile(r"\s*([-*+]\s+|\d{1,3}[.)]\s+)")
_TABLE = re.compile(r"\s*\|")
_SENT_SPLIT = re.compile(r"(?<=[.!?;])(\s+)(?=\S)")
_PREFIX = re.compile(r"^(\s*(?:#{1,6}\s+|[-*+]\s+|\d{1,3}[.)]\s+|\|\s*)?)")


@dataclass(frozen=True)
class Segment:
    kind: str                      # heading | sentence | list_item | table_row | blank
    text: str                      # the unit itself
    trailing: str                  # the whitespace that follows it (kept so the text round-trips)
    author: str
    sha256: str
    agent_id: Optional[str] = None
    model_id: Optional[str] = None
    trace_id: Optional[str] = None
    verifier: Optional[str] = None
    edited_from_model: bool = False


@dataclass(frozen=True)
class ProvenanceDocument:
    segments: Tuple[Segment, ...]
    schema: str = SCHEMA

    def text(self) -> str:
        return "".join(s.text + s.trailing for s in self.segments)

    def model_segments(self) -> List[Segment]:
        return [s for s in self.segments if s.author == "model"]

    def to_dict(self) -> Dict[str, Any]:
        return {"schema": self.schema, "segments": [asdict(s) for s in self.segments]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProvenanceDocument":
        if data.get("schema") != SCHEMA:
            raise ValueError("unknown provenance schema")
        segments = tuple(Segment(**s) for s in data["segments"])
        for s in segments:                                  # third review of PR #79, finding 7
            if not segment_is_valid(s):
                raise ValueError("a provenance segment is not valid (author, kind, text or hash)")
        return cls(segments)


KINDS = frozenset({"heading", "sentence", "list_item", "table_row", "blank"})


def segment_is_valid(s: Segment) -> bool:
    """Every field of a unit has its type and an allowed value; its hash binds its text."""
    optional = (s.agent_id, s.model_id, s.trace_id, s.verifier)
    return (s.author in AUTHORS and s.kind in KINDS and isinstance(s.text, str) and isinstance(s.trailing, str)
            and isinstance(s.sha256, str) and s.sha256 == _sha(s.text) and isinstance(s.edited_from_model, bool)
            and all(v is None or isinstance(v, str) for v in optional) and not s.trailing.strip())


def split_units(text: str) -> List[Tuple[str, str, str]]:
    """(kind, unit, trailing whitespace) for every heading, sentence, list item and table row; blank lines
    are carried as trailing whitespace (or as one leading ``blank`` unit). ''.join(unit + trailing) == text."""
    units: List[List[str]] = []
    for line in (text or "").splitlines(keepends=True):
        content = line.rstrip("\r\n")
        eol = line[len(content):]
        if not content.strip():
            if units:
                units[-1][2] += line
            else:
                units.append(["blank", "", line])
            continue
        if _HEADING.match(content):
            units.append(["heading", content, eol])
            continue
        if _TABLE.match(content):
            units.append(["table_row", content, eol])
            continue
        marker = _LIST.match(content)
        first_kind = "list_item" if marker else "sentence"
        head = content[:marker.end()] if marker else ""
        sentences = split_sentences(content[len(head):])
        sentences[0][0] = head + sentences[0][0]             # the list marker stays on its item
        for k, (body, ws) in enumerate(sentences):
            units.append([first_kind if k == 0 else "sentence", body, ws])
        units[-1][2] += eol
    return [tuple(u) for u in units]


def _no_split_after(before: str, after: str) -> bool:
    """True when the punctuation that ends ``before`` belongs to an abbreviation, not to a sentence end."""
    low = before.lower()
    word = low.rsplit(None, 1)[-1] if low.split() else low
    if word in ABBREVIATIONS:
        return True
    for first, second in ABBREVIATION_PAIRS:            # "z. B.", "p. ej.", "u. a.", "d. h."
        if word == first and after.lower().startswith(second):
            return True
        if word == second and low.endswith(first + " " + second):
            return True
    return False


def split_sentences(text: str) -> List[List[str]]:
    """[[sentence, trailing whitespace], ...] — split after . ! ? ; followed by whitespace, except after a
    defined abbreviation (second review of PR #79, finding 2). ''.join(s + ws) == text."""
    out: List[List[str]] = []
    start = 0
    for m in _SENT_SPLIT.finditer(text):
        if _no_split_after(text[start:m.start()], text[m.end():]):
            continue
        out.append([text[start:m.start()], m.group(1)])
        start = m.end()
    out.append([text[start:], ""])
    return out


def compose(parts: Sequence[Tuple[str, str, Mapping[str, Any]]]) -> ProvenanceDocument:
    """A document from (author, text, metadata) parts in order; the metadata of a model part names its
    agent_id, model_id, trace_id and verifier."""
    segments: List[Segment] = []
    for author, text, meta in parts:
        if author not in AUTHORS:
            raise ValueError(f"unknown author {author!r}")
        for kind, unit, trailing in split_units(text):
            is_model = author == "model" and kind != "blank"
            segments.append(Segment(
                kind=kind, text=unit, trailing=trailing, author=author if kind != "blank" else "software",
                sha256=_sha(unit), agent_id=meta.get("agent_id") if is_model else None,
                model_id=meta.get("model_id") if is_model else None,
                trace_id=meta.get("trace_id") if is_model else None,
                verifier=meta.get("verifier") if is_model else None))
    return ProvenanceDocument(tuple(segments))


def mark_model_text(text: str, *, agent_id: str, model_id: str, trace_id: Optional[str],
                    verifier: Optional[str]) -> ProvenanceDocument:
    """Mark every unit of a model's text as written by that model (RC-119)."""
    return compose([("model", text, {"agent_id": agent_id, "model_id": model_id, "trace_id": trace_id,
                                      "verifier": verifier})])


def verify_document(doc: ProvenanceDocument, text: str) -> bool:
    """The record is the text: same characters, and every unit's hash matches."""
    return doc.text() == text and all(segment_is_valid(s) for s in doc.segments)


def reconcile(original: ProvenanceDocument, edited_text: str) -> ProvenanceDocument:
    """Carry authorship onto the clinician's edited text: unchanged units keep it, changed ones become the
    clinician's (``edited_from_model`` when they replaced model text), new ones are the clinician's."""
    old = list(original.segments)
    new_units = split_units(edited_text)
    old_keys = [s.text.strip() for s in old]
    new_keys = [u[1].strip() for u in new_units]
    out: List[Optional[Segment]] = [None] * len(new_units)
    matcher = difflib.SequenceMatcher(None, old_keys, new_keys, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        replaced_model = any(s.author == "model" for s in old[i1:i2])
        for offset, j in enumerate(range(j1, j2)):
            kind, unit, trailing = new_units[j]
            if tag == "equal":
                base = old[i1 + offset]
                out[j] = replace(base, kind=kind, text=unit, trailing=trailing, sha256=_sha(unit))
            elif kind == "blank" or not unit.strip():
                out[j] = Segment(kind=kind, text=unit, trailing=trailing, author="software", sha256=_sha(unit))
            else:
                out[j] = Segment(kind=kind, text=unit, trailing=trailing, author="clinician", sha256=_sha(unit),
                                 edited_from_model=(tag == "replace" and replaced_model))
    return ProvenanceDocument(tuple(out))


def _legend(doc: ProvenanceDocument) -> str:
    models = sorted({s.model_id for s in doc.model_segments() if s.model_id})
    agents = sorted({s.agent_id for s in doc.model_segments() if s.agent_id})
    verifiers = sorted({s.verifier for s in doc.model_segments() if s.verifier})
    edited = any(s.edited_from_model for s in doc.segments)
    edited_note = (f" Units tagged {TEXT_MARK_EDITED} were written by an AI model and then changed by the clinician."
                   if edited else "")
    if not models:
        if edited:
            return "Legend: no unit is as the AI model wrote it." + edited_note
        return "Legend: no part of this text was written by an AI model."
    checked = f", checked by {', '.join(verifiers)}" if verifiers else ", not checked by a verifier"
    return (f"Legend: the tagged units were written by AI model {', '.join(models)} (agent {', '.join(agents)})"
            f"{checked}; every other unit was computed by the software or written by the clinician.{edited_note}")


def _marked(unit: str, mark: str) -> str:
    m = _PREFIX.match(unit)
    cut = m.end() if m else 0
    return unit[:cut] + mark + " " + unit[cut:]


def render_text(doc: ProvenanceDocument) -> str:
    """Plain text for the signed report: TEXT_MARK before each model unit, TEXT_MARK_EDITED before each unit the
    clinician changed from model text (second review of PR #79, finding 7), then the legend."""
    out = []
    for s in doc.segments:
        unit = s.text
        if s.author == "model" and unit.strip():
            unit = _marked(unit, TEXT_MARK)
        elif s.edited_from_model and unit.strip():
            unit = _marked(unit, TEXT_MARK_EDITED)
        out.append(unit + s.trailing)
    body = "".join(out).rstrip("\n")
    return body + "\n\n" + _legend(doc)


def render_html(doc: ProvenanceDocument) -> str:
    """HTML for the UI: one span per unit with its author (and model) as data attributes. Third review of PR #79,
    finding 7: an invalid record is refused (verify_document) and EVERY interpolated value is escaped."""
    if not verify_document(doc, doc.text()):
        raise ValueError("refusing to render a provenance record that does not verify")
    out = []
    for s in doc.segments:
        attrs = f'data-author="{html.escape(s.author, quote=True)}"'
        if s.author == "model":
            attrs = (f'class="mstool-ai-text" {attrs} data-model="{html.escape(s.model_id or "", quote=True)}" '
                     f'data-agent="{html.escape(s.agent_id or "", quote=True)}"')
        elif s.edited_from_model:
            attrs = f'class="mstool-ai-edited" {attrs} data-edited-from-model="true"'
        out.append(f"<span {attrs}>{html.escape(s.text, quote=True)}</span>{html.escape(s.trailing)}")
    return "".join(out) + f'\n<p class="mstool-ai-legend">{html.escape(_legend(doc))}</p>'
