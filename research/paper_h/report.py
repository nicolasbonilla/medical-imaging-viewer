"""Render the tables of RESULTS.md from out/results.json (no git access).

    python research/paper_h/run_all.py && python research/paper_h/report.py > tables.md

The tables in RESULTS.md were pasted from this output; re-run to check they still match.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.paper_h import config  # noqa: E402

CLASS_NAMES = {"P": "prose / self-attested", "N": "never executed / could never fail", "S": "wrong locus",
               "I": "environment could not observe", "M": "negative control invalid or blind",
               "R": "false statement in an agent-drafted record", "C": "clinical/labelling content not traced"}
CHANNEL_NAMES = {"AR": "adversarial review (agent sessions)", "BP": "behaviour probe", "SA": "systematic sweep",
                 "CI": "CI run", "IM": "while implementing a related action", "EX": "external research",
                 "OW": "owner", "SC": "self-check in the authoring session (post hoc)"}


def pct(a, b):
    return "—" if not b else f"{100 * a / b:.1f} %"


def rq1(r):
    c = r["rq1_contribution"]
    lines = ["| Month | Commits | Agent-trailered | Share |", "|---|---:|---:|---:|"]
    for m, v in c["monthly"].items():
        lines.append(f"| {m} | {v['total']} | {v['agent']} | {pct(v['agent'], v['total'])} |")
    a = c["commits"]["all"]
    lines.append(f"| **All** | **{a['total']}** | **{a['agent']}** | **{pct(a['agent'], a['total'])}** |")
    lines += ["", "| Trailer model string (self-reported) | Commits | First | Last |", "|---|---:|---|---|"]
    for m, n in c["models"].items():
        s = c["model_spans"][m]
        lines.append(f"| {m} | {n} | {s['first']} | {s['last']} |")
    return "\n".join(lines)


def rq2(r):
    f = r["rq2_failures"]
    out = ["| ID | Class | Channel | Stage | Introduced | Detected | Days | CAPA |",
           "|---|---|---|---|---|---|---:|---|"]
    for e in f["episodes"]:
        intro = f"`{e['introduced_commit']}` {e['introduced_date']}" if e["introduced_commit"] else "— (never committed)"
        days = "—" if e["days_to_detection"] is None else e["days_to_detection"]
        cls = e["class"] + ("+" + "".join(e["secondary_classes"]) if e["secondary_classes"] else "")
        out.append(f"| {e['id']} | {cls} | {e['channel']} | {e['stage']} | {intro} | "
                   f"`{e['detected_commit']}` {e['detected_date']} | {days} | {', '.join(e['capa'])} |")
    s = f["summary"]
    out += ["", "| Class | Primary | Incl. secondary | Escaped | Contained |", "|---|---:|---:|---:|---:|"]
    for k, name in CLASS_NAMES.items():
        out.append(f"| {k} — {name} | {s['by_class'][k]} | {s['by_class_including_secondary'][k]} | "
                   f"{s['by_stage_and_class']['escaped'].get(k, 0)} | {s['by_stage_and_class']['contained'].get(k, 0)} |")
    out += ["", "| Channel | Episodes | Escaped | Contained |", "|---|---:|---:|---:|"]
    for k, name in CHANNEL_NAMES.items():
        out.append(f"| {k} — {name} | {s['by_channel'][k]} | {s['by_stage_and_channel']['escaped'].get(k, 0)} | "
                   f"{s['by_stage_and_channel']['contained'].get(k, 0)} |")
    out += ["", "| CAPA | Severity | Opened (commit, date) | Channel |", "|---|---|---|---|"]
    for c in f["capas"]:
        out.append(f"| {c['id']} | {c['severity']} | `{c['opened_commit']}` {c['opened_date']} | {c['channel']} |")
    return "\n".join(out)


def rq3(r):
    v = r["rq3_verification"]
    out = ["| Record | Ref | Mutations | Detected | Declared equivalent/redundant | Unexpected undetected | Restored green |",
           "|---|---|---:|---:|---:|---:|---|"]
    for n in v["negative_controls"]:
        out.append(f"| {n['record']} | `{n['ref']}` | {n['mutations']} | {n['detected']} | "
                   f"{len(n['expected_undetected'])} | {len(n['unexpected_undetected'])} | {n['restored_green']} |")
    p = v["negative_controls_pooled"]
    out.append(f"| **Pooled** | | **{p['mutations']}** | **{p['detected']}** | **{p['declared_equivalent_or_redundant']}** | "
               f"**{p['unexpected_undetected']}** | {p['restored_green_all']} |")
    out += ["", "| Manifest at | Controls | implemented | not_implemented | unverified | implemented with ERRATUM |",
            "|---|---:|---:|---:|---:|---|"]
    for k, m in v["manifest"].items():
        st = m["status"]
        out.append(f"| {k} (`{config.REFS[k][:7]}`) | {m['controls']} | {st.get('implemented', 0)} | "
                   f"{st.get('not_implemented', 0)} | {st.get('unverified', 0)} | {', '.join(m['implemented_with_erratum'])} |")
    return "\n".join(out)


def main():
    r = json.loads((config.OUT_DIR / "results.json").read_text(encoding="utf-8"))
    for title, fn in (("RQ1", rq1), ("RQ2", rq2), ("RQ3", rq3)):
        print(f"<!-- {title} tables: python research/paper_h/report.py -->")
        print(fn(r))
        print()


if __name__ == "__main__":
    main()
