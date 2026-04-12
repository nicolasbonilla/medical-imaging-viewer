# MSTool-AI: Software Release Procedure

## IEC 62304 Clause 5.8 — Release Management

**Document ID**: REL-001
**Version**: 1.0
**Effective Date**: April 12, 2026

---

## 1. Release Types

| Type | Versioning | Trigger | Approval |
|------|-----------|---------|----------|
| **Major** (X.0.0) | Increment major | New features, architecture changes | Project Lead + Clinical Review |
| **Minor** (x.Y.0) | Increment minor | Feature additions, enhancements | Project Lead |
| **Patch** (x.y.Z) | Increment patch | Bug fixes, security patches | Developer + Reviewer |

---

## 2. Pre-Release Checklist

### 2.1 Verification Completeness (Clause 5.8.1)

| Check | Required For | Evidence |
|-------|-------------|----------|
| [ ] All unit tests pass (Class C) | All releases | CI pipeline green |
| [ ] Integration tests pass | All releases | test_endpoints.sh 9/9 PASS |
| [ ] TypeScript compilation successful | All releases | CI: `npx tsc --noEmit` |
| [ ] Python syntax check passes | All releases | CI: ast.parse all .py files |
| [ ] Code review completed for all changes | All releases | GitHub PR approvals |
| [ ] No critical/major open bugs | Major/Minor | GitHub Issues reviewed |
| [ ] Risk analysis updated (if applicable) | Major | RMF-001 reviewed |
| [ ] SOUP list updated (if dependencies changed) | Major/Minor | SOUP-001 checked |
| [ ] Traceability matrix updated | Major | TM-001 updated |
| [ ] Clinical review completed | Major | Clinical advisor sign-off |

### 2.2 Known Residual Anomalies (Clause 5.8.2, 5.8.3)

| Anomaly | Severity | Safety Impact | Disposition | Rationale |
|---------|----------|-------------|-------------|-----------|
| (Document all known issues here per release) | | | | |

---

## 3. Release Process

### Step 1: Create Release Branch
```bash
git checkout -b release/vX.Y.Z
```

### Step 2: Run Full Verification Suite
```bash
# Frontend
cd frontend && npx tsc --noEmit && npm run build && npx vitest run

# Backend
cd backend && python -m pytest tests/ -v

# Endpoint verification
bash test_endpoints.sh
```

### Step 3: Version Bump
Update version in `package.json`, relevant documentation headers.

### Step 4: Create Release Tag
```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z — [description]"
git push origin vX.Y.Z
```

### Step 5: Deploy Backend
```bash
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=COMMIT_SHA=$(git rev-parse --short HEAD)
```

### Step 6: Deploy Frontend
```bash
cd frontend && npm run build && npx firebase deploy --only hosting
```

### Step 7: Post-Deploy Verification
```bash
bash test_endpoints.sh
```

### Step 8: Document Release
Create GitHub Release with:
- Version number
- Change summary
- Known anomalies list
- SOUP changes (if any)
- Deployment record (build ID, deploy URL)

---

## 4. Release Archive (Clause 5.8.7)

| Artifact | Storage | Retention |
|----------|---------|-----------|
| Source code | Git repository (tagged) | Lifetime of device + 10 years |
| Build artifacts | Google Container Registry | 5 years |
| Test results | GitHub Actions artifacts | 5 years |
| Release notes | GitHub Releases | Lifetime of device |
| Deployment logs | Cloud Run revision history | 2 years |

---

## 5. Rollback Procedure

If post-deploy verification fails:

1. **Frontend**: Firebase Hosting supports instant rollback to previous version via console
2. **Backend**: Cloud Run supports traffic splitting and instant revision rollback
3. **Document**: Record rollback in problem resolution system (SPR-001)

---

### References

[1] IEC 62304:2006+AMD1:2015, Clause 5.8.1–5.8.8
[2] ISO 13485:2016, Clause 7.5.6 (Control of production and service provision — Validation)
