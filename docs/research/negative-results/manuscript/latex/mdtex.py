"""mdtex — put a reviewed manuscript.md into a journal's official LaTeX template without changing its text.

Shared by the build_latex.py of each paper (MELBA melba.cls, Elsevier elsarticle.cls, Springer Nature
sn-jnl.cls). Steps:

1. split manuscript.md into the parts a template needs (abstract, keywords, highlights, body,
   declarations, references position, figure legends) - the text itself is not edited;
2. convert each part with pandoc + md2tex.lua (headings, tables, figures, long code) and natbib citations;
3. fill the template, declare every non-ASCII character for pdfLaTeX (newunicodechar), copy the vector
   figures and a pdfLaTeX-safe copy of references.bib next to main.tex (no sub-folders);
4. compile with latexmk and report undefined citations/references, overfull boxes, missing characters,
   floats that do not fit, and the page count;
5. prove the text is unchanged: the words of manuscript.md (pandoc AST) are compared with the words of
   the generated LaTeX; every difference is listed in TEXT_CHECK.md (expected ones: the template's own
   headings and the internal notes that are not part of a submission).
"""
import collections
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PANDOC = os.environ.get("PANDOC", "pandoc")

# ------------------------------------------------------------------ characters for pdfLaTeX
# Latin letters with accents are handled by inputenc/T1; everything else is declared here.
UNI = {
    "\u00a0": "~", "\u2009": "\\,", "\u202f": "\\,", "\u2002": "\\enspace{}", "\u2003": "\\quad{}", "\u200b": "{}",
    "\u2011": "-", "\u2010": "-", "\u2012": "--", "\u2212": "\\ensuremath{-}", "\u00ad": "\\-",
    "\u2190": "\\ensuremath{\\leftarrow}", "\u2192": "\\ensuremath{\\rightarrow}", "\u2194": "\\ensuremath{\\leftrightarrow}",
    "\u21d2": "\\ensuremath{\\Rightarrow}", "\u21d0": "\\ensuremath{\\Leftarrow}", "\u21d4": "\\ensuremath{\\Leftrightarrow}",
    "\u2191": "\\ensuremath{\\uparrow}", "\u2193": "\\ensuremath{\\downarrow}", "\u21a6": "\\ensuremath{\\mapsto}",
    "\u2264": "\\ensuremath{\\leq}", "\u2265": "\\ensuremath{\\geq}", "\u2260": "\\ensuremath{\\neq}", "\u2248": "\\ensuremath{\\approx}",
    "\u2261": "\\ensuremath{\\equiv}", "\u223c": "\\ensuremath{\\sim}", "\u2243": "\\ensuremath{\\simeq}", "\u221d": "\\ensuremath{\\propto}",
    "\u226a": "\\ensuremath{\\ll}", "\u226b": "\\ensuremath{\\gg}", "\u2208": "\\ensuremath{\\in}", "\u2209": "\\ensuremath{\\notin}",
    "\u2229": "\\ensuremath{\\cap}", "\u222a": "\\ensuremath{\\cup}", "\u2282": "\\ensuremath{\\subset}", "\u2286": "\\ensuremath{\\subseteq}",
    "\u2205": "\\ensuremath{\\emptyset}", "\u221e": "\\ensuremath{\\infty}", "\u221a": "\\ensuremath{\\surd}", "\u2211": "\\ensuremath{\\sum}",
    "\u220f": "\\ensuremath{\\prod}", "\u2202": "\\ensuremath{\\partial}", "\u2207": "\\ensuremath{\\nabla}", "\u2200": "\\ensuremath{\\forall}",
    "\u2203": "\\ensuremath{\\exists}", "\u00ac": "\\ensuremath{\\neg}", "\u2227": "\\ensuremath{\\wedge}", "\u2228": "\\ensuremath{\\vee}",
    "\u22c5": "\\ensuremath{\\cdot}", "\u2219": "\\ensuremath{\\cdot}", "\u2218": "\\ensuremath{\\circ}", "\u2032": "\\ensuremath{'}",
    "\u2033": "\\ensuremath{''}", "\u2016": "\\ensuremath{\\|}", "\u27e8": "\\ensuremath{\\langle}", "\u27e9": "\\ensuremath{\\rangle}",
    "\u2308": "\\ensuremath{\\lceil}", "\u2309": "\\ensuremath{\\rceil}", "\u230a": "\\ensuremath{\\lfloor}", "\u230b": "\\ensuremath{\\rfloor}",
    "\u2223": "\\ensuremath{\\mid}", "\u2225": "\\ensuremath{\\parallel}", "\u22a5": "\\ensuremath{\\perp}", "\u2295": "\\ensuremath{\\oplus}",
    "\u2297": "\\ensuremath{\\otimes}", "\u2026": "\\ldots{}", "\u22ef": "\\ensuremath{\\cdots}", "\u00b1": "\\ensuremath{\\pm}",
    "\u2213": "\\ensuremath{\\mp}", "\u00d7": "\\ensuremath{\\times}", "\u00f7": "\\ensuremath{\\div}", "\u00b7": "\\ensuremath{\\cdot}",
    "\u2022": "\\textbullet{}", "\u25cf": "\\ensuremath{\\bullet}", "\u25cb": "\\ensuremath{\\circ}", "\u25a0": "\\ensuremath{\\blacksquare}",
    "\u25a1": "\\ensuremath{\\square}", "\u25b2": "\\ensuremath{\\blacktriangle}", "\u25bc": "\\ensuremath{\\blacktriangledown}",
    "\u25c6": "\\ensuremath{\\blacklozenge}", "\u2605": "\\ensuremath{\\bigstar}", "\u2713": "\\ensuremath{\\checkmark}",
    "\u2714": "\\ensuremath{\\checkmark}", "\u2717": "\\ensuremath{\\times}", "\u2718": "\\ensuremath{\\times}", "\u2715": "\\ensuremath{\\times}",
    "\u2020": "\\textdagger{}", "\u2021": "\\textdaggerdbl{}", "\u00a7": "\\S{}", "\u00b6": "\\P{}", "\u2030": "\\textperthousand{}",
    "\u00b0": "\\textdegree{}", "\u2103": "\\textdegree{}C", "\u00b5": "\\textmu{}", "\u03bc": "\\ensuremath{\\mu}",
    "\u00b2": "\\textsuperscript{2}", "\u00b3": "\\textsuperscript{3}", "\u00b9": "\\textsuperscript{1}",
    "\u2070": "\\textsuperscript{0}", "\u2074": "\\textsuperscript{4}", "\u2075": "\\textsuperscript{5}", "\u2076": "\\textsuperscript{6}",
    "\u2077": "\\textsuperscript{7}", "\u2078": "\\textsuperscript{8}", "\u2079": "\\textsuperscript{9}", "\u207a": "\\textsuperscript{+}",
    "\u207b": "\\textsuperscript{\\ensuremath{-}}", "\u207f": "\\textsuperscript{n}", "\u2071": "\\textsuperscript{i}",
    "\u2080": "\\textsubscript{0}", "\u2081": "\\textsubscript{1}", "\u2082": "\\textsubscript{2}", "\u2083": "\\textsubscript{3}",
    "\u2084": "\\textsubscript{4}", "\u2085": "\\textsubscript{5}", "\u2086": "\\textsubscript{6}", "\u2087": "\\textsubscript{7}",
    "\u2088": "\\textsubscript{8}", "\u2089": "\\textsubscript{9}", "\u2090": "\\textsubscript{a}", "\u2091": "\\textsubscript{e}",
    "\u1d62": "\\textsubscript{i}", "\u2c7c": "\\textsubscript{j}", "\u2096": "\\textsubscript{k}", "\u2099": "\\textsubscript{n}",
    "\u209c": "\\textsubscript{t}",
    "\u00bd": "\\textonehalf{}", "\u00bc": "\\textonequarter{}", "\u00be": "\\textthreequarters{}", "\u2153": "\\ensuremath{\\tfrac{1}{3}}",
    "\u2154": "\\ensuremath{\\tfrac{2}{3}}", "\u00ae": "\\textregistered{}", "\u2122": "\\texttrademark{}", "\u00a9": "\\textcopyright{}",
    "\u20ac": "\\texteuro{}", "\u00a3": "\\pounds{}", "\u2116": "No.", "\u2042": "*",
    "\u2014": "---", "\u2013": "--", "\u2018": "`", "\u2019": "'", "\u201c": "``", "\u201d": "''", "\u201e": ",,",
    "\u2039": "\\guilsinglleft{}", "\u203a": "\\guilsinglright{}", "\u00ab": "\\guillemotleft{}", "\u00bb": "\\guillemotright{}",
    "\u2248": "\\ensuremath{\\approx}", "\u2329": "\\ensuremath{\\langle}", "\u232a": "\\ensuremath{\\rangle}",
    "\u2610": "\\ensuremath{\\square}", "\u2611": "\\ensuremath{\\boxtimes}", "\u2612": "\\ensuremath{\\boxtimes}",
    "\u0218": "\\textcommabelow{S}", "\u0219": "\\textcommabelow{s}", "\u021a": "\\textcommabelow{T}", "\u021b": "\\textcommabelow{t}",
    "\u0131": "\\i{}", "\u0142": "\\l{}", "\u0141": "\\L{}", "\u00df": "\\ss{}", "\u00f8": "\\o{}", "\u00d8": "\\O{}", "\u00e6": "\\ae{}",
    "\u00c6": "\\AE{}", "\u0153": "\\oe{}", "\u0152": "\\OE{}", "\u00e5": "\\aa{}", "\u00c5": "\\AA{}", "\u0111": "\\dj{}", "\u0110": "\\DJ{}",
}
_greek = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho varsigma sigma tau upsilon phi chi psi omega".split()
for _i, _n in enumerate(_greek):
    if _n in ("omicron",):
        UNI[chr(0x03b1 + _i)] = "\\ensuremath{o}"
    else:
        UNI[chr(0x03b1 + _i)] = "\\ensuremath{\\%s}" % _n
