"""mdtex_build — the build and the three journal templates (MELBA, Elsevier elsarticle, Springer Nature sn-jnl).
See mdtex.py for the conversion helpers and the text-identity check."""
from mdtex import *  # noqa: F401,F403
from mdtex import (heading_spans, take_section, drop_rules, bold_items, split_yaml, pandoc_latex, pdf_size,
                   unicode_decls, fix_combining, safe_bib, compile_and_check, text_check, HERE)
import json
import os
import re
import shutil
import tempfile


def replace_section(md, title_re, replacement):
    lines = md.split("\n")
    hs = heading_spans(lines)
    for k, (i, lev, title) in enumerate(hs):
        if re.match(title_re, title):
            j = len(lines)
            for (i2, lev2, _t) in hs[k + 1:]:
                if lev2 <= lev:
                    j = i2
                    break
            return "\n".join(lines[:i] + [replacement] + lines[j:]), "\n".join(lines[i:j])
    raise SystemExit("section not found: " + title_re)


RAW = "\n```{=latex}\n%s\n```\n"


def place_legend_figures(body, legends, figdir, notes):
    """Figure legends listed at the end of the draft become the captions of figures placed after the block
    that first cites them (MELBA wants figures in the text)."""
    paras = re.split(r"\n\s*\n", legends.strip())
    preface, figs = [], []
    for p in paras:
        m = re.match(r"^\*\*Figure (\d+)\.", p)
        if m:
            figs.append((int(m.group(1)), " ".join(x.strip() for x in p.split("\n"))))
        elif p.strip():
            preface.append(" ".join(x.strip() for x in p.split("\n")))
    blocks = re.split(r"(\n\s*\n)", body)
    first = None
    for n, legend in figs:
        cand = sorted(f for f in os.listdir(figdir) if re.match(r"fig%d_.*\.png$" % n, f))
        if not cand:
            raise SystemExit("no figure file for Figure %d" % n)
        if preface and first is None:
            legend = legend + " " + " ".join(preface)
            first = n
            notes.append("The 'Figure legends' section became the figure captions; its general sentence (\"%s\") "
                         "was appended to the caption of Figure %d." % (" ".join(preface), n))
        img = "![%s](figures/%s)" % (legend, cand[0])
        pat = re.compile(r"Fig(?:ure|\.)\s*%d(?![0-9])" % n)
        for bi in range(0, len(blocks), 2):
            blk = blocks[bi]
            if pat.search(blk) and not blk.lstrip().startswith("#") and "![" not in blk:
                blocks[bi] = blk + "\n\n" + img
                notes.append("Figure %d placed after the first block that cites it (\"%s ...\")." %
                             (n, re.sub(r"\s+", " ", blk.strip())[:70]))
                break
        else:
            raise SystemExit("Figure %d is never cited" % n)
    return "".join(blocks)


