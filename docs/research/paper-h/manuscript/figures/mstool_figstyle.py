"""MSTool-AI house style for journal figures - one module shared by every paper (A, F, H, negative results).

The same file and its companion ``mstool.mplstyle`` are copied into each paper's figure folder, so every
paper builds offline from its own branch. Change them in one place and copy again; do not fork them.

    import mstool_figstyle as fs
    fs.use()                                     # Arial, 7 pt ticks / 8 pt labels, 0.5 pt axes, white ground
    fig = fs.figure(fs.DOUBLE, 70)               # exact FINAL size in mm (never rescaled afterwards)
    ax = fs.axes(fig, 14, 4, 70, 50)             # left, top, width, height in mm from the top-left corner
    fs.panel_label(fig, "a", 1, 1)               # bold 9 pt lowercase panel letter, mm from the top-left
    fs.save(fig, "figures/fig1_name")            # vector PDF (TrueType 42, fonts embedded) + 600 dpi PNG

Rules this module enforces or makes easy
  * Widths: single column 88 mm, 1.5 column 130 mm (120-140), double column 180 mm.
  * No titles inside plots and no explanatory footnotes: the message and the notes live in the caption.
    Facet labels (a site, an alpha) are small regular-weight text, not titles.
  * Direct labels instead of legends wherever possible (``spread`` keeps end-of-line labels apart).
  * Numbers: real minus (U+2212); confidence intervals with an en dash ("0.70–0.75"), or "to" when a
    bound is negative ("−0.21 to −0.14", the Lancet/NEJM convention), decimal-aligned in columns.
  * ``save`` refuses to write a figure whose text leaves the canvas, and reports overlapping labels.

Palette - muted, colour-blind safe. Every pair inside a semantic group keeps CIEDE2000 >= 12 after
Machado et al. (2009) simulation of deuteranopia, protanopia and tritanopia (checked by ``cvd_report``);
every series also has its own marker, so no meaning rests on colour alone.
  FLAMeS 5-fold ensemble (the reference)  dark grey  #3B3B3B   - in every paper
  FLAMeS fold 0 (single model)            mid grey   #8E8E8E
  MindGlide                               blue       #2F5D8A   (= primary accent)
  MindGlide, raw input                    light blue #93B4D4
  WMH-SynthSeg                            ochre      #D8A84E   (= secondary accent)
  SAMSEG                                  umber      #80513A
  LST-AI                                  mauve      #B5739E
  met / holds  -  inconclusive  -  not met / violated:  teal #3A8A78 - grey #A3A3A3 - brick #B9503C
"""
from __future__ import annotations

import itertools
import math
import os
from decimal import ROUND_HALF_UP, Decimal

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.text import Text
from matplotlib.transforms import blended_transform_factory

HERE = os.path.dirname(os.path.abspath(__file__))
STYLE_FILE = os.path.join(HERE, "mstool.mplstyle")

# ------------------------------------------------------------------------------------------- sizes (mm)
MM = 1 / 25.4
SINGLE, ONE_HALF, DOUBLE = 88.0, 130.0, 180.0
MAX_HEIGHT = 230.0

# ------------------------------------------------------------------------------------------- type
FS_TICK, FS_LABEL, FS_PANEL, FS_NOTE = 7.0, 8.0, 9.0, 6.5

# ------------------------------------------------------------------------------------------- ink
INK = "#1A1A1A"          # text and data ink
INK2 = "#5E5E5E"         # secondary text (facet labels, column heads, value labels)
AXIS = "#262626"
REFLINE = "#8C8C8C"      # reference lines (null, nominal level) - thin and quiet
GRID = "#ECECEC"         # used sparingly
BAND = "#EDEDED"         # equivalence margins, pre-registered bands - very light
WHITE = "#FFFFFF"