_GREEK_UP = {"\u0393": "Gamma", "\u0394": "Delta", "\u0398": "Theta", "\u039b": "Lambda", "\u039e": "Xi", "\u03a0": "Pi",
             "\u03a3": "Sigma", "\u03a5": "Upsilon", "\u03a6": "Phi", "\u03a8": "Psi", "\u03a9": "Omega"}
for _c, _n in _GREEK_UP.items():
    UNI[_c] = "\\ensuremath{\\%s}" % _n
UNI["\u03d5"] = "\\ensuremath{\\phi}"
UNI["\u03b5"] = "\\ensuremath{\\varepsilon}"
_SUPLET = "ᵃa ᵇb ᶜc ᵈd ᵉe ᶠf ᵍg ʰh ⁱi ʲj ᵏk ˡl ᵐm ⁿn ᵒo ᵖp ʳr ˢs ᵗt ᵘu ᵛv ʷw ˣx ʸy ᶻz"
for _pair in _SUPLET.split():
    UNI[_pair[0]] = "\\textsuperscript{%s}" % _pair[1]
# characters that pdfLaTeX's utf8 inputenc + T1 already know (accented Latin letters)
LATIN_OK = set("ÀÁÂÃÄÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜÝàáâãäçèéêëìíîïñòóôõöùúûüýÿĀāĂăĄąĆćČčĎďĒēĘęĚěĞğĪīİĹĺĽľŃńŇňŌōŐőŔŕŘřŚśŞşŠšŢţŤťŪūŮůŰűŹźŻżŽžĐđ")

