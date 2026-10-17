# MSTool-AI: Configuration Management Plan

**Document ID**: CMP-001 | **Version**: 1.1 DRAFT (2026-10-17, §6 model artefacts added, §5 observation; PENDING owner approval) — last approved: 1.0 | **Date**: April 12, 2026

---

## 1. Configuration Items

| Item Type | Identification | Storage |
|-----------|---------------|---------|
| Source code | Git commit SHA | GitHub repository |
| Frontend dependencies | package.json + package-lock.json (pinned) | npm registry |
| Backend dependencies | requirements.txt (pinned) | PyPI |
| Build configuration | Dockerfile, cloudbuild.yaml, vite.config.ts | Git |
| CI/CD pipeline | .github/workflows/ci.yml | Git |
| Test scripts | test_endpoints.sh, backend/tests/ | Git |
| Documentation | docs/ directory | Git |
| AI models | Filename + version (brain_screening.onnx); in-browser FLAMeS: SHA-256 pin in `plan.ts` + committed manifest (§6) | GCS / public/; FLAMeS: archive per §6 (not Git) |
| Deployment artifacts | Cloud Run revision ID, Firebase deploy version | Cloud console |
| Environment config | env.yaml (not in Git), .env.production | Local / Git |

**Fillable PDF templates**: `TPL-09_Change_Control_Record.pdf` (TPL-CCR-001), `TPL-03_Code_Review_Checklist.pdf` (TPL-CR-001)

## 2. Change Control Process

```
1. Developer creates feature branch from main
2. Implements change with:
   - Commit messages referencing requirement/issue IDs
   - Unit tests for new/changed code
3. Submits pull request with:
   - Description of change
   - Impact analysis
   - Test evidence
4. Reviewer performs code review (per CR checklist)
5. CI pipeline must pass (TypeScript, build, tests, syntax)
5.1 CI pipeline must pass ALL gates (no failure suppression):
   - TypeScript compilation, frontend build, frontend tests
   - Backend unit tests with coverage reporting
   - Backend integration tests
   - SOUP vulnerability scanning (npm audit + pip-audit)
   - Python syntax check
6. Reviewer approves PR
7. Merge to main (squash merge preferred)
8. For backend: deploy via Cloud Build + verify with test_endpoints.sh
9. For frontend: build + firebase deploy + visual verification
```

## 3. Branch Protection Rules

- Direct pushes to `main` branch: **PROHIBITED**
- Pull request required: **YES**
- CI status checks must pass: **YES**
- At least 1 approving review: **REQUIRED**

## 3.1 Code Ownership (IEC 62304 Clause 5.5.4)

Code review responsibility is enforced via `.github/CODEOWNERS`:

| Module Category | Required Reviewer |
|----------------|-------------------|
| Class C backend services | @nicolasbonilla |
| Edge AI Worker | @nicolasbonilla |
| Regulatory documentation | @nicolasbonilla |
| CI/CD pipeline | @nicolasbonilla |
| Security-critical code | @nicolasbonilla |

## 4. Release Management

| Step | Action | Evidence |
|------|--------|----------|
| 1 | Create release tag (vX.Y.Z) | Git tag |
| 2 | Run full test suite | CI pipeline results |
| 3 | Run test_endpoints.sh (pre-deploy) | Script output |
| 4 | Deploy backend (Cloud Build) | Build ID + status |
| 5 | Deploy frontend (Firebase) | Deploy URL |
| 6 | Run test_endpoints.sh (post-deploy) | Script output |
| 7 | Document release | Release notes in Git |

## 5. SOUP Version Control

- All SOUP versions pinned (no `^` or `~` in production)
- Version updates require: impact analysis + regression testing
- Vulnerability scanning: monthly (npm audit + pip-audit)
- *Observation 2026-10-17 (CP-FLAMES-BROWSER-001):* `frontend/package.json` still declares most dependencies with `^`;
  the lockfile is what pins them. The Class C runtime `onnxruntime-web` is now pinned exactly (`1.24.1`); the other
  ranges are an open item for the owner.

## 6. Binary model artefacts not stored in Git (added 2026-10-17, DRAFT — PENDING owner approval)

Applies to the in-browser FLAMeS model (SOUP-FE-014). The 62 MB file is **not committed to Git**
(`frontend/public/models/flames/` is git-ignored).

| Aspect | Rule |
|---|---|
| Identity | Content address = SHA-256. Fold 0: `flames-fold0.onnx`, 61,642,305 B, sha256 `2a10bb9d72dc33381a3f44dd6a59ec612dfd87534e02f15488b426ae127176ae`, exported from Zenodo 10.5281/zenodo.17955359 v2.0 checkpoint sha256 `4fc7db24…3fdf861` by `research/flames_in_browser/export_onnx.py` (torch 2.14.1, opset 17). |
| Pin (in Git) | `frontend/src/services/flames/plan.ts` → `FLAMES_FOLD0_MODEL` (`sha256`, `bytes`, content-addressed URL `/models/flames/flames-fold0-2a10bb9d.onnx`). The browser refuses any other bytes, downloaded or cached (RC-040, REQ-SAFE-031). |
| Provenance record (in Git) | `docs/research/flames-in-browser/evidence/export-fold0-manifest.json` (hash, size, source checkpoint, versions, export checks). A CI-safe test (`draft-model.test.ts`, "CM: the pin equals the committed export manifest") fails if the pin and the manifest disagree or if the model folder stops being git-ignored. |
| Archive (proposed, not yet created — no cloud command was run) | Primary: `gs://mstool-research-data/models/flames/v2.0/flames-fold0-2a10bb9d72dc.onnx` + the manifest next to it, bucket in the research project `mstool-research`, object versioning on, retention lock after approval. Storage cost ≈ 0.06 GB × Standard ≈ USD 0.001/month (inside the research credit). Secondary: attach the same file to the GitHub release that ships it (release assets need no LFS quota). |
| Rejected option | Git LFS: GitHub's free LFS quota (1 GB storage, 1 GB/month transfer) would be consumed by ~16 CI checkouts of a 62 MB file per month, i.e. a recurring cost or failing CI. |
| Release step | Fetch the archived file, then `python -I research/flames_in_browser/stage_model.py <file>`: verifies size + SHA-256 against `plan.ts` **and** the committed manifest, copies it to `frontend/public/models/flames/<content-addressed name>`, re-hashes the copy; exit ≠ 0 stops the release. Then `vite build`. |
| Change | A new model (other fold, ensemble, re-export) is a new artefact with a new hash and a new pin: a Class C change (CP + SRS/RMF/TM update + parity evidence, DESIGN.md §5). Never overwrite an archived object. |

---

*This plan is maintained under configuration management in the Git repository.*