# ------------------------------------------------------------------------------------------- palette
FLAMES = "#3B3B3B"
FLAMES_FOLD0 = "#8E8E8E"
BLUE, BLUE_LIGHT, BLUE_DARK = "#2F5D8A", "#93B4D4", "#1B3A5C"
OCHRE, OCHRE_DARK = "#D8A84E", "#A9792A"
UMBER = "#80513A"
MAUVE = "#B5739E"
TEAL, BRICK = "#3A8A78", "#B9503C"
GREY_MID, GREY_LIGHT = "#A3A3A3", "#D5D5D5"
PRIMARY, SECONDARY = BLUE, OCHRE
ORDINAL4 = ("#122D4A", "#2F5D8A", "#5F8AB8", "#9AB8D8")     # one-hue ramp for ordered categories

TOOLS = {   # fixed identity of every segmentation tool, the same in every paper
    "flames": dict(color=FLAMES, marker="o", name="FLAMeS"),
    "flames-fold0": dict(color=FLAMES_FOLD0, marker="o", name="FLAMeS fold 0"),
    "mindglide": dict(color=BLUE, marker="s", name="MindGlide"),
    "mindglide-raw": dict(color=BLUE_LIGHT, marker="D", name="MindGlide, raw input"),
    "wmhsynthseg": dict(color=OCHRE, marker="^", name="WMH-SynthSeg"),
    "samseg": dict(color=UMBER, marker="v", name="SAMSEG"),
    "lstai": dict(color=MAUVE, marker="P", name="LST-AI"),
}
STATUS = {  # one consistent pair (plus a neutral) for every met / not-met reading
    "met": dict(color=TEAL, marker="o"),
    "inconclusive": dict(color=GREY_MID, marker="D"),
    "not_met": dict(color=BRICK, marker="s"),
}

MS = 4.2          # default marker size (pt)
MEW = 0.5         # marker edge width (pt)
LW_DATA = 1.0     # data lines
LW_CI = 0.75      # confidence-interval whiskers
LW_CI_THICK = 2.2 # inner (e.g. 90 %) interval
LW_REF = 0.5      # reference lines


def use() -> None:
    """Apply the house rcParams (from mstool.mplstyle next to this file)."""
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    matplotlib.use("Agg")
    plt.style.use(STYLE_FILE)


# ------------------------------------------------------------------------------------------- layout in mm
def figure(width_mm: float, height_mm: float):
    if width_mm > DOUBLE + 0.01 or height_mm > MAX_HEIGHT:
        raise ValueError(f"figure {width_mm} x {height_mm} mm exceeds the journal page")
    fig = plt.figure(figsize=(width_mm * MM, height_mm * MM))
    fig._mm = (width_mm, height_mm)
    return fig


def axes(fig, left: float, top: float, width: float, height: float, **kw):
    """Add axes at an exact position, in mm measured from the figure's top-left corner."""
    W, H = fig._mm
    return fig.add_axes([left / W, 1 - (top + height) / H, width / W, height / H], **kw)


def fx(fig, x_mm: float) -> float:
    return x_mm / fig._mm[0]


def fy(fig, y_mm_from_top: float) -> float:
    return 1 - y_mm_from_top / fig._mm[1]


def text_mm(fig, x_mm: float, y_mm: float, s: str, **kw):
    kw.setdefault("va", "top")
    kw.setdefault("ha", "left")
    return fig.text(fx(fig, x_mm), fy(fig, y_mm), s, **kw)


def panel_label(fig, letter: str, x_mm: float, y_mm: float):
    """Bold 9 pt lowercase panel letter; (x, y) is its top-left corner in mm."""
    return text_mm(fig, x_mm, y_mm, letter, fontsize=FS_PANEL, fontweight="bold", color=INK)


def facet_label(ax, s: str, x: float = 0.0, y: float = 1.0, pad_pt: float = 3, **kw):
    """Small regular-weight label above a facet (a site, an alpha) - a label, not a title."""
    kw.setdefault("fontsize", FS_TICK)
    kw.setdefault("color", INK)
    kw.setdefault("ha", "left")
    return ax.annotate(s, (x, y), xycoords="axes fraction", xytext=(0, pad_pt), textcoords="offset points",
                       va="bottom", **kw)


