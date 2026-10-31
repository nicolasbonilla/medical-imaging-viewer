"""Figures of the paper H manuscript, from git- and record-derived data only (offline).

    python docs/research/paper-h/manuscript/figures/make_figures.py

Inputs (both produced from pinned commits by read-only git commands and committed snapshots):
  research/paper_h/out/manuscript_data.json   (python research/paper_h/manuscript_data.py)
  research/paper_h/out/results.json           (python research/paper_h/run_all.py; October analysis)
If an input is missing it is recomputed first. No network access is needed.

Outputs: figN_*.png (300 dpi) and figN_*.pdf in this folder.
Palette: the validated reference palette of the dataviz method (light surface), categorical slots in fixed
order, an ordinal one-hue ramp for severity, status colours only for CI pass/fail.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "research" / "paper_h" / "out"

# --- palette (reference instance, light) ---------------------------------------------------
SURFACE = "#fcfcfb"
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
SEQ = {"blocker": "#104281", "major": "#256abf", "minor": "#5598e7", "nit": "#86b6ef"}
NEUTRAL = "#c3c2b7"
GOOD, CRITICAL = "#0ca30c", "#d03b3b"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8.5, "axes.titlesize": 9.5, "axes.titleweight": "bold",
    "axes.labelsize": 8.5, "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "legend.frameon": False, "legend.fontsize": 8, "lines.linewidth": 2,
})


def load() -> tuple[dict, dict]:
    md, rs = OUT / "manuscript_data.json", OUT / "results.json"
    if not md.exists():
        subprocess.run([sys.executable, str(ROOT / "research/paper_h/manuscript_data.py")], check=True, cwd=ROOT)
    if not rs.exists():
        subprocess.run([sys.executable, str(ROOT / "research/paper_h/run_all.py")], check=True, cwd=ROOT)
    return (json.loads(md.read_text(encoding="utf-8")), json.loads(rs.read_text(encoding="utf-8")))


def d(s: str) -> datetime:
    return datetime.fromisoformat(s[:10])


def save(fig, name: str) -> None:
    for ext in ("png", "pdf"):
        fig.savefig(HERE / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


def month_axis(ax) -> None:
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))


# --------------------------------------------------------------------------------------------
def fig1_timeline(md: dict) -> None:
    w = md["contribution"]["weekly"]
    x = [d(r["week"]) for r in w]
    a = [r["agent"] for r in w]
    o = [r["other"] for r in w]
    fig, ax = plt.subplots(figsize=(7.2, 2.9))
    ax.bar(x, a, width=5.2, color=BLUE, label="with the agent's Co-Authored-By trailer", edgecolor=SURFACE,
           linewidth=0.6)
    ax.bar(x, o, width=5.2, bottom=a, color=NEUTRAL, label="without the trailer", edgecolor=SURFACE,
           linewidth=0.6)
    events = [("2026-07-18", "CAPA-001: 21/22 'verified'\nre-verified to 4/22"),
              ("2026-09-28", "CAPA-006"),
              ("2026-10-17", "CAPA-007..011"),
              ("2026-10-22", "CAPA-012\n(approvals)"),
              ("2026-10-30", "first owner-signed\nweb sign-off")]
    top = max(ai + oi for ai, oi in zip(a, o))
    key = []
    for i, (day, label) in enumerate(events, start=1):
        ax.axvline(d(day), color=MUTED, linewidth=0.8, linestyle=(0, (2, 2)), zorder=0)
        ax.text(d(day), top * (1.04 + 0.09 * ((i + 1) % 2)), str(i), fontsize=7.5, color=INK, ha="center",
                va="bottom", fontweight="bold")
        key.append(f"{i}  {day[5:]}  " + label.replace("\n", " "))
    ax.text(0.02, 0.97, "\n".join(key), transform=ax.transAxes, fontsize=6.8, color=INK2, va="top", ha="left",
            linespacing=1.35)
    ax.set_ylim(0, top * 1.25)
    ax.set_ylabel("commits per week")
    month_axis(ax)
    c = md["contribution"]["commits"]["all"]
    ax.set_title(f"Commits on main, by week ({c['agent']} of {c['total']} carry the agent's trailer)", loc="left")
    ax.legend(loc="center left", ncol=1, bbox_to_anchor=(0, 0.45), fontsize=7)
    save(fig, "fig1_timeline")


def fig2_process(md: dict) -> None:
    rows = md["records"]["rows"]
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.6), sharex=True)
    start, end = d("2026-07-10"), d("2026-11-02")
    for kind, color in (("CAPA", BLUE), ("PRB", ORANGE)):
        ds = sorted(d(r["opened"]) for r in rows if r["kind"] == kind)
        axes[0].step([start] + ds + [end], [0] + list(range(1, len(ds) + 1)) + [len(ds)], where="post",
                     color=color, label=f"{kind} ({len(ds)})")
        axes[0].text(end, len(ds), f" {kind} {len(ds)}", color=INK2, fontsize=7.5, va="center")
    axes[0].set_title("Records opened", loc="left")
    axes[0].legend(loc="upper left", fontsize=7)
    ms = md["manifest_series"]
    xs = [d(p["date"]) for p in ms] + [end]
    for key, color, lab in (("controls", BLUE, "bound in manifest"), ("implemented", AQUA, "'implemented'")):
        ys = [p[key] for p in ms] + [ms[-1][key]]
        axes[1].step(xs, ys, where="post", color=color, label=f"{lab} ({ms[-1][key]})")
    axes[1].set_title("Risk controls in manifest", loc="left")
    axes[1].legend(loc="upper left", fontsize=7)
    snap = json.loads((ROOT / "research/paper_h/data/github_prs_full_2026-10-31.json").read_text(encoding="utf-8"))
    merged = sorted(d(p["merged"]) for p in snap["pull_requests"] if p["merged"])
    axes[2].step([start] + [m for m in merged if m >= start] + [end],
                 [sum(m < start for m in merged)] + list(range(sum(m < start for m in merged) + 1, len(merged) + 1))
                 + [len(merged)], where="post", color=VIOLET)
    axes[2].text(end, len(merged), f" {len(merged)}", color=INK2, fontsize=7.5, va="center")
    axes[2].set_title("Pull requests merged", loc="left")
    for ax in axes:
        ax.set_xlim(start, end)
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.set_ylim(bottom=0)
    fig.tight_layout(w_pad=1.6)
    save(fig, "fig2_process")


def fig3_negative_controls(md: dict) -> None:
    nc = md["negative_controls"]
    final, first = nc["release_2026_10_30_final"], nc["release_2026_10_30_first_run"]
    rows = sorted(final["rows"], key=lambda r: r["mutations"])
    names = [r["record"].replace("RELEASE-2026-10-30_", "").replace("_negative_controls.json", "") for r in rows]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(7.2, 3.6), gridspec_kw={"width_ratios": [1.1, 1]})
    y = range(len(rows))
    det = [r["detected"] for r in rows]
    eq = [r["declared_equivalent"] for r in rows]
    ax.barh(y, det, color=BLUE, height=0.7, label="detected (a bound test failed)")
    ax.barh(y, eq, left=det, color=ORANGE, height=0.7, label="declared equivalent")
    for i, r in enumerate(rows):
        ax.text(r["mutations"] + 2, i, str(r["mutations"]), va="center", fontsize=7, color=INK2)
    ax.set_yticks(list(y), names, fontsize=7)
    ax.set_xlabel("mutations per script")
    t = final["totals"]
    ax.set_title(f"Release 2026-10-30: {t['mutations']} mutations,\n{t['detected']} detected, "
                 f"{t['declared_equivalent']} equivalent (first run: {first['totals']['mutations']})", loc="left")
    ax.legend(loc="lower right", fontsize=7)
    ax.grid(axis="y", visible=False)
    h = nc["history"]
    runs = h["runs"]
    xs, ys, acc = [], [], 0
    for r in runs:
        acc += r["mutations"]
        xs.append(d(r["commit_date"]))
        ys.append(acc)
    bx.step(xs, ys, where="post", color=BLUE)
    bx.set_title(f"Committed record versions: {h['distinct_recorded_runs']} runs,\n"
                 f"{h['mutation_executions']:,} mutation executions, "
                 f"{len(h['runs_with_unexpected_survivor'])} unexpected survivors", loc="left")
    bx.set_ylabel("cumulative mutations")
    bx.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, interval=1))
    bx.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    plt.setp(bx.get_xticklabels(), rotation=45, ha="right")
    bx.set_xlim(d("2026-09-26"), d("2026-11-01"))
    bx.set_ylim(bottom=0)
    fig.tight_layout(w_pad=2.0)
    save(fig, "fig3_negative_controls")


def fig4_reviews(md: dict) -> None:
    r = md["reviews"]
    prs = [p for p in r["per_pr"]]
    sev = ["blocker", "major", "minor", "nit", "unlabelled"]
    colors = [SEQ["blocker"], SEQ["major"], SEQ["minor"], SEQ["nit"], NEUTRAL]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(7.2, 3.1), gridspec_kw={"width_ratios": [1.5, 1]})
    y = list(range(len(prs)))[::-1]
    left = [0] * len(prs)
    for s, c in zip(sev, colors):
        vals = [r["per_pr"][p].get(s, 0) for p in prs]
        ax.barh(y, vals, left=left, color=c, height=0.68, label=s, edgecolor=SURFACE, linewidth=0.6)
        left = [a + b for a, b in zip(left, vals)]
    for yi, p, tot in zip(y, prs, left):
        ax.text(tot + 0.6, yi, f"{tot}  ({r['rounds_by_pr'][p]} round{'s' if r['rounds_by_pr'][p] != 1 else ''})", va="center", fontsize=7, color=INK2)
    ax.set_yticks(y, [f"PR #{p}" for p in prs])
    ax.set_xlim(0, max(left) * 1.35)
    ax.set_xlabel("findings (severity as labelled in the record)")
    tot = r["total"]
    ax.set_title(f"Review findings, PRs #64-#74: {r['total_findings']} in {r['rounds']} rounds", loc="left")
    ax.legend(loc="lower right", fontsize=7, ncol=1)
    ax.grid(axis="y", visible=False)
    ch = r["by_channel"]
    order = sorted(ch, key=lambda k: -sum(ch[k].values()))
    yb = list(range(len(order)))[::-1]
    left = [0] * len(order)
    for s, c in zip(sev, colors):
        vals = [ch[k].get(s, 0) for k in order]
        bx.barh(yb, vals, left=left, color=c, height=0.6, edgecolor=SURFACE, linewidth=0.6)
        left = [a + b for a, b in zip(left, vals)]
    for yi, t in zip(yb, left):
        bx.text(t + 1, yi, str(t), va="center", fontsize=7, color=INK2)
    bx.set_yticks(yb, [k.replace(" / ", "/\n").replace("independent agent session", "independent\nagent session")
                       .replace("coordinating agent session", "coordinating\nagent session") for k in order],
                  fontsize=7)
    bx.set_xlim(0, max(left) * 1.25)
    bx.set_title("by channel", loc="left")
    bx.grid(axis="y", visible=False)
    fig.tight_layout(w_pad=1.5)
    save(fig, "fig4_reviews")


def fig5_approvals(md: dict) -> None:
    a = md["approvals"]
    cats = ["agent-trailered commit", "local commit without agent trailer",
            "owner sign-off in GitHub web editor (verified)"]
    labels = ["agent-trailered commit", "local commit, no trailer, unsigned (8832dae)",
              "owner sign-off, GitHub web editor, verified"]
    colors = [ORANGE, NEUTRAL, BLUE]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(7.2, 2.8), gridspec_kw={"width_ratios": [1, 1.25]})
    snaps = [("main @ 6209131\n(17 Oct)", a["lines_at_draft"]), ("main @ 8805882\n(31 Oct)", a["lines_at_final"])]
    for i, (lab, s) in enumerate(snaps):
        bottom = 0
        for c, col in zip(cats, colors):
            v = s["by_writer"].get(c, 0)
            ax.bar(i, v, bottom=bottom, color=col, width=0.55, edgecolor=SURFACE, linewidth=0.6)
            if v >= 25:
                ax.text(i, bottom + v / 2, str(v), ha="center", va="center", fontsize=7,
                        color="#ffffff" if col != NEUTRAL else INK)
            bottom += v
        ax.text(i, bottom + 8, f"{bottom} lines\n{s['documents']} documents", ha="center", fontsize=7, color=INK2)
    ax.set_xticks([0, 1], [s[0] for s in snaps])
    ax.set_ylim(0, a["lines_at_final"]["lines"] * 1.18)
    ax.set_ylabel("approval lines")
    ax.set_title("Who wrote the approval lines (git blame)", loc="left")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colors]
    ax.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.22), fontsize=6.5, ncol=1)
    ax.grid(axis="x", visible=False)
    subs = a["signoff_substitutions"]["commits"]
    y = list(range(len(subs)))[::-1]
    place = [s["by_kind"].get("approval placeholder", 0) for s in subs]
    other = [s["occurrences_replaced"] - p for s, p in zip(subs, place)]
    bx.barh(y, place, color=BLUE, height=0.6, label="approval placeholder")
    bx.barh(y, other, left=place, color=RED, height=0.6, label="not a placeholder (procedure text, quotation,\n"
                                                                   "'... and code review', pre-sign-off statement)")
    for yi, p, o in zip(y, place, other):
        bx.text(p + o + 4, yi, f"{p + o}" + (f"  ({o} not a placeholder)" if o else ""), va="center", fontsize=7,
                color=INK2)
    bx.set_yticks(y, [f"{s['sha']} ({s['date'][5:]})\n" + ("GitHub web, verified" if s["committer"] == "GitHub"
                                                           else "local, unsigned") for s in subs], fontsize=6.5)
    bx.set_xlim(0, max(p + o for p, o in zip(place, other)) * 1.55)
    bx.set_xlabel("occurrences of 'PENDING owner approval' replaced")
    bx.set_title("What each sign-off replaced", loc="left")
    bx.legend(loc="upper center", bbox_to_anchor=(0.45, -0.22), fontsize=6.5)
    bx.grid(axis="y", visible=False)
    fig.tight_layout(w_pad=1.5)
    save(fig, "fig5_approvals")


def fig6_verification(rs: dict) -> None:
    h = rs["rq3_verification"]["rcv_headline"]["rows"]
    cats = ["Verified", "Partial", "Overstated / not implemented"]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(7.2, 2.7), gridspec_kw={"width_ratios": [1, 1.2]})
    xs = range(len(cats))
    w = 0.36
    before = [h[c]["recorded_2026_04_12"] for c in cats]
    after = [h[c]["reverified_2026_07_18"] for c in cats]
    ax.bar([x - w / 2 for x in xs], before, width=w, color=NEUTRAL, label="recorded 2026-04-12 (prose)")
    ax.bar([x + w / 2 for x in xs], after, width=w, color=BLUE, label="re-verified 2026-07-18 (adversarial)")
    for x, b, a2 in zip(xs, before, after):
        ax.text(x - w / 2, b + 0.4, str(b), ha="center", fontsize=7.5, color=INK2)
        ax.text(x + w / 2, a2 + 0.4, str(a2), ha="center", fontsize=7.5, color=INK2)
    ax.set_xticks(list(xs), ["verified", "partial", "overstated /\nnot implemented"])
    ax.set_ylabel("risk controls (of 22)")
    ax.set_ylim(0, 30)
    ax.set_title("Risk-control verification record", loc="left")
    ax.legend(loc="upper right", fontsize=7)
    ax.grid(axis="x", visible=False)
    vals = rs["rq2_failures"]["summary"]["days_to_detection_by_stage"]
    for i, (stage, col) in enumerate((("escaped", ORANGE), ("contained", BLUE))):
        v = sorted(vals[stage]["values"])
        jitter = [(k % 5 - 2) * 0.05 for k in range(len(v))]
        bx.scatter(v, [i + j for j in jitter], s=22, color=col, edgecolor=SURFACE, linewidth=0.8, zorder=3)
        bx.text(max(v) + 6, i, f"n={vals[stage]['n']}, median {vals[stage]['median']} d", va="center",
                fontsize=7.5, color=INK2)
    bx.set_yticks([0, 1], ["escaped to main", "contained\nbefore merge"])
    bx.set_xlim(-8, 300)
    bx.set_ylim(-0.6, 1.6)
    bx.set_xlabel("days from introducing to detecting commit")
    bx.set_title("Persistence of 28 dated failure episodes (Oct. analysis)", loc="left")
    bx.grid(axis="y", visible=False)
    fig.tight_layout(w_pad=1.5)
    save(fig, "fig6_verification")


def fig7_channels(md: dict) -> None:
    rc = md["record_channels"]
    names = {"BC": "browser capture of a release build\n(filming the application)",
             "AR": "independent / adversarial review\n(separate agent session)",
             "RS": "owner's research studies\n(papers A, C, D, H)",
             "IM": "incidental, while implementing", "BP": "behaviour probe (requests, real browser)",
             "CR": "code reading, orchestrating session", "EX": "external literature research"}
    order = sorted(rc["by_channel"], key=lambda k: rc["by_channel"][k])
    fig, ax = plt.subplots(figsize=(7.2, 2.9))
    y = range(len(order))
    capa = [rc["by_kind"].get("CAPA", {}).get(k, 0) for k in order]
    prb = [rc["by_kind"].get("PRB", {}).get(k, 0) for k in order]
    ax.barh(y, capa, color=BLUE, height=0.62, label="CAPA (16)", edgecolor=SURFACE, linewidth=0.6)
    ax.barh(y, prb, left=capa, color=ORANGE, height=0.62, label="problem report, PRB (22)", edgecolor=SURFACE,
            linewidth=0.6)
    for i, (c, p) in enumerate(zip(capa, prb)):
        ax.text(c + p + 0.25, i, str(c + p), va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(list(y), [names[k] for k in order], fontsize=7)
    ax.set_xlabel("records (CAPA-001..016, PRB-001..031)")
    ax.set_title(f"How the {rc['records']} corrective-action and problem records were opened", loc="left")
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    save(fig, "fig7_channels")


def fig8_tests_ci(md: dict) -> None:
    t = md["tests_weekly"]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(7.2, 2.7))
    x = [d(p["date"]) for p in t]
    ax.plot(x, [p["backend_test_functions"] for p in t], color=BLUE, drawstyle="steps-post",
            label="backend test functions")
    ax.plot(x, [p["frontend_test_cases"] for p in t], color=ORANGE, drawstyle="steps-post",
            label="frontend test cases")
    ax.text(x[-1], t[-1]["backend_test_functions"], f" {t[-1]['backend_test_functions']}", fontsize=7.5,
            color=INK2, va="center")
    ax.text(x[-1], t[-1]["frontend_test_cases"], f" {t[-1]['frontend_test_cases']}", fontsize=7.5,
            color=INK2, va="center")
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    ax.set_title("Tests declared in the tree (weekly)", loc="left")
    ax.legend(loc="upper left", fontsize=7)
    ax.set_ylim(bottom=0)
    c = md["ci"]["by_month"]
    months = list(c)
    xs = range(len(months))
    s = [c[m].get("success", 0) for m in months]
    f = [c[m].get("failure", 0) for m in months]
    k = [c[m].get("cancelled", 0) for m in months]
    bx.bar(xs, s, color=GOOD, width=0.6, label="success", edgecolor=SURFACE, linewidth=0.6)
    bx.bar(xs, f, bottom=s, color=CRITICAL, width=0.6, label="failure", edgecolor=SURFACE, linewidth=0.6)
    bx.bar(xs, k, bottom=[a + b for a, b in zip(s, f)], color=NEUTRAL, width=0.6, label="cancelled",
           edgecolor=SURFACE, linewidth=0.6)
    for i, (a1, b1, c1) in enumerate(zip(s, f, k)):
        bx.text(i, a1 + b1 + c1 + 2, f"{a1}/{a1 + b1 + c1}", ha="center", fontsize=7, color=INK2)
    bx.set_xticks(list(xs), [datetime.fromisoformat(m + "-01").strftime("%b") for m in months])
    bx.set_title(f"CI runs by month ({md['ci']['workflow_runs']} runs, 7 jobs)", loc="left")
    bx.set_ylim(0, max(a1 + b1 + c1 for a1, b1, c1 in zip(s, f, k)) * 1.15)
    bx.set_ylabel("runs (label: successful/all)")
    bx.legend(loc="upper left", fontsize=7)
    bx.grid(axis="x", visible=False)
    fig.tight_layout(w_pad=1.5)
    save(fig, "fig8_tests_ci")


def main() -> None:
    md, rs = load()
    fig1_timeline(md)
    fig2_process(md)
    fig3_negative_controls(md)
    fig4_reviews(md)
    fig5_approvals(md)
    fig6_verification(rs)
    fig7_channels(md)
    fig8_tests_ci(md)


if __name__ == "__main__":
    main()
