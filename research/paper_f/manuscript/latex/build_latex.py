#!/usr/bin/env python3
"""Paper F -> Elsevier elsarticle template (name-year references) for NeuroImage: Clinical.

    python build_latex.py            # writes main.tex, main.pdf, references.bib copy, figures, TEXT_CHECK.md

Needs pandoc >= 3 (set PANDOC=<path> if it is not on PATH), a TeX distribution with latexmk and pdfLaTeX
(MiKTeX or TeX Live), and Python with PyYAML and pypdf. The text comes only from ../manuscript.md.
(header.tex and longcode.lua in this folder belong to the older ../build_manuscript.py PDF build.)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mdtex_build import build, build_docx, write_text_check  # noqa: E402

AUTHOR = dict(
    els_author="\n".join([
        r"% ORCID: TODO owner (add it in the submission system; Elsevier links it to the author record).",
        r"\author[1,2,3]{Nicolás Bonilla Vargas\corref{cor1}\fnref{fn1}}",
        r"\ead{ngbonillav@unal.edu.co}",
        r"\cortext[cor1]{Corresponding author.}",
        r"% the last sentence of the Markdown's affiliation paragraph, kept as an author note",
        r"\fntext[fn1]{The author develops MSTool-AI, investigational software for MRI in multiple sclerosis (see Conflict of interest).}",
        r"\affiliation[1]{organization={Universidad Nacional de Colombia}, city={Bogotá}, country={Colombia}}",
        r"\affiliation[2]{organization={SRH University München}, city={Munich}, country={Germany}}",
        r"\affiliation[3]{Daita AI}",  # no city given; the plain form avoids a trailing comma
    ]),
)

CFG = dict(
    journal="elsarticle",
    journal_name="NeuroImage: Clinical",
    msdir=os.path.abspath(os.path.join(HERE, "..")),
    latexdir=HERE,
    tooldir=HERE,
    twocol=True, colwidth=252.0, textwidth=522.0, textheight=682.0, shortcols=60,
    shift=0,
    author=AUTHOR,
    running_title="CPU lesion segmenters vs FLAMeS on thick-slice FLAIR",
    abstract_re=r"^Abstract$",
    decl_re=r"^Declarations$",
    refs_re=r"^References$",
    # keep the Markdown order: Declarations, Appendix, then the generative-AI declaration immediately above
    # the References, as Elsevier requires
    decl_inline=True,
)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        CFG["latexdir"] = os.path.abspath(sys.argv[1])
    res = build(CFG)
    write_text_check(os.path.join(CFG["latexdir"], "TEXT_CHECK.md"), res, "Paper F (NeuroImage: Clinical)")
    r = res["report"]
    print("pages:", r["pages"], "| undefined citations:", r["undefined_citations"], "| undefined refs:",
          r["undefined_references"], "| overfull>1pt:", len(r["overfull_over_1pt"]), "| errors:", len(r["errors"]),
          "| missing chars:", r["missing_chars"], "| text diffs:", len(res["diffs"]))
    for m in res["messages"]:
        print("  ", m)
    # Elsevier accepts Word: main.docx with Elsevier Harvard references (official CSL style)
    out, warn = build_docx(CFG, "elsevier-harvard.csl")
    print("wrote", os.path.basename(out), "| pandoc warnings:", warn or "none")