def despine(ax, left: bool = True, bottom: bool = True) -> None:
    ax.spines["left"].set_visible(left)
    ax.spines["bottom"].set_visible(bottom)
    if not left:
        ax.tick_params(axis="y", length=0)
    if not bottom:
        ax.tick_params(axis="x", length=0)


def outward(ax, pt: float = 2.0) -> None:
    """Offset the left and bottom spines outward a little (detached axes, as in print journals)."""
    for s in ("left", "bottom"):
        ax.spines[s].set_position(("outward", pt))


def ref_vline(ax, x: float, **kw):
    kw.setdefault("color", REFLINE)
    kw.setdefault("lw", LW_REF)
    kw.setdefault("zorder", 1)
    return ax.axvline(x, **kw)


def ref_hline(ax, y: float, **kw):
    kw.setdefault("color", REFLINE)
    kw.setdefault("lw", LW_REF)
    kw.setdefault("zorder", 1)
    return ax.axhline(y, **kw)


def band_v(ax, lo: float, hi: float, **kw):
    kw.setdefault("color", BAND)
    kw.setdefault("lw", 0)
    kw.setdefault("zorder", 0)
    return ax.axvspan(lo, hi, **kw)


def text_color(color: str) -> str:
    """A legible text shade of a series colour (light hues are darkened for type on white)."""
    r, g, b = matplotlib.colors.to_rgb(color)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    k = 0.0 if lum < 0.35 else 0.45 if lum > 0.55 else 0.25
    return matplotlib.colors.to_hex((r * (1 - k), g * (1 - k), b * (1 - k)))


def spread(values, min_gap: float, lo: float | None = None, hi: float | None = None):
    """Move 1-D label positions apart by at least ``min_gap`` (order kept, mean shift minimal)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    pos = [float(values[i]) for i in order]
    for _ in range(200):
        moved = False
        for i in range(1, len(pos)):
            if pos[i] - pos[i - 1] < min_gap - 1e-12:
                mid = (pos[i] + pos[i - 1]) / 2
                pos[i - 1], pos[i] = mid - min_gap / 2, mid + min_gap / 2
                moved = True
        if lo is not None and pos[0] < lo:
            shift = lo - pos[0]
            pos = [p + shift for p in pos]
        if hi is not None and pos[-1] > hi:
            shift = pos[-1] - hi
            pos = [p - shift for p in pos]
        if not moved:
            break
    out = [0.0] * len(values)
    for k, i in enumerate(order):
        out[i] = pos[k]
    return out


def jitter(n: int, width: float, phase: float = 0.0):
    """Deterministic, evenly spread jitter in [-width/2, width/2] (golden-ratio sequence)."""
    g = (math.sqrt(5) - 1) / 2
    return np.array([((phase + (i + 1) * g) % 1.0 - 0.5) * width for i in range(n)])


# ------------------------------------------------------------------------------------------- numbers
def minus(s: str) -> str:
    """Typographic minus for numbers (a hyphen before a digit or a decimal point)."""
    out = []
    for i, ch in enumerate(s):
        nxt = s[i + 1] if i + 1 < len(s) else ""
        out.append("−" if ch == "-" and (nxt.isdigit() or nxt == ".") else ch)
    return "".join(out)


def fnum(x: float, nd: int, sign: bool = False, half_up: bool = False) -> str:
    """Format with ``nd`` decimals and a real minus. ``half_up`` rounds the stored decimal value half-up
    (as text written from the same record does); otherwise Python's float formatting is used."""
    if half_up:
        q = Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP)
        s = f"{q:f}"
        if s.startswith("-") and q == 0:
            s = s[1:]
        if sign and not s.startswith("-"):
            s = "+" + s
    else:
        s = f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"
        if s in ("-0." + "0" * nd, "+-0." + "0" * nd):
            s = ("+" if sign else "") + "0." + "0" * nd
    return minus(s)


def ci_sep(*bounds) -> str:
    """En dash between bounds, or ' to ' when any bound is negative (avoids '−0.21–−0.14')."""
    return " to " if any(b < 0 for b in bounds) else "–"