def build(cfg):
    latexdir, msdir = cfg["latexdir"], cfg["msdir"]
    cfg["_tooldir"] = cfg.get("tooldir", HERE)
    cfg["_messages"] = []
    notes = []
    md = open(os.path.join(msdir, "manuscript.md"), encoding="utf-8").read().replace("\r\n", "\n")
    meta, body = split_yaml(md)
    check_body = body
    for pat in cfg.get("drop_blocks", []):
        m = re.search(pat, body, re.S | re.M)
        if not m:
            raise SystemExit("drop_blocks pattern not found: " + pat)
        notes.append("Omitted as internal (not part of a submission): \"" + re.sub(r"\s+", " ", m.group(0))[:200] + " ...\"")
        body = body[:m.start()] + body[m.end():]
    check_body = body  # the text check compares against the manuscript as submitted (omissions listed above)
    for old, new, why in cfg.get("substitutions", []):
        if old not in body:
            raise SystemExit("substitution not found: " + old)
        body = body.replace(old, new)
        notes.append("Substituted (%s): \"%s\" -> \"%s\"" % (why, old, new))
    lines = body.split("\n")
    hs = heading_spans(lines)
    ai = [i for (i, lev, t) in hs if re.match(cfg["abstract_re"], t)][0]
    front, body = "\n".join(lines[:ai]), "\n".join(lines[ai:])
    highlights = []
    hm = re.search(r"^#+ Highlights\s*\n(.*?)(?=^#|\Z)", front, re.S | re.M)
    if hm:
        highlights = [re.sub(r"\s+", " ", x).strip() for x in re.split(r"\n- ", "\n" + hm.group(1).strip())[1:]]
        front = front[:hm.start()] + front[hm.end():]
    abstract, body, _ = take_section(body, cfg["abstract_re"])
    kw = None
    for where in ("abstract", "front"):
        src = abstract if where == "abstract" else front
        km = re.search(r"^\*\*Keywords:?\*\*:?\s*(.*?)(?:\n\s*\n|\Z)", src, re.S | re.M)
        if km:
            kw = re.sub(r"\s+", " ", km.group(1)).strip()
            if where == "abstract":
                abstract = abstract[:km.start()] + abstract[km.end():]
            else:
                front = front[:km.start()] + front[km.end():]
            break
    if kw is None and meta.get("keywords"):
        kw = "; ".join(meta["keywords"])
    leftover = re.sub(r"<!--.*?-->", "", drop_rules(front), flags=re.S).strip()
    if leftover:
        notes.append("Front matter replaced by the template's title block (authors, affiliations, venue notes): \""
                     + re.sub(r"\s+", " ", leftover)[:400] + "\"")
    abstract = drop_rules(abstract).strip()
    if cfg.get("legends_re"):
        legends, body, _ = take_section(body, cfg["legends_re"])
        body = place_legend_figures(body, legends, os.path.join(msdir, "figures"), notes)
    if cfg.get("decl_inline"):
        # declarations stay where the Markdown has them (e.g. Elsevier: the generative-AI declaration must
        # stay immediately above the references)
        decl = ""
    else:
        decl, body, _ = take_section(body, cfg["decl_re"], include_heading=True)
    body, _refsec = replace_section(body, cfg["refs_re"], RAW % "%%MTBIB%%")
    body = drop_rules(body)

    os.makedirs(latexdir, exist_ok=True)
    figdir = os.path.join(msdir, "figures")
    sizes = {}
    used = re.findall(r"\]\((figures/[^)\s]+\.(?:png|pdf))\)", body)
    for rel in used:
        stem = os.path.splitext(os.path.basename(rel))[0]
        pdf = os.path.join(figdir, stem + ".pdf")
        png = os.path.join(figdir, stem + ".png")
        src = pdf if os.path.exists(pdf) else png
        if src == png:
            notes.append("No vector PDF for %s: PNG used." % stem)
        shutil.copyfile(src, os.path.join(latexdir, os.path.basename(src)))
        if src.endswith(".pdf"):
            sizes[os.path.basename(src)] = pdf_size(src)
        else:
            from PIL import Image
            im = Image.open(src)
            dpi = (im.info.get("dpi") or (300, 300))[0] or 300
            sizes[os.path.basename(src)] = [im.size[0] / dpi * 72.27, im.size[1] / dpi * 72.27]
    tmp = tempfile.mkdtemp()
    cfg["_figsizes"] = os.path.join(tmp, "figsizes.json").replace("\\", "/")
    json.dump(sizes, open(cfg["_figsizes"], "w"))

    shift = cfg.get("shift", 0)
    parts = {"title": pandoc_latex(meta["title"], cfg), "abstract": pandoc_latex(abstract, cfg),
             "keywords": pandoc_latex(kw, cfg) if kw else "",
             "highlights": [pandoc_latex(h, cfg) for h in highlights],
             "body": pandoc_latex(body, cfg, shift=shift)}
    if cfg["journal"] == "melba":
        items = bold_items(take_section(decl, cfg["decl_re"])[0])
        parts["decl_items"] = [(lab, pandoc_latex(txt, cfg)) for lab, txt in items]
        notes.append("Declarations placed in the MELBA template's own blocks: " +
                     "; ".join("'%s' -> %s" % (lab, cfg["melba_decl"].get(lab, ("?",))[0]) for lab, _t in items))
    else:
        parts["decl"] = pandoc_latex(decl, cfg, shift=shift) if decl else ""

    # the running title comes from the Markdown's YAML when it has one (running-title / short_title)
    for key in ("running-title", "running_title", "short_title"):
        if meta.get(key):
            cfg["running_title"] = pandoc_latex(str(meta[key]), cfg)
            notes.append("Running title taken from the YAML header (%s): \"%s\"" % (key, meta[key]))
            break
    tex = fix_combining(ASSEMBLE[cfg["journal"]](cfg, meta, parts, notes))
    decls, missing = unicode_decls(tex)
    if missing:
        raise SystemExit("characters without a pdfLaTeX declaration: " + ", ".join(missing))
    tex = tex.replace("%%UNICODE%%", decls)
    with open(os.path.join(latexdir, "main.tex"), "w", encoding="utf-8", newline="\n") as f:
        f.write(tex)
    badbib = safe_bib(os.path.join(msdir, "references.bib"), os.path.join(latexdir, "references.bib"))
    if badbib:
        notes.append("Non-ASCII characters left in the bibliography copy: " + "".join(badbib))

    rep, log = compile_and_check(latexdir)
    # declarations at the place they occupy in the Markdown (just before the references), in Markdown order
    if "decl" in parts:
        decl_tex = parts["decl"]
    else:
        decl_tex = "\n\n".join(("\\textbf{%s.} %s" % (lab, t)) if cfg["melba_decl"][lab][1] else t
                               for lab, t in parts["decl_items"])
    pieces = [parts["abstract"], parts["keywords"]] + parts["highlights"] + \
        [parts["body"].replace("%%MTBIB%%", "\n" + decl_tex + "\n")]
    a, b, diffs, only_md, only_tex = text_check(check_body, pieces, "")
    return dict(report=rep, notes=notes, messages=cfg["_messages"], diffs=diffs, only_md=only_md,
                only_tex=only_tex, ntok_md=len(a), ntok_tex=len(b), log=log, sizes=sizes)


