"""Launch design D5's consensus job (research/paper_2/cloud/vm_consensus.sh) on one Spot VM in mstool-research.

It uses paper 1's VM launcher (the same safety layers: self-deleting, wall-clock guard, project fixed), paper 1's
evaluation code at the evaluated commit, and the atlas transforms kept by paper 1's reproduction run. When the VM is
done, it downloads the outputs to research/paper_2/runs/consensus/ (ignored by git; non-commercial sources).

    python -m research.paper_2.launch_consensus --p1 <paper-1 worktree> --p1-commit <sha of the reproduction run>

Paper 1's first run kept no transforms and its affine registration is not bit-reproducible, so the reference is the
reproduction run for everything: transforms, per_unit.csv, lesions.csv, registration.json (PREREG §12, 2026-11-16).
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PROJECT, BK = "mstool-research", "gs://mstool-research-data"
ENV = dict(os.environ, CLOUDSDK_CONFIG="C:/Users/Nicolas/.gcloud-mstool")


def sh(cmd, cwd=None):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=ENV, cwd=cwd)
    if r.returncode != 0:
        raise SystemExit(f"failed: {cmd}\n{r.stderr[-1500:]}")
    return r.stdout


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--p1", required=True, help="paper-1 worktree (its research/cloud/launch_vm.py is used)")
    ap.add_argument("--p1-commit", required=True, help="full sha of paper 1's reproduction run (code + transforms)")
    a = ap.parse_args(argv)
    if sh("git status --porcelain --untracked-files=no -- research/paper_2", cwd=ROOT).strip():
        raise SystemExit("research/paper_2 has uncommitted changes: commit first")
    commit = sh("git rev-parse HEAD", cwd=ROOT).strip()
    rep = f"mimics-eval-{a.p1_commit[:7]}"
    sh(f'gcloud storage ls "{BK}/mimics/evalcode/{a.p1_commit}.tar.gz" --project={PROJECT}')
    regsrc = f"{BK}/mimics/registration/{rep}/registration"
    sh(f'gcloud storage ls "{regsrc}/" --project={PROJECT}')
    sh(f'gcloud storage ls "{BK}/mimics/results/{rep}/DONE" --project={PROJECT}')
    tar = os.path.join(tempfile.mkdtemp(), f"{commit}.tar.gz")
    sh(f'git archive --format=tar.gz -o "{tar}" {commit} research/paper_2', cwd=ROOT)
    sh(f'gcloud storage cp "{tar}" "{BK}/paper2/code/{commit}.tar.gz" --quiet --project={PROJECT}')
    name = f"p2-consensus-{commit[:7]}"
    cmd = [sys.executable, os.path.join(a.p1, "research", "cloud", "launch_vm.py"), "--name", name, "--machine-type",
           "c2d-standard-8", "--disk-gb", "60", "--spot", "--startup", os.path.join(HERE, "cloud", "vm_consensus.sh"),
           "--paper", "2", "--max-hours", "4", "--purpose", "Paper 2 design D5: two-tool consensus on paper 1's masks",
           "--meta", f"p1code=mimics/evalcode/{a.p1_commit}.tar.gz", f"p2code=paper2/code/{commit}.tar.gz",
           f"regsrc={regsrc}", f"p1results={BK}/mimics/results/{rep}", f"commit={commit}", "workers=8"]
    r = subprocess.run(cmd, capture_output=True, text=True, env=ENV, cwd=a.p1)
    print(r.stdout[-1500:])
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise SystemExit("VM launch failed")
    out_uri = f"{BK}/paper2/consensus/{name}"
    print(f"waiting for {out_uri}/DONE (polls every 5 min) ...", flush=True)
    while True:
        time.sleep(300)
        if subprocess.run(f'gcloud storage ls "{out_uri}/DONE" --project={PROJECT}', shell=True, capture_output=True,
                          env=ENV).returncode == 0:
            break
        alive = subprocess.run(f"gcloud compute instances list --project={PROJECT} --filter=name={name} "
                               f"--format=value(name)", shell=True, capture_output=True, text=True, env=ENV).stdout
        if name not in alive:
            raise SystemExit(f"{name} ended without DONE: read {BK}/paper2/logs/{name}.log")
    dst = os.path.join(HERE, "runs", "consensus")
    os.makedirs(dst, exist_ok=True)
    sh(f'gcloud storage cp -r "{out_uri}/*" "{dst}" --quiet --project={PROJECT}')
    print(open(os.path.join(dst, "consensus_gate.json")).read()[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