def dtext(ax, x, y, s: str, transform=None, **kw):
    """Draw ``s`` with its first decimal point at x (decimal alignment); no point -> right-aligned at x."""
    kw.setdefault("va", "center")
    kw.setdefault("fontsize", FS_TICK)
    kw.setdefault("color", INK)
    tr = transform if transform is not None else ax.transData
    if "." in s:
        i = s.index(".")
        a = ax.text(x, y, s[:i], ha="right", transform=tr, **kw)
        b = ax.text(x, y, s[i:], ha="left", transform=tr, **kw)
        return a, b
    return (ax.text(x, y, s, ha="right", transform=tr, **kw),)


def xcol(ax):
    """Transform for table columns beside an axes: x in axes fraction, y in data units."""
    return blended_transform_factory(ax.transAxes, ax.transData)


def mm_to_axfrac(ax, fig, mm: float) -> float:
    """Width of ``mm`` millimetres expressed as a fraction of the axes width."""
    W, _ = fig._mm
    return mm / (ax.get_position().width * W)


def text_width_mm(fig, s: str, fontsize: float = FS_TICK, **kw) -> float:
    """Rendered width of ``s`` in mm (Arial metrics, so table columns are set from real widths)."""
    r = fig.canvas.get_renderer()
    t = fig.text(0, 0, s, fontsize=fontsize, **kw)
    w = t.get_window_extent(r).width / fig.dpi * 25.4
    t.remove()
    return w


def _split_dec(s: str):
    return (s[:s.index(".")], s[s.index("."):]) if "." in s else (s, "")


def table_layout(fig, x0: float, columns, kinds: str, gaps, fontsize: float = FS_TICK):
    """Lay out text columns from x0 (mm). ``columns`` is a list of columns (each a list of strings),
    ``kinds`` one letter per column: d = decimal-aligned, l = left, r = right, c = centred; ``gaps`` the
    space (mm) after each column. Returns (anchors, x_end): the x (mm) of each column's anchor -
    the decimal point for d, the left edge for l, right edge for r, centre for c."""
    anchors, x = [], x0
    if isinstance(gaps, (int, float)):
        gaps = [gaps] * len(columns)
    for col, kind, gap in zip(columns, kinds, gaps):
        if kind == "d":
            wi = max(text_width_mm(fig, _split_dec(s)[0], fontsize) for s in col)
            wf = max((text_width_mm(fig, _split_dec(s)[1], fontsize) if _split_dec(s)[1] else 0.0) for s in col)
            # strings without a point are right-aligned on the decimal anchor
            anchors.append(x + wi)
            x += wi + wf + gap
        else:
            w = max(text_width_mm(fig, s, fontsize) for s in col)
            anchors.append({"l": x, "r": x + w, "c": x + w / 2}[kind])
            x += w + gap
    return anchors, x - (gaps[-1] if gaps else 0)


def table_row(fig, anchors, kinds: str, y_mm: float, cells, fontsize: float = FS_TICK, color: str = INK, **kw):
    """Draw one row of a ``table_layout`` table at height y_mm (centre of the text)."""
    for x, kind, s in zip(anchors, kinds, cells):
        if s is None or s == "":
            continue
        if kind == "d":
            a, b = _split_dec(s)
            text_mm(fig, x, y_mm, a, ha="right", va="center", fontsize=fontsize, color=color, **kw)
            if b:
                text_mm(fig, x, y_mm, b, ha="left", va="center", fontsize=fontsize, color=color, **kw)
        else:
            text_mm(fig, x, y_mm, s, ha={"l": "left", "r": "right", "c": "center"}[kind], va="center",
                    fontsize=fontsize, color=color, **kw)


def ci_cells(est: float, lo: float, hi: float, nd: int, sign: bool = True, sep: str | None = None,
             half_up: bool = False):
    """Cells [estimate, '(lo', sep, 'hi)'] for a decimal-aligned estimate (95% CI) column group."""
    sep = (sep if sep is not None else ci_sep(lo, hi)).strip()
    f = lambda v: fnum(v, nd, sign=sign, half_up=half_up)  # noqa: E731
    return [f(est), "(" + f(lo), sep, f(hi) + ")"]