# accents for the pdfLaTeX-safe bibliography copy (BibTeX abbreviates first names byte-wise)
BIBACC = {
    "á": "{\\'a}", "é": "{\\'e}", "í": "{\\'i}", "ó": "{\\'o}", "ú": "{\\'u}", "ý": "{\\'y}", "Á": "{\\'A}", "É": "{\\'E}",
    "Í": "{\\'I}", "Ó": "{\\'O}", "Ú": "{\\'U}", "à": "{\\`a}", "è": "{\\`e}", "ì": "{\\`i}", "ò": "{\\`o}", "ù": "{\\`u}",
    "ä": "{\\\"a}", "ë": "{\\\"e}", "ï": "{\\\"i}", "ö": "{\\\"o}", "ü": "{\\\"u}", "Ä": "{\\\"A}", "Ö": "{\\\"O}", "Ü": "{\\\"U}",
    "â": "{\\^a}", "ê": "{\\^e}", "î": "{\\^i}", "ô": "{\\^o}", "û": "{\\^u}", "ñ": "{\\~n}", "Ñ": "{\\~N}", "ã": "{\\~a}",
    "õ": "{\\~o}", "ç": "{\\c{c}}", "Ç": "{\\c{C}}", "ş": "{\\c{s}}", "Ş": "{\\c{S}}", "š": "{\\v{s}}", "Š": "{\\v{S}}",
    "ž": "{\\v{z}}", "Ž": "{\\v{Z}}", "č": "{\\v{c}}", "Č": "{\\v{C}}", "ć": "{\\'c}", "ř": "{\\v{r}}", "ě": "{\\v{e}}",
    "ș": "{\\textcommabelow{s}}", "Ș": "{\\textcommabelow{S}}", "ț": "{\\textcommabelow{t}}", "Ț": "{\\textcommabelow{T}}",
    "ł": "{\\l}", "Ł": "{\\L}", "ø": "{\\o}", "Ø": "{\\O}", "å": "{\\aa}", "Å": "{\\AA}", "ß": "{\\ss}", "ğ": "{\\u{g}}",
    "ı": "{\\i}", "ő": "{\\H{o}}", "ű": "{\\H{u}}", "ń": "{\\'n}", "ś": "{\\'s}", "ź": "{\\'z}", "ż": "{\\.z}",
    "–": "--", "—": "---", "’": "'", "‘": "`", "“": "``", "”": "''", "§": "{\\S}", "\u00a0": "~",
}