def write_text_check(path, res, paper):
    rep = res["report"]
    L = ["# TEXT_CHECK - %s: LaTeX version against manuscript.md" % paper, "",
         "Generated by `build_latex.py`. The words of `manuscript.md` (pandoc AST; citations and heading numbers "
         "excluded) are compared, in order, with the words of the LaTeX written into `main.tex` (template commands "
         "excluded). Every difference is listed below; none may touch a number or a scientific statement.", "",
         "- words in manuscript.md: %d; words in main.tex: %d" % (res["ntok_md"], res["ntok_tex"]),
         "- PDF pages: %s" % rep["pages"],
         "- undefined citations: %s" % (", ".join(rep["undefined_citations"]) or "none"),
         "- undefined references: %s" % (", ".join(rep["undefined_references"]) or "none"),
         "- overfull boxes > 1 pt: %d (all overfull: %d)" % (len(rep["overfull_over_1pt"]), len(rep["overfull"])),
         "- missing characters: %s" % (", ".join(rep["missing_chars"]) or "none"),
         "- floats too large: %s" % (", ".join(rep["float_too_large"]) or "none"),
         "- overfull vertical boxes: %s" % (", ".join(rep["overfull_vbox"]) or "none"),
         "- pages holding only floats: %s" % (", ".join(rep["float_only_pages"]) or "none"),
         "- LaTeX errors: %s" % (len(rep["errors"]) or "none"),
         "- BibTeX warnings: %d" % len(rep["bibtex_warnings"]), ""]
    if rep["overfull_over_1pt"]:
        L += ["Overfull boxes over 1 pt (amount, kind, main.tex line):", ""]
        L += ["- %.1f pt, %s, line %d: `%s`" % o for o in rep["overfull_over_1pt"]]
        L.append("")
    if rep["bibtex_warnings"]:
        L += ["BibTeX warnings:", ""] + ["- " + w for w in rep["bibtex_warnings"]] + [""]
    L += ["## Structural changes made by the template conversion", ""]
    L += ["- " + n for n in res["notes"]] or ["- none"]
    if res["messages"]:
        L += ["", "## Converter messages", ""] + ["- " + m for m in res["messages"]]
    L += ["", "## Word-level differences, in order", ""]
    if not res["diffs"]:
        L.append("None: the text is word-for-word identical.")
    for op, a, b, ctx in res["diffs"]:
        L.append("- **%s** after \"...%s\": manuscript.md \"%s\" -> main.tex \"%s\"" % (op, ctx[-60:], a[:500], b[:500]))
    L += ["", "## Words only in manuscript.md (multiset difference)", "",
          ", ".join("%s x%d" % (k, v) for k, v in sorted(res["only_md"].items())) or "none",
          "", "## Words only in main.tex (multiset difference)", "",
          ", ".join("%s x%d" % (k, v) for k, v in sorted(res["only_tex"].items())) or "none", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))


