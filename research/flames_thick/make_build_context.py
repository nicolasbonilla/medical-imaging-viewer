"""Write a minimal Docker build context for the FLAMeS-thick image (nothing else from the repo is uploaded).

    python research/flames_thick/make_build_context.py C:/tmp/flames-thick-ctx
    python research/flames_thick/make_build_context.py --eval-code C:/tmp/flames_thick.tar.gz

Copies Dockerfile, requirements-gpu.lock, cloudbuild.yaml and the flames_thick package (code, unit
tests, test fixtures; no caches) and prints the SHA-256 of every file (record it with the image digest).
--eval-code writes the package (without tests) as the tarball the evaluation VM downloads.
"""
import hashlib
import os
import shutil
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP = {"__pycache__", ".pytest_cache"}


def main(dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    for f in ("Dockerfile", "requirements-gpu.lock", "cloudbuild.yaml"):
        shutil.copyfile(os.path.join(HERE, f), os.path.join(dst, f))
    shutil.copytree(HERE, os.path.join(dst, "flames_thick"),
                    ignore=lambda d, names: [n for n in names if n in SKIP or n.endswith(".pyc")
                                             or n in ("Dockerfile", "requirements-gpu.lock", "cloudbuild.yaml")])
    total = 0
    for d, _, files in sorted(os.walk(dst)):
        for f in sorted(files):
            p = os.path.join(d, f)
            total += os.path.getsize(p)
            print(hashlib.sha256(open(p, "rb").read()).hexdigest(), os.path.relpath(p, dst).replace(os.sep, "/"))
    print(f"{total / 1024:.0f} KiB in {dst}")


def eval_code(out):
    skip = SKIP | {"tests", "kaggle_run", "Dockerfile", "requirements-gpu.lock", "cloudbuild.yaml"}
    with tarfile.open(out, "w:gz") as t:
        for d, dirs, files in os.walk(HERE):
            dirs[:] = sorted(x for x in dirs if x not in skip)
            for f in sorted(files):
                if f in skip or f.endswith(".pyc"):
                    continue
                p = os.path.join(d, f)
                t.add(p, arcname=os.path.join("flames_thick", os.path.relpath(p, HERE)).replace(os.sep, "/"))
    print(hashlib.sha256(open(out, "rb").read()).hexdigest(), out)
    print("\n".join(tarfile.open(out).getnames()))


if __name__ == "__main__":
    if sys.argv[1] == "--eval-code":
        eval_code(sys.argv[2])
    else:
        main(sys.argv[1])