# ------------------------------------------------------------------ markdown splitting
def split_yaml(md):
    if not md.startswith("---"):
        return {}, md
    end = md.index("\n---", 3)
    meta = yaml.safe_load(md[3:end]) or {}
    return meta, md[end + 4:].lstrip("\n")


HEAD = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def heading_spans(lines):
    """[(index, level, title)] of ATX headings outside fenced code."""
    out, fence = [], False
    for i, ln in enumerate(lines):
        if ln.startswith("```") or ln.startswith("~~~"):
            fence = not fence
        if fence:
            continue
        m = HEAD.match(ln)
        if m:
            out.append((i, len(m.group(1)), m.group(2)))
    return out


def take_section(md, title_re, include_heading=False):
    """Remove the section whose heading matches title_re; return (section_text, md_without, level)."""
    lines = md.split("\n")
    hs = heading_spans(lines)
    for k, (i, lev, title) in enumerate(hs):
        if re.match(title_re, title):
            j = len(lines)
            for (i2, lev2, _t) in hs[k + 1:]:
                if lev2 <= lev:
                    j = i2
                    break
            sec = "\n".join(lines[i if include_heading else i + 1:j])
            rest = "\n".join(lines[:i] + lines[j:])
            return sec, rest, lev
    return None, md, None


def drop_rules(md):
    """Horizontal rules (---) are visual separators of the Markdown draft; the template has its own layout."""
    out, fence = [], False
    for ln in md.split("\n"):
        if ln.startswith("```"):
            fence = not fence
        if not fence and re.fullmatch(r"\s*(-{3,}|\*{3,}|_{3,})\s*", ln):
            out.append("")
            continue
        out.append(ln)
    return "\n".join(out)


def bold_items(sec):
    """Split '**Label.** text' paragraphs into [(label, text)]; text runs until the next '**Label.**' paragraph."""
    items, cur = [], None
    for para in re.split(r"\n\s*\n", sec.strip()):
        m = re.match(r"^\*\*([^*]+?)\.?\*\*\.?\s*(.*)$", para, re.S)
        if m and not para.lstrip().startswith("- "):
            cur = [m.group(1).strip().rstrip("."), m.group(2)]
            items.append(cur)
        elif cur is not None:
            cur[1] += "\n\n" + para
        else:
            items.append(["", para])
    return [(a, b) for a, b in items]