COMMON_PKGS = r"""\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{textcomp}
\usepackage{newunicodechar}
\usepackage{tabulary}
\usepackage{seqsplit}
\usepackage{xurl}
\usepackage{fvextra}
\usepackage{array}
\usepackage{longtable}
\newcommand{\mtcontinued}[1]{\multicolumn{#1}{@{}l@{}}{\emph{(continued)}}}
\setlength{\emergencystretch}{3em}
\setlength{\tymin}{48pt}
\renewcommand{\arraystretch}{1.12}
\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\tracinglostchars=2
%%UNICODE%%
"""

GENERATED = ("% Generated from ../manuscript.md by build_latex.py (pandoc + md2tex.lua). Do not edit by hand:\n"
             "% change manuscript.md and run  python build_latex.py  again.\n")


def bib_and_decl_melba(cfg, parts):
    mp = cfg["melba_decl"]
    macro = {"acks": [], "ethics": [], "coi": [], "data": []}
    extra = []
    for lab, txt in parts["decl_items"]:
        if lab not in mp:
            raise SystemExit("declaration item without a place in the MELBA template: " + lab)
        where, lead = mp[lab]
        block = txt if not lead else "\\textbf{%s.} %s" % (lab, txt)
        if where in macro:
            macro[where].append(block)
        else:
            extra.append((where, block))
    out = []
    for name in ("acks", "ethics", "coi", "data"):
        if macro[name]:
            out.append("\\%s{%s}" % (name, "\n\n".join(macro[name])))
    for title, block in extra:
        out.append("\\melbadeclaration{%s}{%s}" % (title, block))
    out.append("\\bibliography{references}")
    return "\n\n".join(out)


def assemble_melba(cfg, meta, parts, notes):
    a = cfg["author"]
    abstract = re.sub(r"\n\s*\n", "\n\\\\endgraf\n", parts["abstract"])
    body = parts["body"].replace("%%MTBIB%%", bib_and_decl_melba(cfg, parts))
    return GENERATED + r"""% Template: MELBA official LaTeX class melba.cls v2.03 (github.com/melba-journal/submission, commit 44b4072),
% submission mode: line numbers on, issue information off, as the journal asks (class options unchanged).
\documentclass{melba}
""" + COMMON_PKGS + r"""\long\def\melbadeclaration#1#2{\vskip 0.3in\noindent{\color{melba}\large\bf #1}\vskip 0.2in\noindent #2}
% melba.cls uses \doi for the article's own DOI; plainnat needs \doi to print each reference's DOI, so it is
% redefined inside the reference list only (otherwise every reference DOI is silently dropped).
\usepackage{etoolbox}
\AtBeginEnvironment{thebibliography}{\renewcommand{\doi}[1]{doi:\,\href{https://doi.org/#1}{\nolinkurl{#1}}}}

% Header and footer: the publishing editor provides these values at acceptance (template placeholders kept).
\melbaid{YYYY:NNN}
\doi{10.59275/j.melba.YYYY-AAAA}
\melbaauthors{""" + a["melbaauthors"] + r"""}
\email{""" + a["email"] + r"""}
\volume{V}
\firstpageno{1}
\melbayear{""" + cfg.get("year", "2026") + r"""}
\datesubmitted{YYYY-MM-DD}
\datepublished{YYYY-MM-DD}

\ShortHeadings{""" + cfg["running_title"] + r"""}{""" + a["short"] + r"""}

\title{""" + parts["title"] + r"""}

% ORCID: add \orcid{xxxx-xxxx-xxxx-xxxx} after the name when available (TODO owner).
""" + a["melba_author"] + r"""

\affiliations{%
""" + a["melba_affils"] + r"""
}

\abstract{%
""" + abstract + r"""}

\keywords{""" + parts["keywords"] + r"""}

\begin{document}

""" + cfg.get("melba_titlecmd", r"\twocolumn[\maketitle]") + r"""

""" + body + r"""

\end{document}
"""


