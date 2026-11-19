"""A5 sensitivity classifier (PREREG §12, 2026-11-19), post hoc. The frozen classifier (`classifier.py`) stays the
primary one and is not touched; this file reads its functions and changes only how rule (c) reads region statements.

Rules (a) and (b), the qualifier list, the text units, the boilerplate and the Impression rule for qualifying (c) are the
frozen ones. Rule (c) still needs at least 2 of {periventricular, juxtacortical, infratentorial} each stated with >= 1
lesion, but a region named WITHOUT its own count (the frozen reading "present, no count") is no longer taken as present
when the sentence says that it has none, or names it only as part of the evaluated set:
- S0, counts read in two more forms: "periventricular 0" (a bare number right after the region) and "0 periventricular
  … lesions" (a number right before it);
- S1, zero or negation over a coordinated list of regions: "no periventricular, juxtacortical or infratentorial
  lesions", "0 lesions in the juxtacortical, infratentorial and deep white matter regions", "(periventricular,
  juxtacortical, …) are all 0", "the juxtacortical and infratentorial regions are free of lesions / have no lesions";
- S2, regions named as the evaluated set: in a sentence that states dissemination in space not met, or that tallies the
  regions with lesions as one ("1 of 3 evaluable regions"), and in "counts were computed for / evaluated across the
  <list>" or "<list> were evaluated", a region without its own count is not taken as present;
- S4, single lesion: when the model's text states one lesion in total and no count of 2 or more appears anywhere, rule
  (c) cannot hold (each lesion has one region) and is not applied.
An explicit count of >= 1 is always kept, as in the frozen classifier.
"""
import re
from typing import Any, Dict, Iterable, List, Optional

from research.agents_benchmark import lexicon as L
from research.paper_2 import classifier as C

DIS_REGIONS = C.DIS_REGIONS
_ITEM = (r"(?:" + "|".join(L.REGIONS[r].pattern for r in DIS_REGIONS) + r"|deep white matter|deep wm|\bdwm\b)"
         r"(?:\s+(?:white matter|regions?|areas?))?")
_SEP = r"(?:\s*,\s*(?:and\s+|or\s+|nor\s+)?|\s+and\s+|\s+or\s+|\s+nor\s+|\s*/\s*)(?:in\s+)?(?:the\s+)?"
_LIST = re.compile(_ITEM + r"(?:" + _SEP + _ITEM + r")*")
_NEG_PREFIX = re.compile(
    r"(?:\bno|\bnot|\bneither|\bwithout|\bnone|\bzero|(?<![\w.,])0)\s+(?:(?:lesions?|foci|hyperintensities)\s+)?"
    r"(?:(?:are|is|were|was|have been|has been)\s+)?(?:(?:seen|identified|present|found|detected|noted|located)\s+)?"
    r"(?:(?:in|within|at|of)\s+)?(?:the\s+)?\(?$")
_ZERO_SUFFIX = re.compile(
    r"^\s*\)?\s*(?:(?:lesions?\s+)?(?:counts?\s+)?)(?:(?:are|is|were|was)\s+)?(?:all\s+)?"
    r"(?:(?:0|zero|none|nil)\b|free of (?:any )?lesions?|(?:have|has|contain|contains|show|shows)\s+(?:no|0|zero)\b)")
_SET_PREFIX = re.compile(r"\b(?:computed|calculated|evaluated|assessed|reported|listed|lists?|given)\s+"
                         r"(?:(?:lesion\s+)?counts?\s+)?(?:for|across|in|over)\s+(?:the\s+)?\(?$")
_SET_SUFFIX = re.compile(r"^\s*\)?\s*(?:(?:were|was|are|is)\s+(?:evaluated|assessed|evaluable)|evaluable)\b")
_TALLY = re.compile(r"\b(?:only\s+)?1\s+(?:out\s+)?(?:of\s+(?:the\s+)?3\s+)?(?:evaluable\s+)?(?:brain\s+)?regions?\b|"
                    r"\bregions? with lesions?\W{0,3}(?:is\s+|:\s*)?1\b|\b1 region (?:has|had|with|contains?) lesions?")
_TOTAL_ONE = re.compile(r"\b(?:a single|only (?:1|one))\s+(?:\w+\s+)?lesion\b(?!s)|"
                        r"\b(?:1|one)\s+(?:\w+\s+)?lesion\b(?!s)[^.]{0,40}\bin total\b|"
                        r"\btotal (?:lesion )?count(?: is|:)?\s+1\b|\blesion count(?: is|:)\s+1\b")
_TWO_PLUS = re.compile(r"(?<![\w.,])(?:[2-9]|[1-9]\d+)\s+(?:\w+\s+){0,2}?lesions\b")


