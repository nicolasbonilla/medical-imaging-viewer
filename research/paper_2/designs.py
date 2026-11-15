"""Paper 2 pipeline designs D1–D5 (PREREG §3), built on the agents benchmark v1 arms, which are unchanged.

Two views of one record:
- **The honest view** (`rec["view"]`) is what the model reads. It is the v1 view, except that regions and DIS are
  given as computed on the tool's unreviewed mask, marked "automatic, unreviewed" (`regions.confirmed` stays False).
- **The support view** (`support_view`) is what the frozen verifier v3 and the code skeleton read.
  - It is the same view with `regions.confirmed = True` whenever the record carries region counts.
  - Reason: v1's verifier flags any region statement when regions are "not confirmed", because in v1 such regions were
    never in the record. Here they are in the record, so a sentence that repeats them is faithful to it.
  - The verifier's code is unchanged; only the view it reads differs. PREREG §12 logs this.

Designs:
- **D1 (single call)** and **D2 (agent)** are v1's A1 and A2 on the honest view.
  - D2 adds the tool `get_second_segmentation` and a sentence saying that it exists.
  - D2i also adds "Compare the result with `get_second_segmentation` and report any disagreement."
- **D3, D4 and D5** are v1's A3 on the record each one receives:
  - D3: automatic regions and DIS;
  - D4: regions withheld and DIS not evaluated;
  - D5: the regions and DIS of agreed lesions, plus the count of single-tool candidates.
- **Code-written source line.** It names the arm's tool, because v1's line always named FLAMeS.
"""
import copy
import json
from typing import List

from research.agents_benchmark import arms as A
from research.agents_benchmark import config
from research.agents_benchmark import verifier as V

TOOL_LABEL = {"flames_ens": "FLAMeS, mean of 5 models", "flames_f0": "FLAMeS, fold 0", "lstai": "LST-AI",
              "wmhsynthseg": "WMH-SynthSeg", "mindglide": "MindGlide", "samseg": "SAMSEG"}

SECOND_TOOL = {"name": "get_second_segmentation",
               "description": "Lesion count, regions and dissemination-in-space status computed from a second, "
                              "independent automatic segmentation of the same scan.",
               "input_schema": {"type": "object", "properties": {}}}
TOOLS_D2 = A.TOOLS + [SECOND_TOOL]

_D2_AVAILABLE = ("A second, independent automatic segmentation of the same scan is available through the tool "
                 "get_second_segmentation.")
D2I_INSTRUCTION = "Compare the result with get_second_segmentation and report any disagreement."

SOURCE_LINE = "Source: automatic AI lesion marking ({tool}), not reviewed by a radiologist."
CANDIDATE_LINE = "Single-tool candidates, not used for dissemination: {n}."


def support_view(view):
    v = copy.deepcopy(view)
    if (v.get("regions") or {}).get("lesion_counts") is not None:
        v["regions"]["confirmed"] = True
    return v


def skeleton2(view, lang="en"):
    """v1's skeleton on the support view, with the arm's tool in the source line and D5's candidate line."""
    f, comp, imp, lim = A.skeleton(view, lang)
    seg = view["segmentation"]
    if not seg["confirmed_by_radiologist"] and seg.get("tool"):
        f[0] = SOURCE_LINE.format(tool=seg["tool"])
    n = view.get("single_tool_candidates")
    if n is not None:
        at = next(i for i, x in enumerate(f) if x.startswith(("Lesions per MAGNIMS region", "Lesion regions")))
        f.insert(at + 1, CANDIDATE_LINE.format(n=n))
    return f, comp, imp, lim


def assemble2(view, lang, findings_comment, impression_comment):
    s = A.SECTIONS[lang]
    f, comp, imp, lim = skeleton2(view, lang)
    out = [f"## {s['findings']}"] + [f"- {x}" for x in f]
    if findings_comment:
        out += ["", findings_comment]
    if comp:
        out += ["", f"## {s['comparison']}"] + [f"- {x}" for x in comp]
    out += ["", f"## {s['impression']}"] + [f"{i + 1}. {x}" for i, x in enumerate(imp)]
    if impression_comment:
        out += ["", impression_comment]
    out += ["", f"## {s['limitations']}"] + lim
    return "\n".join(out)


def tool_result2(view, name):
    if name == "get_second_segmentation":
        return view.get("second_segmentation") or {"available": False}
    return A.tool_result(view, name)


# ------------------------------------------------------------------------------------------------------ designs
class D1(A.A1):
    arm = "D1"

    def code_texts(self) -> List[str]:
        return []