def assemble_elsarticle(cfg, meta, parts, notes):
    a = cfg["author"]
    kws = " \\sep ".join(k.strip() for k in parts["keywords"].split(";") if k.strip())
    hl = "\n".join("\\item " + h for h in parts["highlights"])
    body = parts["body"].replace("%%MTBIB%%", parts["decl"] + "\n\n\\bibliographystyle{elsarticle-harv}\n\\bibliography{references}")
    return GENERATED + r"""% Template: Elsevier elsarticle.cls (CTAN, built from elsarticle.dtx) with name-year references
% (elsarticle-harv.bst). Two-column journal layout (5p) so that the figures keep their print size (88 mm one
% column, 180 mm two columns); continuous line numbers for review.
\PassOptionsToPackage{switch}{lineno}
\documentclass[5p,authoryear]{elsarticle}
""" + COMMON_PKGS + r"""\usepackage{amssymb}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage[hidelinks]{hyperref}
\journal{""" + cfg["journal_name"] + r"""}

\begin{document}
\begin{frontmatter}

\title{""" + parts["title"] + r"""}

""" + a["els_author"] + r"""

\begin{abstract}
""" + parts["abstract"] + r"""
\end{abstract}

\begin{highlights}
""" + hl + r"""
\end{highlights}

\begin{keyword}
""" + kws + r"""
\end{keyword}

\end{frontmatter}

\linenumbers

""" + body + r"""

\end{document}
"""


def assemble_snjnl(cfg, meta, parts, notes):
    a = cfg["author"]
    body = parts["body"].replace("%%MTBIB%%", "\\backmatter\n\n" + parts["decl"] + "\n\n\\bibliography{references}")
    return GENERATED + r"""% Template: Springer Nature LaTeX template sn-jnl.cls v3.1 (December 2024) with the Basic Springer
% reference style (sn-basic, author-year), as Empirical Software Engineering asks; line numbers for review.
\documentclass[pdflatex,sn-basic,lineno]{sn-jnl}
\usepackage{graphicx}
\usepackage{multirow}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{xcolor}
\usepackage{booktabs}
""" + COMMON_PKGS + r"""\raggedbottom

\begin{document}

\title[""" + cfg["running_title"] + r"""]{""" + parts["title"] + r"""}

""" + a["sn_author"] + r"""

\abstract{""" + parts["abstract"] + r"""}

\keywords{""" + parts["keywords"] + r"""}

\maketitle

""" + body + r"""

\end{document}
"""


ASSEMBLE = {"melba": assemble_melba, "elsarticle": assemble_elsarticle, "snjnl": assemble_snjnl}


def build_docx(cfg, csl, out_name="main.docx"):
    """Word version for journals that accept Word: the same Markdown (internal blocks removed, as for the
    LaTeX), references formatted with the journal's CSL style from the official CSL repository."""
    import subprocess
    from mdtex import PANDOC
    md = open(os.path.join(cfg["msdir"], "manuscript.md"), encoding="utf-8").read().replace("\r\n", "\n")
    for pat in cfg.get("drop_blocks", []):
        md = re.sub(pat, "", md, count=1, flags=re.S | re.M)
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    out = os.path.join(cfg["latexdir"], out_name)
    cmd = [PANDOC, "-f", "markdown", "-t", "docx", "--citeproc", "--csl", os.path.join(cfg["latexdir"], csl),
           "--bibliography", os.path.join(cfg["msdir"], "references.bib"), "--resource-path", cfg["msdir"],
           "-M", "link-citations=true", "-o", out]
    r = subprocess.run(cmd, input=md.encode("utf-8"), capture_output=True)
    if r.returncode:
        raise SystemExit("pandoc docx failed: " + r.stderr.decode("utf-8", "replace"))
    warn = [w for w in r.stderr.decode("utf-8", "replace").splitlines() if w.strip()]
    return out, warn
