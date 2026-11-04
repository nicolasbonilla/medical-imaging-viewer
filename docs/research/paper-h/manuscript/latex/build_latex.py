#!/usr/bin/env python3
"""Paper H -> Springer Nature LaTeX template (sn-jnl.cls, Basic Springer author-year references) for
Empirical Software Engineering.

    python build_latex.py            # writes main.tex, main.pdf, references.bib copy, figures, TEXT_CHECK.md

Needs pandoc >= 3 (set PANDOC=<path> if it is not on PATH), a TeX distribution with latexmk and pdfLaTeX
(MiKTeX or TeX Live), and Python with PyYAML and pypdf. The text comes only from ../manuscript.md.
Springer asks for a flat LaTeX folder (no sub-folders): main.tex, the class, the .bst, the .bib and the figures
all sit in this folder.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mdtex_build import build, build_docx, write_text_check  # noqa: E402

AUTHOR = dict(
    sn_author="\n".join([
        r"\author*[1,2,3]{\fnm{Nicolás} \sur{Bonilla Vargas}}\email{ngbonillav@unal.edu.co}",
        r"% ORCID: TODO owner (Springer asks for the 16-digit ORCID if available).",
        r"\affil*[1]{\orgname{Universidad Nacional de Colombia}, \orgaddress{\city{Bogotá}, \country{Colombia}}}",
        r"\affil[2]{\orgname{SRH University München}, \orgaddress{\city{Munich}, \country{Germany}}}",
        r"\affil[3]{\orgname{Daita AI}}",
    ]),
)

CFG = dict(
    journal="snjnl",
    msdir=os.path.abspath(os.path.join(HERE, "..")),
    latexdir=HERE,
    tooldir=HERE,
    twocol=False, colwidth=372.0, textwidth=372.0, textheight=552.69, shortcols=999,
    shift=-1,  # sections are level-2 headings in the Markdown (the title is in the YAML header)
    author=AUTHOR,
    running_title="Evidence That Can Fail",
    abstract_re=r"^Abstract$",
    decl_re=r"^Declarations$",
    refs_re=r"^References$",
)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        CFG["latexdir"] = os.path.abspath(sys.argv[1])
    res = build(CFG)
    write_text_check(os.path.join(CFG["latexdir"], "TEXT_CHECK.md"), res, "Paper H (Empirical Software Engineering)")
    r = res["report"]
    print("pages:", r["pages"], "| undefined citations:", r["undefined_citations"], "| undefined refs:",
          r["undefined_references"], "| overfull>1pt:", len(r["overfull_over_1pt"]), "| errors:", len(r["errors"]),
          "| missing chars:", r["missing_chars"], "| text diffs:", len(res["diffs"]))
    for m in res["messages"]:
        print("  ", m)
    # Empirical Software Engineering accepts Word or LaTeX: main.docx with Springer Basic (author-date)
    # references (official CSL style)
    out, warn = build_docx(CFG, "springer-basic-author-date.csl")
    print("wrote", os.path.basename(out), "| pandoc warnings:", warn or "none")