# ------------------------------------------------------------------ pandoc
def pandoc_latex(md, cfg, shift=0, extra_meta=None):
    meta = {"mt_twocol": "true" if cfg["twocol"] else "false", "mt_colwidth": str(cfg["colwidth"]),
            "mt_textwidth": str(cfg["textwidth"]), "mt_textheight": str(cfg.get("textheight", 0)),
            "mt_figsizes": cfg["_figsizes"], "mt_figprefix": "",
            "mt_shortcols": str(cfg.get("shortcols", 60))}
    if extra_meta:
        meta.update(extra_meta)
    cmd = [PANDOC, "-f", "markdown-auto_identifiers", "-t", "latex", "--natbib", "--wrap=preserve",
           "--lua-filter", os.path.join(cfg["_tooldir"], "md2tex.lua")]
    if shift:
        meta["mt_shift"] = str(shift)  # applied inside md2tex.lua, before the heading counters
    for k, v in meta.items():
        cmd += ["-M", "%s=%s" % (k, v)]
    r = subprocess.run(cmd, input=md.encode("utf-8"), capture_output=True)
    if r.returncode:
        raise SystemExit("pandoc failed: " + r.stderr.decode("utf-8", "replace"))
    err = r.stderr.decode("utf-8", "replace").strip()
    if err:
        cfg["_messages"].extend(err.splitlines())
    return r.stdout.decode("utf-8").replace("\r\n", "\n").strip()


def pdf_size(path):
    from pypdf import PdfReader
    p = PdfReader(path).pages[0]
    box = p.mediabox
    return [float(box.width), float(box.height)]


# ------------------------------------------------------------------ text identity check
def ast_tokens(md):
    r = subprocess.run([PANDOC, "-f", "markdown-auto_identifiers", "-t", "json"], input=md.encode("utf-8"),
                       capture_output=True, check=True)
    doc = json.loads(r.stdout.decode("utf-8"))
    out = []

    def walk(n):
        if isinstance(n, list):
            for x in n:
                walk(x)
            return
        if not isinstance(n, dict):
            return
        t, c = n.get("t"), n.get("c")
        if t == "Str":
            out.append(c)
        elif t in ("Space", "SoftBreak", "LineBreak"):
            out.append(" ")
        elif t in ("Code", "Math"):
            out.append(c[1])
        elif t == "CodeBlock":
            out.append(" " + c[1] + " ")
        elif t in ("Cite", "RawInline", "RawBlock", "Image"):
            out.append(" ")
        elif t == "Figure":
            walk(c[1])
            out.append(" ")
        elif t == "Link":
            walk(c[1])
        elif t == "Header":
            inl = list(c[2])
            if inl and inl[0].get("t") == "Str" and re.fullmatch(r"\d+[.\d]*\.?", inl[0]["c"]):
                inl = inl[2:]
            elif inl and inl[0].get("t") == "Str" and inl[0]["c"] == "Appendix" and len(inl) > 2 and \
                    re.fullmatch(r"[A-Z][.:]?", inl[2].get("c", "") or ""):
                k = 3
                while k < len(inl) and (inl[k].get("t") == "Space" or inl[k].get("c") in ("—", "–", ":", "-")):
                    k += 1
                inl = inl[k:]
            out.append(" ")
            walk(inl)
            out.append(" ")
        else:
            walk(c)
            if t in ("Para", "Plain", "BulletList", "OrderedList", "Table", "BlockQuote", "Div", "Cell", "Row"):
                out.append(" ")

    walk(doc["blocks"])
    return norm_tokens("".join(out))


QUOTES = "'\"`\u2018\u2019\u201c\u201d"


def norm_tokens(s):
    s = s.replace("\u2026", "...")
    toks = []
    for w in s.split():
        w = w.strip(QUOTES)
        w = "".join(ch for ch in w if ch not in QUOTES)
        if w:
            toks.append(w)
    return toks


