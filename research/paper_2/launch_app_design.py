"""Launch E5's state-C job (research/paper_2/cloud/vm_app_design.sh) on one Spot VM in mstool-research (PREREG §12,
2026-11-21), with paper 1's VM launcher (project fixed, self-deleting, wall-clock guard). Uploads the paper-2 code at
HEAD and the application's backend at e559929; uses paper 1's run-3 code (a2affb3), transforms (detreg-a) and results
(mimics-xe-a2affb3). When the VM is done, downloads its outputs to research/paper_2/runs/e5-vm-<VM name>/ (ignored by
git; non-commercial sources).

    python -m research.paper_2.launch_app_design --p1 <paper-1 worktree with research/cloud/launch_vm.py>
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
RUN3_CODE = "a2affb306ca7dfbdb6013f879d5654322a0a2397"
RUN3 = "mimics-xe-a2affb3"
APP_COMMIT = "e559929aaf5a19160e20ffdb64d5790eff70c4d6"


def sh(cmd, cwd=None):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=ENV, cwd=cwd)
    if r.returncode != 0:
        raise SystemExit(f"failed: {cmd}\n{r.stderr[-1500:]}")
    return r.stdout


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--p1", required=True, help="a folder with paper 1's research/cloud/launch_vm.py")
    ap.add_argument("--max-hours", type=int, default=3)
    a = ap.parse_args(argv)
    if sh("git status --porcelain --untracked-files=no -- research/paper_2", cwd=ROOT).strip():
        raise SystemExit("research/paper_2 has uncommitted changes: commit first")
    commit = sh("git rev-parse HEAD", cwd=ROOT).strip()
    sh(f'gcloud storage ls "{BK}/mimics/evalcode/{RUN3_CODE}.tar.gz" --project={PROJECT}')
    regsrc = f"{BK}/mimics/registration/detreg-a/registration"
    sh(f'gcloud storage ls "{regsrc}/" --project={PROJECT}')
    sh(f'gcloud storage ls "{BK}/mimics/results/{RUN3}/DONE" --project={PROJECT}')
    tmp = tempfile.mkdtemp()
    p2 = os.path.join(tmp, f"{commit}.tar.gz")
    sh(f'git archive --format=tar.gz -o "{p2}" {commit} research/paper_2', cwd=ROOT)
    sh(f'gcloud storage cp "{p2}" "{BK}/paper2/code/{commit}.tar.gz" --quiet --project={PROJECT}')
    appt = os.path.join(tmp, f"app-{APP_COMMIT}.tar.gz")
    sh(f'git archive --format=tar.gz -o "{appt}" {APP_COMMIT} backend', cwd=ROOT)
    sh(f'gcloud storage cp "{appt}" "{BK}/paper2/code/app-{APP_COMMIT}.tar.gz" --quiet --project={PROJECT}')
    name = f"p2-e5-{commit[:7]}"
    cmd = [sys.executable, os.path.join(a.p1, "research", "cloud", "launch_vm.py"), "--name", name, "--machine-type",
           "c2d-standard-8", "--disk-gb", "50", "--spot", "--startup", os.path.join(HERE, "cloud", "vm_app_design.sh"),
           "--paper", "2", "--max-hours", str(a.max_hours),
           "--purpose", "Paper 2 E5: the application's DIS and lesion table on the experts' masks (state C)",
           "--meta", f"p1code=mimics/evalcode/{RUN3_CODE}.tar.gz", f"appcode=paper2/code/app-{APP_COMMIT}.tar.gz",
           f"p2code=paper2/code/{commit}.tar.gz", f"regsrc={regsrc}", f"p1results={BK}/mimics/results/{RUN3}",
           f"commit={commit}", "workers=8"]
    r = subprocess.run(cmd, capture_output=True, text=True, env=ENV, cwd=a.p1)
    print(r.stdout[-1500:])
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise SystemExit("VM launch failed")
    out_uri = f"{BK}/paper2/e5/{name}"
    print(f"waiting for {out_uri}/DONE (polls every 3 min) ...", flush=True)
    while True:
        time.sleep(180)
        if subprocess.run(f'gcloud storage ls "{out_uri}/DONE" --project={PROJECT}', shell=True, capture_output=True,
                          env=ENV).returncode == 0:
            break
        alive = subprocess.run(f"gcloud compute instances list --project={PROJECT} --filter=name={name} "
                               f"--format=value(name)", shell=True, capture_output=True, text=True, env=ENV).stdout
        if name not in alive:
            raise SystemExit(f"{name} ended without DONE: read {BK}/paper2/logs/{name}.log")
    dst = os.path.join(HERE, "runs", f"e5-vm-{name}")
    os.makedirs(dst, exist_ok=True)
    sh(f'gcloud storage cp -r "{out_uri}/*" "{dst}" --quiet --project={PROJECT}')
    print(open(os.path.join(dst, "e5_vm_gate.json")).read()[:2500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