# ------------------------------------------------------------------------------------------- checks + save
def _texts(fig):
    out = []
    for t in fig.findobj(Text):
        if not t.get_visible() or not t.get_text().strip():
            continue
        out.append(t)
    return out


def _leader(t, r):
    """Display-space end points of an annotation's leader line, or None."""
    ap = getattr(t, "arrow_patch", None)
    if ap is None or not ap.get_visible():
        return None
    try:
        path = ap._get_path_in_displaycoord()
        path = path[0] if isinstance(path, tuple) else path
        if isinstance(path, list):
            path = path[0]
        v = path.vertices
    except Exception:  # pragma: no cover - matplotlib internals
        return None
    return (float(v[0][0]), float(v[0][1])), (float(v[-1][0]), float(v[-1][1]))


def _cross(p1, p2, q1, q2) -> bool:
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2 = orient(q1, q2, p1), orient(q1, q2, p2)
    d3, d4 = orient(p1, p2, q1), orient(p1, p2, q2)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def _seg_hits_box(p, q, bb, shrink=1.0) -> bool:
    x0, y0, x1, y1 = bb.x0 + shrink, bb.y0 + shrink, bb.x1 - shrink, bb.y1 - shrink
    if x0 >= x1 or y0 >= y1:
        return False
    for t in [i / 40 for i in range(41)]:
        x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        if x0 < x < x1 and y0 < y < y1:
            return True
    return False