def _drop_cmd(s, name, nopt, nargs, keep=None):
    """Remove \\name[opt]{arg}...; keep=k keeps the k-th mandatory argument's text."""
    pat = re.compile(r"\\" + re.escape(name) + r"(?![A-Za-z])\*?")
    out, pos = [], 0
    while True:
        m = pat.search(s, pos)
        if not m:
            out.append(s[pos:])
            break
        out.append(s[pos:m.start()])
        i = m.end()
        kept = ""
        for _ in range(nopt):
            j = i
            while j < len(s) and s[j] in " \t":
                j += 1
            if j < len(s) and s[j] == "[":
                depth, k = 0, j
                while k < len(s):
                    if s[k] == "[":
                        depth += 1
                    elif s[k] == "]":
                        depth -= 1
                        if depth == 0:
                            break
                    k += 1
                i = k + 1
        for a in range(nargs):
            j = i
            while j < len(s) and s[j] in " \t\n":
                j += 1
            if j < len(s) and s[j] == "{":
                depth, k = 0, j
                while k < len(s):
                    if s[k] == "\\":
                        k += 2
                        continue
                    if s[k] == "{":
                        depth += 1
                    elif s[k] == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    k += 1
                if keep is not None and a == keep:
                    kept = s[j + 1:k]
                i = k + 1
        out.append(" " + kept + " ")
        pos = i
    return "".join(out)


