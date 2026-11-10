"""The product's claim check: the benchmark's frozen check v2 PLUS stricter rules on the model's own text (Class C,
report item). REQ-SAFE-048 (amended), RC-103; second independent review of PR #78, items A and B. DRAFT, PENDING owner
approval.

STRICTLY STRICTER THAN v2, by construction: `report_claim_verifier` (the byte-exact port of v2) is not changed; every
element it returns is kept, and the rules here only ADD elements (tests/unit/test_verified_report_review2.py checks
the property on the ported verifier corpus and on generated adversarial comments).

A. v2 drops a forbidden phrase whenever ANY negation or condition word stands earlier in the same sentence, so
   "This draft is not a diagnosis, but the lesion pattern is consistent with multiple sclerosis." passed it. Here:
   - a diagnostic statement is a finding in EITHER polarity: every L1 (diagnosis, criteria) or L4 (demyelination)
     phrase, every naming of multiple sclerosis and every "diagnos..." word — affirmed, denied or conditional — unless
     the whole sentence is one of the fixed disclaimers about the draft itself ("This draft is not a diagnosis.");
   - an activity statement (L3) likewise, in either polarity; the PREREG exception ("disease activity ... cannot be
     determined") holds within the same clause only;
   - a treatment phrase (L5) is exempt only when a negation GOVERNS it: among the three words just before it, in the
     same clause — never across a comma, ";", ":", a dash or brackets, nor across "but", "however", "although",
     "pero", "sin embargo", "aunque", "aber", "jedoch", "sondern" ...
B. v2 reads a line in bold, or in capitals of up to 60 characters, as a heading and checks nothing in it. Headings are
   not allowed in the comments: `heading_lines` names every line v2 would read as a heading (the answer check fails
   it, FMT.heading), and the rules above read every line, headings included.

K. (found by the agent-platform work, PR #79) v2 reads a statement on dissemination in space only from past
   participles and a few negations: "The findings fulfil dissemination in space.", "do not fulfil", "may meet",
   "erfullen ... nicht" passed it. Here a sentence of the comments that names dissemination in space and uses a
   criterion word (fulfil, meet, satisfy, support, cumplir, satisfacer, erfullen ...) is refused when DIS was not
   evaluated (any polarity, hedged too; only the "not evaluated" wording itself is allowed), and refused when DIS was
   evaluated and it contradicts the record (affirmed or hedged against "not met", denied against "met").

Rules A and B read text only; rule K also reads the record's DIS state.

@module services.report_claim_strict
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional

from app.services import report_claim_lexicon as L
from app.services import report_claim_verifier as V

KIND_DIAGNOSTIC = "strict_diagnostic"     # rule id E4.strict_diagnostic
KIND_ACTIVITY = "strict_activity"         # rule id E4.strict_activity
KIND_TREATMENT = "strict_treatment"       # rule id E4.strict_treatment

# The fixed words of the details below (RC-065: the device's own words of a regeneration request).
DETAIL_DIAGNOSTIC = "forbidden wording: a diagnostic statement, affirmed or denied"
DETAIL_ACTIVITY = "forbidden wording: a statement on disease activity, affirmed or denied"
DETAIL_TREATMENT = "forbidden wording: treatment or follow-up advice"
FIXED_DETAIL_TEXTS = (DETAIL_DIAGNOSTIC, DETAIL_ACTIVITY, DETAIL_TREATMENT)

# Diagnostic wording in either polarity (L1 and L4 of the frozen lexicon, plus these).
DIAGNOSTIC_TERMS = [re.compile(r"\bdiagnos\w*"), L.MS_MENTION]
# The only sentences with a diagnostic word that are allowed: the fixed disclaimers about the draft itself.
DISCLAIMER = re.compile(
    r"(?:this|the) (?:ai )?(?:draft|report|comment|text) (?:is|are) not (?:a )?diagnos(?:is|tic)"
    r"|(?:este|el) (?:borrador|informe|comentario|texto) no es (?:un )?diagnostico"
    r"|(?:dieser|der) (?:entwurf|bericht|kommentar|text) ist keine diagnose")

# Clause boundaries: a negation never reaches across one.
CLAUSE_BREAK = re.compile(
    r"[,;:()\[\]{}]|(?:^|\s)-+(?:\s|$)|\b(?:but|however|although|though|yet|whereas|while|nevertheless|nonetheless|"
    r"except|instead|rather|pero|sin embargo|aunque|mientras|no obstante|sino|excepto|aber|jedoch|doch|allerdings|"
    r"obwohl|wahrend|sondern|dennoch|trotzdem|ausser)\b")
GOVERNING_WORDS = 3

_SENT_SPLIT = re.compile(r"(?<=[.!?;])\s+(?=\S)")
_LINE_MARK = re.compile(r"^\s*(?:>\s*)*(?:#{1,6}\s*|[-*+]\s+|\d{1,3}[.)]\s+)?")


def comment_sentences(text: str) -> Iterator[str]:
    """Every sentence of every line of `text`, markup removed (headings, bold and capitals included)."""
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        plain = _LINE_MARK.sub("", line).replace("*", "").replace("_", " ").strip()
        for sentence in _SENT_SPLIT.split(plain):
            if sentence.strip():
                yield sentence.strip()


def _clause_before(fold: str, start: int) -> str:
    """The text of the clause that ends where a match starts."""
    head = fold[:start]
    cut = 0
    for m in CLAUSE_BREAK.finditer(head):
        cut = m.end()
    return head[cut:]


def _clause_of(fold: str, start: int, end: int) -> str:
    """The whole clause around a match."""
    before = _clause_before(fold, start)
    after = fold[end:]
    m = CLAUSE_BREAK.search(after)
    return before + fold[start:end] + (after[:m.start()] if m else after)


def governed_by_negation(fold: str, m: "re.Match[str]") -> bool:
    """True only when a negation stands among the few words just before the match, in the same clause."""
    words = _clause_before(fold, m.start()).split()
    return bool(L.NEGATION.search(" ".join(words[-GOVERNING_WORDS:])))


def is_disclaimer(fold: str) -> bool:
    return bool(DISCLAIMER.fullmatch(re.sub(r"\s+", " ", fold).strip(" .!")))


def _hits(fold: str, patterns) -> List["re.Match[str]"]:
    return [m for p in patterns for m in p.finditer(fold)]


def sentence_elements(sentence: str) -> List[Dict[str, Any]]:
    """The stricter rules on one sentence of the model's text (elements in the verifier's shape)."""
    fold = L.fold(sentence)
    out: List[Dict[str, Any]] = []

    def add(kind: str, detail: str, terms: List[str]) -> None:
        out.append({"cls": "E4", "kind": kind, "unit": sentence[:200],
                    "detail": f"{detail}: {sorted(set(terms))[:4]}"})

    if not is_disclaimer(fold):
        diag = _hits(fold, L.L1 + L.L4 + DIAGNOSTIC_TERMS)
        if diag:
            add(KIND_DIAGNOSTIC, DETAIL_DIAGNOSTIC, [m.group(0) for m in diag])
    act = [m for m in _hits(fold, L.L3)
           if not (L.ACTIVITY_TERM.fullmatch(m.group(0))
                   and L.UNDETERMINED.search(_clause_of(fold, m.start(), m.end())))]
    if act:
        add(KIND_ACTIVITY, DETAIL_ACTIVITY, [m.group(0) for m in act])
    treat = [m for m in _hits(fold, L.L5) if not governed_by_negation(fold, m)]
    if treat:
        add(KIND_TREATMENT, DETAIL_TREATMENT, [m.group(0) for m in treat])
    return out


# ─────────────────────────────────────────── K: statements on dissemination in space (found by PR #79)
# v2's DIS_POS / DIS_NEG know past participles ("met", "fulfilled", "erfullt") and a few negations; present-tense,
# negated and hedged wording ("the findings fulfil DIS", "do not fulfil", "may meet", "erfullen ... nicht") passed.
DIS_NAMED = re.compile(r"\b(?:dissemination in space|dis|diseminacion en (?:el )?espacio|diseminacion espacial|"
                       r"raumlich\w* dissemination|dissemination im raum|disseminierung im raum)\b")
# criterion words only — not words that usually describe the lesions or the review ("present", "confirmed")
# (verbs and participles only: the nouns "fulfilment", "cumplimiento", "Erfullung" name the criterion, they state
# nothing — "evaluating the fulfilment of DIS")
DIS_CRITERION = re.compile(
    r"\b(?:fulfil(?!l?ment)\w*|fulfill(?!ment)\w*|meet(?:s|ing)?|met|satisf(?!action)\w*|support\w*|demonstrat\w*|"
    r"establish\w*|consistent with|cumpl(?!imiento)\w*|satisfac(?!cion)\w*|satisfech\w*|apoy\w*|respald\w*|"
    r"demostr\w*|establec\w*|compatible|erfull(?!ung)\w*|gegeben|nachgewiesen|unterstutz\w*|vereinbar)\b")
DETAIL_DIS_NOT_EVALUATED = "dissemination in space was not evaluated: a statement on it is not allowed"
DETAIL_DIS_STATUS = "the statement on dissemination in space contradicts the record"
KIND_DIS_NOT_EVALUATED = "strict_dis_not_evaluated"     # rule id E2.strict_dis_not_evaluated
KIND_DIS_STATUS = "strict_dis_status"                   # rule id E2.strict_dis_status
FIXED_DETAIL_TEXTS = FIXED_DETAIL_TEXTS + (DETAIL_DIS_NOT_EVALUATED, DETAIL_DIS_STATUS)


DIS_WORDS_APART = 4


def _criteria_on_dis(fold: str) -> List["re.Match[str]"]:
    """Criterion words that speak of dissemination in space: in the same clause as its name and at most four words
    from it ("the findings fulfil DIS", "DIS is not met", "erfullt die raumliche Dissemination") — not a verb of
    another part of the sentence ("the scan demonstrates seven lesions, with DIS not evaluated")."""
    out = []
    for d in DIS_NAMED.finditer(fold):
        for m in DIS_CRITERION.finditer(fold):
            between = fold[m.end():d.start()] if m.end() <= d.start() else fold[d.end():m.start()]
            if m.start() < d.end() and m.end() > d.start():
                between = ""
            if not CLAUSE_BREAK.search(between) and len(between.split()) <= DIS_WORDS_APART and m not in out:
                out.append(m)
    return out


def _negated_claim(fold: str, m: "re.Match[str]") -> bool:
    """A criterion word is denied when a negation governs it (just before it, same clause) or follows it in the same
    clause (German puts "nicht" after the verb: "erfullt die raumliche Dissemination nicht")."""
    if governed_by_negation(fold, m):
        return True
    after = fold[m.end():]
    cut = CLAUSE_BREAK.search(after)
    return bool(L.NEGATION.search(after[:cut.start()] if cut else after))


def dis_elements(sentence: str, view: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """K: a sentence of the comments that names dissemination in space and states something about it.

    DIS not evaluated: any such statement — affirmed, denied or hedged — is refused; only the "not evaluated" wording
    itself is allowed (rule 3 of the instructions). DIS evaluated: a statement that contradicts the record is
    refused — an affirmed or hedged one against "not met", a denied one against "met"."""
    if not isinstance(view, dict):
        return []
    fold = L.fold(sentence)
    if not DIS_NAMED.search(fold):
        return []
    dis = view.get("dis") or {}
    if dis.get("status") != "evaluated":
        rest = L.NOT_EVALUATED.sub(lambda x: " " * len(x.group(0)), fold)    # same length: positions kept
        hits = [m.group(0) for m in _criteria_on_dis(rest)]
        if hits:
            return [{"cls": "E2", "kind": KIND_DIS_NOT_EVALUATED, "unit": sentence[:200],
                     "detail": f"{DETAIL_DIS_NOT_EVALUATED}: {sorted(set(hits))[:4]}"}]
        return []
    met = bool(dis.get("dis_met_brain"))
    wrong = [m.group(0) for m in _criteria_on_dis(fold) if _negated_claim(fold, m) == met]
    if wrong:
        return [{"cls": "E2", "kind": KIND_DIS_STATUS, "unit": sentence[:200],
                 "detail": f"{DETAIL_DIS_STATUS} (met={met}): {sorted(set(wrong))[:4]}"}]
    return []


def comment_elements(text: str, view: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """The stricter rules on every sentence of every line of the model's text (with the record: also K)."""
    return [e for s in comment_sentences(text) for e in sentence_elements(s) + dis_elements(s, view)]


def heading_lines(text: str) -> List[str]:
    """Lines the frozen check would read as a heading (markdown, bold-only, capitals, an inline section label) — and
    so check for nothing. None is allowed in a comment."""
    out = [u["text"] for u in V.units(text) if u.get("heading")]
    out += [line.strip() for line in (text or "").split("\n") if re.match(r"^\s*#", line)]
    return out


def verify(authored: str, delivered: Optional[str], view: Dict[str, Any]) -> Dict[str, Any]:
    """The frozen v2 result with the stricter elements of every sentence of `authored` added (never removed)."""
    res = V.verify(authored, delivered, view)
    extra = comment_elements(authored, view)
    if extra:
        res["elements"] = list(res["elements"]) + extra
        res["n_elements"] = len(res["elements"])
        res["primary"] = True
        res["by_class"] = {c: sum(1 for e in res["elements"] if e["cls"] == c) for c in ("E1", "E2", "E3", "E4")}
    return res
