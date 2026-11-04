#!/usr/bin/env python3
"""Paper A -> MELBA (Machine Learning for Biomedical Imaging) official LaTeX template.

    python build_latex.py            # writes main.tex, main.pdf, references.bib copy, figures, TEXT_CHECK.md

Needs pandoc >= 3 (set PANDOC=<path> if it is not on PATH), a TeX distribution with latexmk and pdfLaTeX
(MiKTeX or TeX Live), and Python with PyYAML and pypdf. The text comes only from ../manuscript.md.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mdtex_build import build, write_text_check  # noqa: E402

AUTHOR = dict(
    melbaauthors="Nicolás Bonilla Vargas",
    short="Bonilla Vargas",
    email="ngbonillav@unal.edu.co",
    melba_author=r"\author{\firstname Nicolás \surname Bonilla Vargas\aff{1,2,3}}",
    melba_affils="\\num 1 \\addr Universidad Nacional de Colombia, Bogotá, Colombia \\\\\n"
                 "\\num 2 \\addr SRH University München, Munich, Germany \\\\\n"
                 "\\num 3 \\addr Daita AI",
)

CFG = dict(
    journal="melba",
    msdir=os.path.abspath(os.path.join(HERE, "..")),
    latexdir=HERE,
    tooldir=HERE,
    twocol=True, colwidth=265.30, textwidth=540.60, textheight=721.14, shortcols=60,
    shift=0,
    author=AUTHOR,
    # the title block (authors + long structured abstract) is longer than one page: the template's own
    # alternative, \maketitle then \twocolumn
    # (\enlargethispage keeps the last line of the title block, the corresponding author, on page 1)
    melba_titlecmd=r"\enlargethispage{3\baselineskip}" + "\n" + r"\maketitle" + "\n" + r"\twocolumn",
    running_title="Conformal false-lesion control under acquisition shift",  # fallback; the YAML running-title wins
    abstract_re=r"^Abstract$",
    decl_re=r"^Declarations$",
    refs_re=r"^References$",
    # Appendix D ("Open items before submission (owner checklist)") is kept: the text cites it three times.
    # It must be deleted, together with those citations, before submission (SUBMISSION_CHECKLIST.md).
    drop_blocks=[],
    # Declarations -> MELBA blocks: (block, keep the bold label inside the block?)
    melba_decl={
        "Data availability": ("data", False),
        "Code availability": ("data", True),
        "Ethics": ("ethics", False),
        "Licences": ("ethics", True),
        "Funding": ("acks", True),
        "Competing interests": ("coi", False),
        "Author contributions (CRediT)": ("Author contributions (CRediT)", False),
        "Use of AI assistance": ("Use of AI assistance", False),
        "Acknowledgements": ("acks", False),
    },
)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        CFG["latexdir"] = os.path.abspath(sys.argv[1])
    res = build(CFG)
    write_text_check(os.path.join(CFG["latexdir"], "TEXT_CHECK.md"), res, "Paper A (MELBA)")
    r = res["report"]
    print("pages:", r["pages"], "| undefined citations:", r["undefined_citations"], "| undefined refs:",
          r["undefined_references"], "| overfull>1pt:", len(r["overfull_over_1pt"]), "| errors:", len(r["errors"]),
          "| missing chars:", r["missing_chars"], "| text diffs:", len(res["diffs"]))
    for m in res["messages"]:
        print("  ", m)