def tex_tokens(tex):
    s = tex
    s = re.sub(r"\\renewcommand\{\\thetable\}\{([^}]*)\}%mtlabel", r" Table \1. ", s)
    s = re.sub(r"\\renewcommand\{\\thefigure\}\{([^}]*)\}%mtlabel", r" Figure \1. ", s)
    s = re.sub(r"\\renewcommand\{\\thefigure\}\{([^}]*)\}%mtautolabel", " ", s)
    # verbatim blocks: keep their text as is
    verb = []

    def keepverb(m):
        verb.append(m.group(1))
        return " \x02%d\x02 " % (len(verb) - 1)
    s = re.sub(r"\\begin\{[Vv]erbatim\}(?:\[[^\]\n]*\])?\n(.*?)\n\\end\{[Vv]erbatim\}", keepverb, s, flags=re.S)
    # long tables: the column specification line and the header repeated on continuation pages
    s = re.sub(r"\\begin\{longtable\}[^\n]*%mtcolspec", " ", s)
    s = re.sub(r"%mtrepeat-begin.*?%mtrepeat-end", " ", s, flags=re.S)
    s = re.sub(r"\\mtcontinued\{\d+\}", " ", s)
    s = re.sub(r"(?<!\\)%[^\n]*", "", s)
    ph = {"\\%": "\x01P", "\\&": "\x01A", "\\_": "\x01U", "\\#": "\x01H", "\\$": "\x01D", "\\{": "\x01L", "\\}": "\x01R",
          "\\textasciitilde{}": "\x01T", "\\textbackslash{}": "\x01B", "\\textless{}": "<", "\\textgreater{}": ">",
          "\\textbar{}": "|", "\\textasciicircum{}": "^", "\\^{}": "^", "\\ldots{}": "...", "\\textquotesingle{}": "'",
          "\\textasciigrave{}": "`", "\\textquotedbl{}": '"', "\\S{}": "\u00a7", "\\S ": "\u00a7 "}
    back = {"\x01P": "%", "\x01A": "&", "\x01U": "_", "\x01H": "#", "\x01D": "$", "\x01L": "{", "\x01R": "}", "\x01T": "~",
            "\x01B": "\\"}
    s = re.sub(r"\\def\\labelenum[ivx]+\{\\[A-Za-z]+\{enum[ivx]+\}[^}]*\}", " ", s)
    s = s.replace("-{}-", "\x01M\x01M").replace("-\\/-", "\x01M\x01M").replace("\\,", "").replace("\\allowbreak{}", "")
    s = s.replace("\\/", "")
    # hyphens inside code are literal (typewriter fonts have no dash ligatures)
    s = re.sub(r"\\texttt\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}",
               lambda m: "\\texttt{" + m.group(1).replace("-", "\x01M") + "}", s)
    s = _drop_cmd(s, "addcontentsline", 0, 3)
    esc = {"textbar": "|", "textless": "<", "textgreater": ">", "textasciitilde": "\x01T", "textbackslash": "\x01B",
           "textasciicircum": "^", "ldots": "...", "textquotesingle": "'", "textasciigrave": "`", "textquotedbl": '"'}
    s = re.sub(r"\\(" + "|".join(esc) + r")(?:\{\}| (?=\S)|(?![A-Za-z]))", lambda m: esc[m.group(1)], s)
    for k, v in ph.items():
        s = s.replace(k, v)
    for name, nopt, nargs, keep in [("citetext", 0, 1, None),("includegraphics", 1, 1, None), ("setcounter", 0, 2, None), ("label", 0, 1, None),
                                    ("bibliography", 0, 1, None), ("bibliographystyle", 0, 1, None),
                                    ("renewcommand", 0, 2, None), ("vspace", 0, 1, None), ("hspace", 0, 1, None),
                                    ("citep", 2, 1, None), ("citet", 2, 1, None), ("cite", 2, 1, None),
                                    ("citealp", 2, 1, None), ("citeauthor", 2, 1, None), ("citeyear", 2, 1, None),
                                    ("citeyearpar", 2, 1, None), ("hypertarget", 0, 1, None), ("href", 0, 2, 1),
                                    ("makebox", 2, 0, None), ("caption", 1, 1, 0), ("begin", 0, 1, None), ("end", 0, 1, None)]:
        s = _drop_cmd(s, name, nopt, nargs, keep)
    # arguments of table environments that _drop_cmd(begin) left behind: {\textwidth}{@{}LLR@{}}
    s = re.sub(r"\{\\(?:textwidth|columnwidth|linewidth)\}\{@\{\}[LCRJlcrp{}0-9.]*@\{\}\}", " ", s)
    s = re.sub(r"\[(?:tp|tbp|htbp|t|h|H|p)\]", " ", s)
    s = s.replace("\\\\", " ")
    s = re.sub(r"\\[,;:!> ]", " ", s)
    s = re.sub(r"\\newline\{\}", " ", s)
    s = re.sub(r"\\[A-Za-z]+\*?(?=\{)", "", s)
    s = re.sub(r"\\[A-Za-z]+\*?", " ", s)
    s = s.replace("{", "").replace("}", "")
    s = s.replace("&", " ").replace("~", " ")
    s = s.replace("---", "\u2014").replace("--", "\u2013").replace("``", "").replace("''", "")
    for k, v in back.items():
        s = s.replace(k, v)
    s = s.replace("\x01M", "-")
    s = re.sub(r"\x02(\d+)\x02", lambda m: verb[int(m.group(1))], s)
    return norm_tokens(s)


def text_check(md_full_body, tex_pieces, expected_note):
    a = ast_tokens(md_full_body)
    b = tex_tokens("\n".join(tex_pieces))
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    diffs = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        diffs.append((op, " ".join(a[i1:i2]), " ".join(b[j1:j2]), " ".join(a[max(0, i1 - 6):i1])))
    ca, cb = collections.Counter(a), collections.Counter(b)
    only_md = ca - cb
    only_tex = cb - ca
    return a, b, diffs, only_md, only_tex


# ------------------------------------------------------------------ bibliography copy
def safe_bib(src, dst):
    txt = open(src, encoding="utf-8").read()
    out = []
    for line in txt.split("\n"):
        m = re.match(r"^(\s*title\s*=\s*)\{(.*)\}(\s*,?\s*)$", line)
        if m and not m.group(2).startswith("{"):
            line = "%s{{%s}}%s" % (m.group(1), m.group(2), m.group(3))
        out.append(line)
    txt = "\n".join(out)
    for k, v in BIBACC.items():
        txt = txt.replace(k, v)
    bad = sorted(set(ch for ch in txt if ord(ch) > 127))
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)
    return bad