class D2(A.A2):
    arm = "D2"
    extra = _D2_AVAILABLE

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.system = self.system.replace("get_longitudinal and get_acquisition.",
                                          "get_longitudinal, get_acquisition and get_second_segmentation. " + self.extra, 1)
        assert "get_second_segmentation" in self.system

    def next_request(self):
        req = super().next_request()
        if req is not None:
            req["tools"] = TOOLS_D2
        return req

    def consume(self, resp):                     # v1's A2.consume with tool_result2
        self.record_call(resp)
        if resp.get("error"):
            return self.fail(resp["error"])
        blocks = resp.get("content") or [{"type": "text", "text": resp.get("text") or ""}]
        uses = [b for b in blocks if b.get("type") == "tool_use"]
        if uses and self.tool_steps < config.A2_MAX_STEPS:
            self.messages.append({"role": "assistant", "content": blocks})
            results = []
            for u in uses:
                self.tool_calls.append(u["name"])
                results.append({"type": "tool_result", "tool_use_id": u["id"],
                                "content": json.dumps(tool_result2(self.view, u["name"]))})
            self.messages.append({"role": "user", "content": results})
            self.tool_steps += 1
            return
        text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        self.done = True
        self.result = {"status": "ok", "model_text": text, "authored": text,
                       "delivered": A.DISCLAIMER[self.lang] + "\n\n" + text, "tool_calls": self.tool_calls,
                       "tool_steps": self.tool_steps}

    def code_texts(self) -> List[str]:
        return []


class D2i(D2):
    arm = "D2i"
    extra = _D2_AVAILABLE + " " + D2I_INSTRUCTION


class Verified(A.A3):
    """D3, D4 and D5: v1's A3. The model reads the honest view; the skeleton and the verifier read the support view."""
    arm = "D3"

    def __init__(self, rec, lang="en", payload=None, max_tokens=config.MAX_TOKENS):
        A.Job.__init__(self, rec, lang, payload, max_tokens)
        self.llm_view = self.view
        self.view = support_view(self.llm_view)
        self.system = A.SYSTEM_A3
        self.attempts = []
        skel = assemble2(self.view, lang, "[FINDINGS_COMMENT]", "[IMPRESSION_COMMENT]")
        self.messages = [{"role": "user", "content": (
            A.user_lang_line(lang) + "\n\nMeasurement record:\n```json\n"
            + json.dumps(self.llm_view, ensure_ascii=False, separators=(",", ":"))
            + "\n```\n\nThe software has written this report; your two comments replace the two markers:\n\n" + skel)}]
        self.pending = True

    def check(self, text):                       # v1's A3.check with assemble2
        import re
        fails = []
        m = A._SLOT.search(text or "")
        if not m:
            return None, ["The answer did not follow the format: [FINDINGS_COMMENT] ... [IMPRESSION_COMMENT] ..."]
        fc, ic = m.group(1).strip(), m.group(2).strip()
        vals = A.placeholder_values(self.view, self.lang)
        for ph in set(re.findall(r"\{([a-z_]+)\}", fc + " " + ic)):
            if ph not in vals:
                fails.append(f"Placeholder {{{ph}}} is not available for this record.")
        if re.search(r"\d", re.sub(r"\{[a-z_]+\}", "", fc + " " + ic)):
            fails.append("Digits are not allowed in the comments; use a placeholder or no number.")
        for k, v in vals.items():
            fc, ic = fc.replace("{" + k + "}", v), ic.replace("{" + k + "}", v)
        if re.search(r"^\s*#", fc + "\n" + ic, re.M):
            fails.append("Headings are not allowed in the comments.")
        assembled = assemble2(self.view, self.lang, fc, ic)
        res = V.verify(assembled, None, self.view)
        for e in res["elements"]:
            fails.append(f"{e['detail']} (in: \"{e['unit']}\")")
        return assembled, fails

    def consume(self, resp):                     # v1's A3.consume with assemble2
        self.record_call(resp)
        if resp.get("error"):
            return self.fail(resp["error"])
        text = resp.get("text") or ""
        assembled, fails = self.check(text)
        self.attempts.append({"text": text, "failures": fails})
        if not fails:
            self.done = True
            self.result = {"status": "ok", "a3_outcome": f"passed_{len(self.attempts) - 1}", "model_text": text,
                           "authored": assembled, "delivered": A.DISCLAIMER[self.lang] + "\n\n" + assembled,
                           "attempts": self.attempts}
            return
        if len(self.attempts) <= config.A3_MAX_REGENERATIONS:
            self.messages.append({"role": "assistant", "content": text or "(empty)"})
            self.messages.append({"role": "user", "content": "Your comments failed the automatic check:\n- "
                                  + "\n- ".join(fails[:12]) + "\nRewrite both comments, fixing every point, in the same "
                                                              "format."})
            self.pending = True
            return
        blocked = assemble2(self.view, self.lang, "", "")
        self.done = True
        self.result = {"status": "ok", "a3_outcome": "blocked", "model_text": text, "authored": blocked,
                       "delivered": A.DISCLAIMER[self.lang] + "\n\n" + blocked + "\n\n" + A.WITHHELD[self.lang],
                       "attempts": self.attempts}

    def code_texts(self) -> List[str]:
        """Every line the code wrote: the classifier attributes these units to 'code' (PREREG §5.1)."""
        return [ln for ln in assemble2(self.view, self.lang, "", "").split("\n") if ln.strip() and not ln.startswith("#")]


class D3(Verified):
    arm = "D3"


class D4(Verified):
    arm = "D4"


class D5(Verified):
    arm = "D5"


DESIGNS = {"D1": D1, "D2": D2, "D2i": D2i, "D3": D3, "D4": D4, "D5": D5}
BOILERPLATE = [A.DISCLAIMER["en"], A.WITHHELD["en"]]