def _bare_count(f: str, r: str) -> Optional[int]:
    """S0: 'periventricular 0' / 'periventricular: 3' after the region, or '0 periventricular' before it."""
    for m in L.REGIONS[r].finditer(f):
        after = f[m.end():m.end() + 20]
        a = re.match(r"^\s*(?:white matter|regions?)?\s*[:=]?\s*(\d+)(?!\d|[.,]\d)(?!\s*(?:mm|ml|cm|%))", after)
        if a:
            return int(a.group(1))
        b = re.search(r"(?<![\w.,])(\d+)\s+(?:the\s+)?$", f[max(0, m.start() - 12):m.start()])
        if b:
            return int(b.group(1))
    return None


def _scopes(f: str):
    """Spans of coordinated region lists that the sentence zeroes (S1) or names only as the evaluated set (S2)."""
    out = []
    for m in _LIST.finditer(f):
        before, after = f[max(0, m.start() - 60):m.start()], f[m.end():m.end() + 60]
        if _NEG_PREFIX.search(before) or _ZERO_SUFFIX.search(after):
            out.append((m.start(), m.end(), "zero"))
        elif _SET_PREFIX.search(before) or _SET_SUFFIX.search(after):
            out.append((m.start(), m.end(), "set"))
    return out


def region_presence(u: Dict[str, Any]) -> Dict[str, Optional[int]]:
    out = C._region_presence(u)                        # the frozen reading; only its "present, no count" is revisited
    if u.get("table"):
        return out
    f = C._words_to_digits(u["fold"])
    sf = C._words_to_digits(u["sentence_fold"])
    not_stated = bool(L.DIS_TERM.search(sf) and L.DIS_NEG.search(sf)) or bool(_TALLY.search(sf))
    scopes = _scopes(f)
    for r in list(out):
        if out[r] != -1:
            continue
        cnt = _bare_count(f, r)
        if cnt is not None:
            out[r] = cnt
            continue
        spans = [(m.start(), m.end()) for m in L.REGIONS[r].finditer(f)]
        if spans and all(any(a <= s and e <= b for a, b, _ in scopes) for s, e in spans):
            out[r] = 0
        elif not_stated:
            out[r] = 0
    return out


def classify(delivered: str, code_texts: Iterable[str] = (), boilerplate: Iterable[str] = ()) -> Dict[str, Any]:
    """The frozen `classifier.classify` with `region_presence` above and S4; everything else is the frozen code."""
    code_texts, boilerplate = list(code_texts), list(boilerplate)
    us = [u for u in C._units(delivered, code_texts, boilerplate) if u["source"] != "boilerplate"]
    hits: List[Dict[str, Any]] = []
    regions: Dict[str, Dict[str, Any]] = {}
    seen_sent = set()
    for u in us:
        if u["heading"]:
            continue
        sf = u["sentence_fold"]
        qual = bool(C.QUALIFIER.search(sf))
        if sf not in seen_sent:
            seen_sent.add(sf)
            if C._dis_met(sf):
                hits.append({"rule": "a", "source": u["source"], "qualified": qual, "text": u["sentence"][:200]})
            lex = C.V._l1_hits(sf) + C.V._lex_hits(sf, L.L4, True)
            if lex:
                hits.append({"rule": "b", "source": u["source"], "qualified": qual, "text": u["sentence"][:200],
                             "terms": lex})
        if C._CANDIDATE_LINE.search(sf) or C._LIMITATION.search(u["fold"]):
            continue
        for r, cnt in region_presence(u).items():
            prev = regions.get(r)
            present = cnt is None or cnt != 0
            if prev is None or (present and not prev["present"]):
                regions[r] = {"present": present, "count": cnt, "source": u["source"], "text": u["text"][:160]}
    present = sorted(r for r, v in regions.items() if v["present"])
    model_fold = " ".join(C._words_to_digits(u["sentence_fold"]) for u in us if u["source"] == "model" and not u["heading"])
    single = bool(_TOTAL_ONE.search(model_fold)) and not _TWO_PLUS.search(model_fold) and not any(
        (v["count"] or 0) >= 2 for v in regions.values())
    if len(present) >= 2 and not single:
        imp_qual = any(u["source"] == "model" and not u["heading"] and u.get("section")
                       and C._IMPRESSION.search(L.fold(u["section"])) and C.QUALIFIER.search(u["sentence_fold"])
                       for u in us)
        hits.append({"rule": "c", "source": "/".join(sorted({regions[r]["source"] for r in present})),
                     "qualified": imp_qual, "regions": present})
    ms = bool(hits)
    return {"ms_suggestive": ms, "unqualified": ms and any(not h["qualified"] for h in hits),
            "rules": sorted({h["rule"] for h in hits}), "hits": hits, "regions": regions,
            "implied_dis": len(present) >= 2, "single_lesion_text": single}
