# MSTool-AI: Configuration Management Plan

**Document ID**: CMP-001 | **Version**: 1.0 | **Date**: April 12, 2026

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
| AI models | Filename + version (brain_screening.onnx) | GCS / public/ |
| Deployment artifacts | Cloud Run revision ID, Firebase deploy version | Cloud console |
| Environment config | env.yaml (not in Git), .env.production | Local / Git |

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

---

*This plan is maintained under configuration management in the Git repository.*