def check_layout(fig, name: str = "", tolerance_px: float = 0.5, strict: bool = True):
    """Collision check before saving. Raises if text leaves the canvas, if two text boxes overlap, if two
    leader lines cross, or if a leader line runs through another label (text boxes only, arrows excluded)."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    W, H = fig.bbox.width, fig.bbox.height
    boxes, leaders = [], []
    problems = []
    for t in _texts(fig):
        bb = Text.get_window_extent(t, r)          # the text itself, without any leader line
        if bb.width <= 0 or bb.height <= 0:
            continue
        if bb.x0 < -tolerance_px or bb.y0 < -tolerance_px or bb.x1 > W + tolerance_px or bb.y1 > H + tolerance_px:
            problems.append(f"outside canvas: {t.get_text()!r} {bb.bounds}")
        boxes.append((t, bb))
        seg = _leader(t, r)
        if seg:
            leaders.append((t, seg))
    if problems:
        raise RuntimeError(f"[{name}] text clipped by the canvas:\n  " + "\n  ".join(problems))
    issues = []
    for (t1, b1), (t2, b2) in itertools.combinations(boxes, 2):
        ix = min(b1.x1, b2.x1) - max(b1.x0, b2.x0)
        iy = min(b1.y1, b2.y1) - max(b1.y0, b2.y0)
        if ix > 1.0 and iy > 1.0:
            issues.append(f"text overlap {t1.get_text()!r} / {t2.get_text()!r} ({round(ix * iy)} px^2)")
    for (t1, s1), (t2, s2) in itertools.combinations(leaders, 2):
        if _cross(*s1, *s2):
            issues.append(f"leader lines cross: {t1.get_text()!r} / {t2.get_text()!r}")
    for t1, s1 in leaders:
        for t2, b2 in boxes:
            if t2 is not t1 and _seg_hits_box(*s1, b2):
                issues.append(f"leader of {t1.get_text()!r} runs through {t2.get_text()!r}")
    for msg in issues:
        print(f"   [{name}] {msg}")
    if issues and strict:
        raise RuntimeError(f"[{name}] {len(issues)} label collision(s); fix the layout before saving")
    return issues


def save(fig, stem: str, png_dpi: int = 600, check: bool = True, strict: bool = True) -> list[str]:
    """Write ``stem.pdf`` (vector, TrueType embedded) and ``stem.png`` (600 dpi) at the exact figure size,
    after the collision check (``strict``: refuse to write a figure with overlapping or crossing labels)."""
    name = os.path.basename(stem)
    if check:  # MSTOOL_FIG_REPORT=1 lists every collision without stopping (for a survey of all figures)
        check_layout(fig, name, strict=strict and os.environ.get("MSTOOL_FIG_REPORT") != "1")
    pdf, png = stem + ".pdf", stem + ".png"
    fig.savefig(pdf, metadata={"Creator": "mstool_figstyle (matplotlib)", "CreationDate": None})
    fig.savefig(png, dpi=png_dpi, metadata={"Software": "mstool_figstyle (matplotlib)"})
    plt.close(fig)
    print("wrote", pdf, "and", os.path.basename(png))
    return [pdf, png]


# ------------------------------------------------------------------------------------------- palette audit
def cvd_report(groups: dict[str, dict[str, str]], floor: float = 12.0) -> bool:
    """CIEDE2000 between every pair of each group under normal, deutan, protan and tritan vision."""
    M = {
        "deutan": np.array([[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413],
                            [-0.011820, 0.042940, 0.968881]]),
        "protan": np.array([[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216],
                            [-0.003882, -0.048116, 1.051998]]),
        "tritan": np.array([[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602],
                            [0.004733, 0.691367, 0.303900]]),
    }

    def lin(c):
        return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

    def delin(c):
        return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.clip(c, 0, 1) ** (1 / 2.4) - 0.055)

    def lab(rgb):
        xyz = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                        [0.0193339, 0.1191920, 0.9503041]]) @ lin(rgb) / np.array([0.95047, 1.0, 1.08883])
        f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
        return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])

    def de(l1, l2):
        L1, a1, b1 = l1
        L2, a2, b2 = l2
        Cb = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
        G = 0.5 * (1 - math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
        a1p, a2p = (1 + G) * a1, (1 + G) * a2
        C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
        h1p, h2p = math.degrees(math.atan2(b1, a1p)) % 360, math.degrees(math.atan2(b2, a2p)) % 360
        dLp, dCp = L2 - L1, C2p - C1p
        dhp = 0.0 if C1p * C2p == 0 else (h2p - h1p + 180) % 360 - 180
        dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))
        Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
        hbp = h1p + h2p if C1p * C2p == 0 else ((h1p + h2p) / 2 if abs(h1p - h2p) <= 180 else
                                                 (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2)
        T = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
             + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
        Rc = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
        Sl = 1 + 0.015 * (Lbp - 50) ** 2 / math.sqrt(20 + (Lbp - 50) ** 2)
        Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
        Rt = -math.sin(math.radians(60 * math.exp(-((hbp - 275) / 25) ** 2))) * Rc
        return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))

    ok = True
    for gname, pal in groups.items():
        for kind in ("normal", "deutan", "protan", "tritan"):
            worst = (1e9, "", "")
            for (n1, c1), (n2, c2) in itertools.combinations(pal.items(), 2):
                rgb1, rgb2 = (np.array(matplotlib.colors.to_rgb(c)) for c in (c1, c2))
                if kind != "normal":
                    rgb1, rgb2 = (np.clip(delin(np.clip(M[kind] @ lin(c), 0, 1)), 0, 1) for c in (rgb1, rgb2))
                d = de(lab(rgb1), lab(rgb2))
                worst = min(worst, (d, n1, n2))
            flag = "ok " if worst[0] >= floor else "LOW"
            ok &= worst[0] >= floor
            print(f"  {gname:28s} {kind:7s} {flag} min CIEDE2000 {worst[0]:5.1f}  ({worst[1]} / {worst[2]})")
    return ok


PALETTE_GROUPS = {
    "tools": {k: v["color"] for k, v in TOOLS.items() if k != "flames-fold0"},
    "flames arms + accents": {"FLAMeS": FLAMES, "fold 0": FLAMES_FOLD0, "primary": PRIMARY, "secondary": SECONDARY},
    "status": {k: v["color"] for k, v in STATUS.items()},
    "ordinal ramp": dict(zip("abcd", ORDINAL4)),
}

if __name__ == "__main__":
    print("palette check (Machado 2009 severity 1.0; floor CIEDE2000 12):")
    print("ALL PASS" if cvd_report(PALETTE_GROUPS) else "SOME PAIRS BELOW FLOOR")