# ------------------------------------------------------------------ unicode declarations
COMBINING = {"̂": "hat", "̃": "tilde", "̄": "bar", "̇": "dot", "̈": "ddot", "⃗": "vec"}


def fix_combining(tex):
    """Base character + combining accent (e.g. the lambda-hat of a calibrated threshold) -> one math accent."""
    def rep(m):
        base, acc = m.group(1), COMBINING[m.group(2)]
        if base in UNI and UNI[base].startswith("\ensuremath{"):
            inner = UNI[base][len("\ensuremath{"):-1]
        else:
            inner = base
        return "\ensuremath{\%s{%s}}" % (acc, inner)
    return re.sub("(.)([" + "".join(COMBINING) + "])", rep, tex)


def unicode_decls(tex):
    need = sorted(set(ch for ch in tex if ord(ch) > 127 and ch not in LATIN_OK))
    lines, missing = [], []
    for ch in need:
        if ch in UNI:
            rep = UNI[ch]
            lines.append("\\newunicodechar{%s}{%s}" % (ch, rep))
        else:
            i = tex.index(ch)
            missing.append("U+%04X %s (near: %r)" % (ord(ch), ch, tex[max(0, i - 60):i + 20]))
    return "\n".join(lines), missing


# ------------------------------------------------------------------ compile and log
def compile_and_check(latexdir):
    for ext in ("aux", "bbl", "blg", "fdb_latexmk", "fls", "log", "out", "toc", "lof", "lot"):
        p = os.path.join(latexdir, "main." + ext)
        if os.path.exists(p):
            os.remove(p)
    r = subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "-file-line-error", "main.tex"], cwd=latexdir,
                       capture_output=True)
    log = open(os.path.join(latexdir, "main.log"), encoding="latin-1").read()
    blg = ""
    if os.path.exists(os.path.join(latexdir, "main.blg")):
        blg = open(os.path.join(latexdir, "main.blg"), encoding="latin-1").read()
    rep = {"latexmk_rc": r.returncode}
    m = re.search(r"Output written on main\.pdf \((\d+) pages?", log)
    rep["pages"] = int(m.group(1)) if m else None
    rep["undefined_citations"] = sorted(set(re.findall(r"Citation `([^']+)' on page", log)))
    rep["undefined_references"] = sorted(set(re.findall(r"Reference `([^']+)' on page", log)))
    rep["errors"] = re.findall(r"^\S+:\d+: (.*)$", log, re.M)
    rep["missing_chars"] = sorted(set(re.findall(r"Missing character: There is no (.*?) in font", log)))
    rep["float_too_large"] = re.findall(r"Float too large for page by ([\d.]+pt)", log)
    over = []
    for mm in re.finditer(r"Overfull \\hbox \(([\d.]+)pt too wide\) (in paragraph|in alignment|detected) at lines? (\d+)(?:--(\d+))?\n(.*)\n", log):
        over.append((float(mm.group(1)), mm.group(2), int(mm.group(4) or mm.group(3)), mm.group(5)[:120]))
    rep["overfull_vbox"] = re.findall(r"Overfull \\vbox \(([\d.]+pt) too high\)", log)
    rep["float_only_pages"] = re.findall(r"Text page (\d+) contains only floats", log)
    rep["overfull"] = over
    rep["overfull_over_1pt"] = [o for o in over if o[0] > 1.0]
    rep["underfull_count"] = len(re.findall(r"Underfull \\[hv]box", log))
    rep["bibtex_warnings"] = re.findall(r"^Warning--(.*)$", blg, re.M)
    rep["latex_warnings"] = [w for w in re.findall(r"LaTeX Warning: (.*)", log)
                             if "Citation" in w or "Reference" in w or "undefined" in w or "Float" in w]
    subprocess.run(["latexmk", "-c", "main.tex"], cwd=latexdir, capture_output=True)
    for ext in ("aux", "fdb_latexmk", "fls", "out", "log", "blg", "synctex.gz", "spl"):
        p = os.path.join(latexdir, "main." + ext)
        if os.path.exists(p):
            os.remove(p)
    return rep, log


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True)
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")
