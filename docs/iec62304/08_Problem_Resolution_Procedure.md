# MSTool-AI: Software Problem Resolution Procedure

**Document ID**: SPR-001 | **Version**: 1.0 | **Date**: April 12, 2026

---

## 1. Problem Reporting

All software problems are reported via GitHub Issues using the following template:

```
**Problem ID**: AUTO-GENERATED
**Reporter**: [Name]
**Date**: [YYYY-MM-DD]
**Version**: [Software version / Git SHA]
**Severity**: [Critical / Major / Minor]

**Description**: [What happened]
**Steps to Reproduce**: [1. 2. 3.]
**Expected Behavior**: [What should happen]
**Actual Behavior**: [What actually happened]

**Safety Impact Assessment**:
- [ ] Could contribute to a hazardous situation (reference HAZ-ID if yes)
- [ ] Affects a Class C software item
- [ ] Requires regulatory notification (EU MDR Article 87)
```

## 2. Severity Classification

| Severity | Definition | Response Time |
|----------|-----------|---------------|
| **Critical** | Safety impact, data corruption, complete system failure | Immediate (same day) |
| **Major** | Significant functional loss, no workaround | Within 1 week |
| **Minor** | Cosmetic, minor inconvenience, workaround available | Next release cycle |

## 3. Investigation Process

1. **Triage** (within 24 hours of report):
   - Confirm reproducibility
   - Assess safety impact (reference RMF-001)
   - Assign severity
   - Assign to developer

2. **Root Cause Analysis**:
   - Document root cause
   - Identify affected software items and their safety class
   - Assess if similar problems could exist elsewhere
   - For Class C items: document analysis in detail

3. **Impact Analysis**:
   - Identify all affected requirements (SRS-001)
   - Identify all affected risk controls (RMF-001)
   - Determine if previously released versions are affected
   - Determine if regulatory notification required

## 4. Resolution

1. Implement fix following change control (CMP-001)
2. Code review of fix (per code review checklist)
3. Unit tests for fix
4. Regression testing (CI pipeline + test_endpoints.sh)
5. Verify risk controls still effective
6. Close problem report with:
   - Resolution description
   - Verification evidence
   - Commit SHA of fix
   - Affected version and fixed version

## 5. Trend Analysis

Quarterly review of:
- Problem open/close rates
- Time to resolution by severity
- Problems by software item (identify systemic issues)
- Problems by safety class (Class C items tracked separately)

## 6. Records Retention

All problem reports retained for:
- Lifetime of the medical device + 10 years (per EU MDR Article 10(8))
- GitHub Issues provide permanent, version-controlled record

---

*This procedure is maintained under configuration management in the Git repository.*
