"""Figures of the paper H manuscript, from git- and record-derived data only (offline).

    python docs/research/paper-h/manuscript/figures/make_figures.py

Inputs (both produced from pinned commits by read-only git commands and committed snapshots):
  research/paper_h/out/manuscript_data.json   (python research/paper_h/manuscript_data.py)
  research/paper_h/out/results.json           (python research/paper_h/run_all.py; October analysis)
If an input is missing it is recomputed first. No network access is needed.

Outputs: figN_*.pdf (vector, Arial embedded as TrueType) and figN_*.png (600 dpi) in this folder, drawn at their
final size for a Springer journal (174 mm full width, 129 mm for Figure 7) in the MSTool-AI house style
(mstool_figstyle.py + mstool.mplstyle): white ground, thin axes, direct labels, notes in the captions.
Palette: the house palette (muted, colour-blind safe; checked for deuteranopia, protanopia and tritanopia):
blue = the agent's work, ochre = second category, the met / not-met pair (teal / brick) only for pass/fail and
contained/escaped, a one-hue ordinal ramp for review severity.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mstool_figstyle as fs  # noqa: E402

fs.use()
import matplotlib.dates as mdates  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

ROOT = HERE.parents[4]
OUT = ROOT / "research" / "paper_h" / "out"
W_FULL, W_ONEHALF = 174.0, 129.0          # Springer figure widths (mm)
SEV = ["blocker", "major", "minor", "nit", "unlabelled"]
SEV_COL = list(fs.ORDINAL4) + [fs.GREY_LIGHT]


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
    fs.save(fig, str(HERE / name))


def month_ticks(ax, fmt="%b", years=True) -> None:
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonthday=15))
    ax.figure.canvas.draw()
    labels = []
    for t in ax.get_xticks():
        dt = mdates.num2date(t)
        s = dt.strftime(fmt)
        if years and (dt.month == 1 or not labels):
            s += f"\n{dt.year}"
        labels.append(s)
    ax.set_xticks(ax.get_xticks())
    ax.set_xticklabels(labels)


def end_label(ax, x, y, s, dx=3, **kw):
    kw.setdefault("fontsize", 7)
    kw.setdefault("color", fs.INK)
    return ax.annotate(s, (x, y), xytext=(dx, 0), textcoords="offset points", va="center", ha="left",
                       annotation_clip=False, **kw)


def key_row(fig, x_mm, y_mm, items, gap=4.0, size=2.2):
    """Compact one-line key of filled squares (only where direct labels would not fit)."""
    x = x_mm
    for col, lab in items:
        fig.patches.append(Rectangle((fs.fx(fig, x), fs.fy(fig, y_mm + size / 2)), size / fig._mm[0], size / fig._mm[1],
                                     transform=fig.transFigure, color=col, lw=0))
        fs.text_mm(fig, x + size + 1.2, y_mm, lab, va="center", fontsize=7)
        x += size + 1.2 + fs.text_width_mm(fig, lab) + gap


# --------------------------------------------------------------------------------------------
def fig1_timeline(md: dict) -> None:
    w = md["contribution"]["weekly"]
    x = [d(r["week"]) for r in w]
    a = [r["agent"] for r in w]
    o = [r["other"] for r in w]
    fig = fs.figure(W_FULL, 60)
    ax = fs.axes(fig, 12.0, 3.5, 159.0, 46.5)
    ax.bar(x, a, width=5.0, color=fs.PRIMARY, lw=0, zorder=2)
    ax.bar(x, o, width=5.0, bottom=a, color=fs.GREY_LIGHT, lw=0, zorder=2)
    events = [("2026-07-18", "CAPA-001: 21 of 22 'verified' controls re-verified to 4"),
              ("2026-09-28", "CAPA-006"),
              ("2026-10-17", "CAPA-007 to CAPA-011"),
              ("2026-10-22", "CAPA-012 (approvals)"),
              ("2026-10-30", "First owner-signed web sign-off")]
    top = max(ai + oi for ai, oi in zip(a, o))
    ymax = top * 1.16
    for i, (day, label) in enumerate(events, start=1):
        ax.plot([d(day)] * 2, [0, ymax * (0.93 if i % 2 else 0.86)], color=fs.INK2, lw=0.5, ls=(0, (2, 2)), zorder=1)
        ax.annotate(str(i), (d(day), ymax * (0.93 if i % 2 else 0.86)), ha="center", va="bottom", fontsize=6.5,
                    fontweight="bold", color=fs.INK)
    # event key in the empty early months
    for i, (day, label) in enumerate(events, start=1):
        yk = ymax * (0.95 - 0.085 * (i - 1))
        ax.text(d("2025-12-08"), yk, str(i), fontsize=6.5, fontweight="bold", va="center", ha="left")
        ax.text(d("2025-12-18"), yk, datetime.fromisoformat(day).strftime("%d %b"), fontsize=6.5, va="center",
                ha="left", color=fs.INK2)
        ax.text(d("2026-01-12"), yk, label, fontsize=6.5, va="center", ha="left")
    # direct labels for the two series, on the April bars
    i_apr = max(range(len(x)), key=lambda k: (x[k].month == 4) * (a[k] + o[k]))
    ax.annotate("Agent's Co-Authored-By trailer", (x[i_apr - 2], a[i_apr - 2] * 0.6), xytext=(-30, 24),
                textcoords="offset points", ha="right", va="center", fontsize=7,
                arrowprops=dict(arrowstyle="-", lw=0.4, color=fs.GREY_MID, shrinkA=1, shrinkB=1))
    ax.annotate("No trailer", (x[i_apr], a[i_apr] + o[i_apr] * 0.6), xytext=(8, 4), textcoords="offset points",
                ha="left", va="center", fontsize=7,
                arrowprops=dict(arrowstyle="-", lw=0.4, color=fs.GREY_MID, shrinkA=1, shrinkB=1))
    ax.set_ylim(0, ymax)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlim(d("2025-11-20"), d("2026-11-08"))
    ax.set_ylabel("Commits per week")
    month_ticks(ax)
    ax.tick_params(axis="x", which="minor", length=0)
    save(fig, "fig1_timeline")


def fig2_process(md: dict) -> None:
    rows = md["records"]["rows"]
    fig = fs.figure(W_FULL, 47)
    start, end = d("2026-07-10"), d("2026-11-02")
    PW, GX, L, T, PH = 41.0, 17.5, 12.0, 4.5, 35.5
    axes = [fs.axes(fig, L + i * (PW + GX), T, PW, PH) for i in range(3)]
    for i, ax in enumerate(axes):
        fs.panel_label(fig, "abc"[i], L + i * (PW + GX) - 11.5, 0.4)
    for kind, color in (("CAPA", fs.PRIMARY), ("PRB", fs.OCHRE)):
        ds = sorted(d(r["opened"]) for r in rows if r["kind"] == kind)
        axes[0].step([start] + ds + [end], [0] + list(range(1, len(ds) + 1)) + [len(ds)], where="post",
                     color=color, lw=fs.LW_DATA)
        end_label(axes[0], end, len(ds), f"{len(ds)}", dx=2)
        n_aug = sum(1 for t in ds if t <= d("2026-08-01"))
        axes[0].annotate(kind, (d("2026-07-24"), n_aug), xytext=(0, 2.5), textcoords="offset points", ha="left",
                         va="bottom", fontsize=7, color=fs.text_color(color))
    axes[0].set_ylabel("Records opened")
    ms = md["manifest_series"]
    xs = [d(p["date"]) for p in ms] + [end]
    for key, color, lab in (("controls", fs.INK2, "Bound in manifest"), ("implemented", fs.PRIMARY, "'Implemented'")):
        ys = [p[key] for p in ms] + [ms[-1][key]]
        axes[1].step(xs, ys, where="post", color=color, lw=fs.LW_DATA)
        end_label(axes[1], end, ms[-1][key], f"{ms[-1][key]}", dx=2)
        axes[1].annotate(lab, (xs[0], ys[0]), xytext=(0, 2.5), textcoords="offset points", ha="left", va="bottom",
                         fontsize=7, color=fs.text_color(color))
    axes[1].set_ylabel("Risk controls in manifest")
    snap = json.loads((ROOT / "research/paper_h/data/github_prs_full_2026-10-31.json").read_text(encoding="utf-8"))
    merged = sorted(d(p["merged"]) for p in snap["pull_requests"] if p["merged"])
    axes[2].step([start] + [m for m in merged if m >= start] + [end],
                 [sum(m < start for m in merged)] + list(range(sum(m < start for m in merged) + 1, len(merged) + 1))
                 + [len(merged)], where="post", color=fs.PRIMARY, lw=fs.LW_DATA)
    end_label(axes[2], end, len(merged), f"{len(merged)}", dx=2)
    axes[2].set_ylabel("Pull requests merged")
    for ax, top, ticks in zip(axes, (24, 92, 68), ((0, 5, 10, 15, 20), (0, 20, 40, 60, 80), (0, 20, 40, 60))):
        ax.set_xlim(start, end)
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.set_ylim(0, top)
        ax.set_yticks(ticks)
    save(fig, "fig2_process")


def fig3_negative_controls(md: dict) -> None:
    nc = md["negative_controls"]
    final = nc["release_2026_10_30_final"]
    rows = sorted(final["rows"], key=lambda r: r["mutations"])
    names = [r["record"].replace("RELEASE-2026-10-30_", "").replace("_negative_controls.json", "") for r in rows]
    fig = fs.figure(W_FULL, 63)
    ax = fs.axes(fig, 33.0, 4.0, 62.0, 50.0)
    fs.panel_label(fig, "a", 0, 0.4)
    y = list(range(len(rows)))
    det = [r["detected"] for r in rows]
    eq = [r["declared_equivalent"] for r in rows]
    ax.barh(y, det, color=fs.PRIMARY, height=0.68, lw=0, zorder=2)
    ax.barh(y, eq, left=det, color=fs.OCHRE, height=0.68, lw=0, zorder=2)
    for i, r in enumerate(rows):
        ax.annotate(str(r["mutations"]), (r["mutations"], i), xytext=(2.5, 0), textcoords="offset points",
                    va="center", fontsize=6.5, color=fs.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_xlim(0, 130)
    ax.set_xticks([0, 25, 50, 75, 100, 125])
    ax.set_xlabel("Mutations per script")
    top = len(rows) - 1
    ax.text(3, top, "detected", color="white", fontsize=6.5, va="center", ha="left", zorder=3)
    i_eq = max(range(len(rows)), key=lambda k: eq[k])
    ax.annotate("declared equivalent", (det[i_eq] + eq[i_eq] / 2, i_eq - 0.34), xytext=(72, i_eq - 0.52),
                textcoords="data", ha="left", va="center", fontsize=6.5, color=fs.INK,
                arrowprops=dict(arrowstyle="-", lw=0.4, color=fs.GREY_MID, shrinkA=1, shrinkB=0.5))
    h = nc["history"]
    xs, ys, acc = [], [], 0
    for r in h["runs"]:
        acc += r["mutations"]
        xs.append(d(r["commit_date"]))
        ys.append(acc)
    bx = fs.axes(fig, 120.0, 4.0, 46.0, 50.0)
    fs.panel_label(fig, "b", 106.0, 0.4)
    bx.step(xs, ys, where="post", color=fs.PRIMARY, lw=fs.LW_DATA)
    end_label(bx, xs[-1], ys[-1], f"{h['mutation_executions']:,}", dx=2)
    bx.set_ylabel("Cumulative mutation executions")
    bx.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, interval=1))
    bx.xaxis.set_major_formatter(mdates.DateFormatter("%d"))
    bx.set_xlim(d("2026-09-26"), d("2026-11-01"))
    bx.set_ylim(bottom=0)
    bx.set_yticks([0, 2000, 4000, 6000])
    bx.set_yticklabels(["0", "2,000", "4,000", "6,000"])
    bx.set_xlabel("Monday of each week, Sep–Oct 2026")
    save(fig, "fig3_negative_controls")


def fig4_reviews(md: dict) -> None:
    r = md["reviews"]
    prs = [p for p in r["per_pr"]]
    fig = fs.figure(W_FULL, 61)
    T = 9.0
    ax = fs.axes(fig, 14.0, T, 78.0, 42.0)
    fs.panel_label(fig, "a", 0, 0.4)
    y = list(range(len(prs)))[::-1]
    left = [0] * len(prs)
    for s, c in zip(SEV, SEV_COL):
        vals = [r["per_pr"][p].get(s, 0) for p in prs]
        ax.barh(y, vals, left=left, color=c, height=0.66, lw=0.4, edgecolor="white", zorder=2)
        left = [a + b for a, b in zip(left, vals)]
    for yi, p, tot in zip(y, prs, left):
        n = r["rounds_by_pr"][p]
        ax.annotate(f"{tot}", (tot, yi), xytext=(2.5, 0), textcoords="offset points", va="center", fontsize=6.5)
        ax.annotate(f"{n} round{'s' if n != 1 else ''}", (tot, yi), xytext=(13, 0), textcoords="offset points",
                    va="center", fontsize=6.5, color=fs.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels([f"PR #{p}" for p in prs])
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_ylim(-0.6, len(prs) - 0.4)
    ax.set_xlim(0, 60)
    ax.set_xlabel("Findings (severity as labelled)")
    ch = r["by_channel"]
    order = sorted(ch, key=lambda k: -sum(ch[k].values()))
    bx = fs.axes(fig, 135.0, T, 32.0, 42.0)
    fs.panel_label(fig, "b", 104.0, 0.4)
    yb = list(range(len(order)))[::-1]
    left = [0] * len(order)
    for s, c in zip(SEV, SEV_COL):
        vals = [ch[k].get(s, 0) for k in order]
        bx.barh(yb, vals, left=left, color=c, height=0.5, lw=0.4, edgecolor="white", zorder=2)
        left = [a + b for a, b in zip(left, vals)]
    for yi, t in zip(yb, left):
        bx.annotate(str(t), (t, yi), xytext=(2.5, 0), textcoords="offset points", va="center", fontsize=6.5)
    names = {"independent agent session": "Independent\nagent session",
             "browser walk-through / capture": "Browser walk-\nthrough, capture",
             "coordinating agent session": "Coordinating\nagent session"}
    bx.set_yticks(yb)
    bx.set_yticklabels([names.get(k, k) for k in order])
    bx.tick_params(axis="y", length=0)
    bx.spines["left"].set_visible(False)
    bx.set_ylim(-0.6, len(order) - 0.4)
    bx.set_xlim(0, 175)
    bx.set_xticks([0, 50, 100, 150])
    bx.set_xlabel("Findings")
    key_row(fig, 14.0, 3.2, list(zip(SEV_COL, ["Blocker", "Major", "Minor", "Nit", "Unlabelled"])))
    save(fig, "fig4_reviews")


def fig5_approvals(md: dict) -> None:
    a = md["approvals"]
    cats = ["agent-trailered commit", "local commit without agent trailer",
            "owner sign-off in GitHub web editor (verified)"]
    labels = ["Agent-trailered commit", "Local commit, no trailer,\nunsigned (8832dae)",
              "Owner sign-off, GitHub web\neditor, verified"]
    colors = [fs.OCHRE, fs.GREY_LIGHT, fs.PRIMARY]
    fig = fs.figure(W_FULL, 58)
    ax = fs.axes(fig, 13.0, 6.0, 44.0, 42.0)
    fs.panel_label(fig, "a", 0, 0.4)
    snaps = [("main @ 6209131\n17 Oct", a["lines_at_draft"]), ("main @ 8805882\n31 Oct", a["lines_at_final"])]
    mids = {}
    for i, (lab, s) in enumerate(snaps):
        bottom = 0
        for c, col in zip(cats, colors):
            v = s["by_writer"].get(c, 0)
            ax.bar(i, v, bottom=bottom, color=col, width=0.58, lw=0.4, edgecolor="white", zorder=2)
            if v >= 25:
                ax.text(i, bottom + v / 2, str(v), ha="center", va="center", fontsize=6.5,
                        color="white" if col == fs.PRIMARY else fs.INK)
            if i == 1:
                mids[c] = bottom + v / 2
            bottom += v
        ax.annotate(f"{bottom} lines\n{s['documents']} documents", (i, bottom), xytext=(0, 2), textcoords="offset points",
                    ha="center", va="bottom", fontsize=6.5, color=fs.INK2, linespacing=1.1)
    for c, lab in zip(cats, labels):
        ax.annotate(lab, (1.31, mids[c]), xytext=(8, 0), textcoords="offset points", ha="left", va="center",
                    fontsize=6.5, linespacing=1.1, annotation_clip=False,
                    arrowprops=dict(arrowstyle="-", lw=0.4, color=fs.GREY_MID, shrinkA=0, shrinkB=0))
    ax.set_xticks([0, 1])
    ax.set_xticklabels([s[0] for s in snaps])
    ax.tick_params(axis="x", length=0)
    ax.set_xlim(-0.55, 1.55)
    ax.set_ylim(0, a["lines_at_final"]["lines"] * 1.18)
    ax.set_ylabel("Approval lines")
    subs = a["signoff_substitutions"]["commits"]
    bx = fs.axes(fig, 120.0, 6.0, 40.0, 42.0)
    fs.panel_label(fig, "b", 89.0, 0.4)
    y = list(range(len(subs)))[::-1]
    place = [s["by_kind"].get("approval placeholder", 0) for s in subs]
    other = [s["occurrences_replaced"] - p for s, p in zip(subs, place)]
    bx.barh(y, place, color=fs.PRIMARY, height=0.58, lw=0, zorder=2)
    bx.barh(y, other, left=place, color=fs.BRICK, height=0.58, lw=0, zorder=2)
    for yi, p, o in zip(y, place, other):
        bx.annotate(f"{p + o}", (p + o, yi), xytext=(2.5, 0), textcoords="offset points", va="center", fontsize=6.5)
        if o:
            bx.annotate(f"{o} not a placeholder", (p + o, yi), xytext=(2.5, -6.2), textcoords="offset points",
                        va="center", fontsize=6, color=fs.BRICK)
    bx.set_yticks(y)
    bx.set_yticklabels([f"{s['sha']} ({datetime.fromisoformat(s['date']).strftime('%d %b')})\n"
                        + ("GitHub web, verified" if s["committer"] == "GitHub" else "local, unsigned") for s in subs],
                       fontsize=6.5)
    bx.tick_params(axis="y", length=0)
    bx.spines["left"].set_visible(False)
    bx.set_ylim(-0.6, len(subs) - 0.4)
    bx.set_xlim(0, 320)
    bx.set_xticks([0, 100, 200, 300])
    bx.set_xlabel("'PENDING owner approval' replaced")
    save(fig, "fig5_approvals")


def fig6_verification(rs: dict) -> None:
    h = rs["rq3_verification"]["rcv_headline"]["rows"]
    cats = ["Verified", "Partial", "Overstated / not implemented"]
    fig = fs.figure(W_FULL, 56)
    ax = fs.axes(fig, 13.0, 6.0, 58.0, 36.0)
    fs.panel_label(fig, "a", 0, 0.4)
    xs = range(len(cats))
    w = 0.36
    before = [h[c]["recorded_2026_04_12"] for c in cats]
    after = [h[c]["reverified_2026_07_18"] for c in cats]
    ax.bar([x - w / 2 for x in xs], before, width=w - 0.03, color=fs.GREY_LIGHT, lw=0, zorder=2)
    ax.bar([x + w / 2 for x in xs], after, width=w - 0.03, color=fs.PRIMARY, lw=0, zorder=2)
    for x, b, a2 in zip(xs, before, after):
        ax.annotate(str(b), (x - w / 2, b), xytext=(0, 1.5), textcoords="offset points", ha="center", va="bottom",
                    fontsize=6.5, color=fs.INK2)
        ax.annotate(str(a2), (x + w / 2, a2), xytext=(0, 1.5), textcoords="offset points", ha="center", va="bottom",
                    fontsize=6.5, color=fs.INK2)
    ax.annotate("Recorded, Apr 2026 (prose)", (0 - w / 2, before[0]), xytext=(10, 1.5), textcoords="offset points",
                ha="left", va="center", fontsize=6.5, color=fs.INK)
    ax.annotate("Re-verified, Jul 2026\n(adversarial)", (2 + w / 2, after[2]), xytext=(0, 9),
                textcoords="offset points", ha="center", va="bottom", fontsize=6.5, color=fs.INK, linespacing=1.1)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(["Verified", "Partial", "Overstated or\nnot implemented"])
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Risk controls (of 22)")
    ax.set_ylim(0, 24)
    ax.set_yticks([0, 5, 10, 15, 20])
    vals = rs["rq2_failures"]["summary"]["days_to_detection_by_stage"]
    bx = fs.axes(fig, 104.0, 6.0, 64.0, 36.0)
    fs.panel_label(fig, "b", 82.0, 0.4)
    for i, (stage, col, lab) in enumerate((("escaped", fs.BRICK, "Escaped to main"),
                                           ("contained", fs.TEAL, "Contained before merge"))):
        v = sorted(vals[stage]["values"])
        jit = fs.jitter(len(v), 0.42, phase=0.3 * i)
        bx.scatter(v, [i + j for j in jit], s=9, color=col, edgecolor="white", linewidth=0.4, zorder=3)
        med = vals[stage]["median"]
        bx.plot([med, med], [i - 0.3, i + 0.3], color=fs.INK, lw=1.0, zorder=4)
        bx.annotate(f"n = {vals[stage]['n']}, median {med} d", (min(v), i + 0.3), xytext=(0, 1.5),
                    textcoords="offset points", ha="left", va="bottom", fontsize=6.5, color=fs.INK2)
    bx.set_yticks([0, 1])
    bx.set_yticklabels(["Escaped\nto main", "Contained\nbefore merge"])
    bx.tick_params(axis="y", length=0)
    bx.spines["left"].set_visible(False)
    bx.set_xlim(-8, 300)
    bx.set_ylim(-0.6, 1.6)
    bx.set_xlabel("Days from introducing to detecting commit")
    save(fig, "fig6_verification")


def fig7_channels(md: dict) -> None:
    rc = md["record_channels"]
    names = {"BC": "Browser capture of a release build\n(filming the application)",
             "AR": "Independent or adversarial review\n(separate agent session)",
             "RS": "Owner's research studies\n(papers A, C, D, H)",
             "IM": "Incidental, while implementing", "BP": "Behaviour probe (requests, real browser)",
             "CR": "Code reading, orchestrating session", "EX": "External literature research"}
    order = sorted(rc["by_channel"], key=lambda k: rc["by_channel"][k])
    fig = fs.figure(W_ONEHALF, 58)
    ax = fs.axes(fig, 52.0, 3.0, 70.0, 44.0)
    y = list(range(len(order)))
    capa = [rc["by_kind"].get("CAPA", {}).get(k, 0) for k in order]
    prb = [rc["by_kind"].get("PRB", {}).get(k, 0) for k in order]
    ax.barh(y, capa, color=fs.PRIMARY, height=0.62, lw=0.4, edgecolor="white", zorder=2)
    ax.barh(y, prb, left=capa, color=fs.OCHRE, height=0.62, lw=0.4, edgecolor="white", zorder=2)
    for i, (c, p) in enumerate(zip(capa, prb)):
        ax.annotate(str(c + p), (c + p, i), xytext=(2.5, 0), textcoords="offset points", va="center", fontsize=6.5)
    i_ar = order.index("AR")
    ax.text(capa[i_ar] / 2, i_ar, "CAPA", ha="center", va="center", fontsize=6.5, color="white", zorder=3)
    ax.text(capa[i_ar] + prb[i_ar] / 2, i_ar, "PRB", ha="center", va="center", fontsize=6.5, color=fs.INK, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([names[k] for k in order], fontsize=6.5)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_ylim(-0.6, len(order) - 0.4)
    ax.set_xlim(0, 15)
    ax.set_xticks([0, 2, 4, 6, 8, 10, 12, 14])
    ax.set_xlabel("Records (CAPA-001 to 016, PRB-001 to 031)")
    save(fig, "fig7_channels")


def fig8_tests_ci(md: dict) -> None:
    t = md["tests_weekly"]
    fig = fs.figure(W_FULL, 53)
    ax = fs.axes(fig, 13.0, 4.0, 55.0, 38.0)
    fs.panel_label(fig, "a", 0, 0.4)
    x = [d(p["date"]) for p in t]
    ax.plot(x, [p["backend_test_functions"] for p in t], color=fs.PRIMARY, drawstyle="steps-post", lw=fs.LW_DATA)
    ax.plot(x, [p["frontend_test_cases"] for p in t], color=fs.OCHRE, drawstyle="steps-post", lw=fs.LW_DATA)
    end_label(ax, x[-1], t[-1]["backend_test_functions"], f"Backend test functions {t[-1]['backend_test_functions']:,}"
              .replace(",", ","), dx=3)
    end_label(ax, x[-1], t[-1]["frontend_test_cases"], f"Frontend test cases {t[-1]['frontend_test_cases']}", dx=3)
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
    ax.figure.canvas.draw()
    labs = []
    for tk in ax.get_xticks():
        dt = mdates.num2date(tk)
        labs.append(dt.strftime("%b") + (f"\n{dt.year}" if dt.month == 1 or not labs else ""))
    ax.set_xticks(ax.get_xticks())
    ax.set_xticklabels(labs)
    ax.set_ylim(0, 1600)
    ax.set_yticks([0, 500, 1000, 1500])
    ax.set_yticklabels(["0", "500", "1,000", "1,500"])
    ax.set_ylabel("Tests declared in the tree")
    c = md["ci"]["by_month"]
    months = list(c)
    xs = range(len(months))
    s = [c[m].get("success", 0) for m in months]
    f = [c[m].get("failure", 0) for m in months]
    k = [c[m].get("cancelled", 0) for m in months]
    bx = fs.axes(fig, 121.0, 4.0, 38.0, 38.0)
    fs.panel_label(fig, "b", 101.0, 0.4)
    bx.bar(xs, s, color=fs.TEAL, width=0.62, lw=0.4, edgecolor="white", zorder=2)
    bx.bar(xs, f, bottom=s, color=fs.BRICK, width=0.62, lw=0.4, edgecolor="white", zorder=2)
    bx.bar(xs, k, bottom=[a + b for a, b in zip(s, f)], color=fs.GREY_LIGHT, width=0.62, lw=0.4, edgecolor="white",
           zorder=2)
    for i, (a1, b1, c1) in enumerate(zip(s, f, k)):
        bx.annotate(f"{a1}/{a1 + b1 + c1}", (i, a1 + b1 + c1), xytext=(0, 1.5), textcoords="offset points",
                    ha="center", va="bottom", fontsize=6.5, color=fs.INK2)
    # direct labels on the April bar, which has all three outcomes
    for val, base, lab in ((s[0], 0, "Success"), (f[0], s[0], "Failure"), (k[0], s[0] + f[0], "Cancelled")):
        bx.annotate(lab, (-0.31, base + val / 2), xytext=(-3, 0), textcoords="offset points", ha="right",
                    va="center", fontsize=6.5, annotation_clip=False)
    bx.set_xticks(list(xs))
    bx.set_xlim(-0.6, len(months) - 0.2)
    bx.set_xticklabels([datetime.fromisoformat(m + "-01").strftime("%b") for m in months])
    bx.tick_params(axis="x", length=0)
    bx.set_ylim(0, max(a1 + b1 + c1 for a1, b1, c1 in zip(s, f, k)) * 1.12)
    bx.set_ylabel("CI runs per month")
    bx.yaxis.set_label_position("right")
    bx.yaxis.tick_right()
    bx.spines["left"].set_visible(False)
    bx.spines["right"].set_visible(True)
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
