"""Build manuscript.docx and manuscript.pdf from manuscript.md (pandoc + citeproc; PDF via xelatex).

    python research/paper_f/manuscript/build_manuscript.py --pandoc <path to pandoc>   (pandoc >= 3; MiKTeX/TeX Live xelatex)

Used for the 2026-10-31 build: pandoc 3.9 (pypandoc_binary 1.17 wheel) and MiKTeX xelatex on Windows 11.
"""
import argparse
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pandoc", default="pandoc")
    ap.add_argument("--skip-pdf", action="store_true")
    a = ap.parse_args()
    common = [a.pandoc, "manuscript.md", "--citeproc", "--bibliography", "references.bib", "--resource-path", "."]
    subprocess.run(common + ["-o", "manuscript.docx"], cwd=HERE, check=True)
    print("wrote manuscript.docx")
    if not a.skip_pdf:
        subprocess.run(common + ["--pdf-engine=xelatex", "-H", "build/header.tex", "--lua-filter", "build/longcode.lua",
                                 "-V", "mainfont=Cambria", "-V", "mainfontoptions=Ligatures=NoCommon", "-V", "monofont=Consolas", "-V", "geometry:margin=2.2cm",
                                 "-V", "fontsize=10pt", "-V", "linestretch=1.2", "-V", "colorlinks=true",
                                 "-V", "linkcolor=black", "-V", "urlcolor=blue", "-o", "manuscript.pdf"], cwd=HERE, check=True)
        print("wrote manuscript.pdf")


if __name__ == "__main__":
    main()
