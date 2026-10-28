# MSTool-AI — Deployment Checklist

## Required Environment Variables on Cloud Run

Every deploy via `cloudbuild.yaml` uses `--update-env-vars` to preserve
these. If any is missing after a deploy, re-set it manually.

| Variable | Purpose | How to set |
|---|---|---|
| `ENVIRONMENT` | Runtime mode (production/development) | `gcloud run services update brain-mri --update-env-vars ENVIRONMENT=production` |
| `REDIS_HOST` | Redis connection for caching/sessions | Same pattern |
| `JWT_SECRET_KEY` | JWT signing key for auth tokens | Same pattern |
| `ENCRYPTION_MASTER_KEY` | AES-256 key for password encryption. **If this is wrong or missing, ALL logins fail with "Key mismatch"** | Same pattern. Value in `backend/.env` |
| `CORS_ORIGINS` | Comma-separated allowed origins. **Must use `,` not `;`** | `--update-env-vars "^;;^CORS_ORIGINS=https://brain-mri-476110.web.app,https://app.mstool-ai.com"` |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID | Set in cloudbuild.yaml |
| `GCS_BUCKET_NAME` | Cloud Storage bucket for medical images | Same pattern |
| `GCS_PROJECT_ID` | GCS project | Same pattern |
| `ANTHROPIC_API_KEY` | Claude API for AI features | Same pattern |

## Verify after deploy

```bash
# 1) Check all env vars present (should show 9 names)
gcloud run services describe brain-mri --region=us-central1 \
  --project=brain-mri-476110 \
  --format="value(spec.template.spec.containers[0].env[].name)"

# 2) Test login works
curl -s -w "\nHTTP: %{http_code}\n" \
  -X POST -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_DEFAULT_PASSWORD\"}" \
  "https://brain-mri-209356685171.us-central1.run.app/api/v1/auth/login" | tail -2

# 3) Test CORS
curl -s -D - -o /dev/null \
  -H "Origin: https://app.mstool-ai.com" \
  "https://brain-mri-7bp6oqdu7a-uc.a.run.app/api/v1/auth/me" 2>&1 | grep "access-control-allow-origin"
```

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| "Incorrect username or password" | `ENCRYPTION_MASTER_KEY` missing or wrong | Re-set from `backend/.env` |
| CORS blocked in browser | `CORS_ORIGINS` uses `;` instead of `,` | Re-set with comma separator |
| Login works via curl but not browser | CORS + different URL aliases | Add ALL Cloud Run URLs to CORS_ORIGINS |
| 500 on all endpoints | Missing required env var | Check the 9-var list above |

## Accounts (PRB-020, PRB-024 — DRAFT, PENDING owner approval)

- **Do not set `SELF_REGISTRATION_ENABLED`** on Cloud Run. Self-registration is off by default; with
  `ENVIRONMENT=production` the setting is ignored anyway (a warning is logged). Turning it on for any production use
  needs a code change, a code review and the owner's regulatory decision (EU MDR "making available").
- Check after deploy: `curl -s https://<backend>/api/v1/auth/registration` must answer
  `{"self_registration_enabled":false,"account_creation":"administrator"}`, and the sign-in page must show no
  Register tab.
- Accounts are created by an administrator: `POST /api/v1/auth/users` with an administrator token
  (`username`, `email`, `full_name`, `password`, `role`). The first password is handed over through a separate channel.
- Before the first deployment of this change: review every existing account (`GET /api/v1/auth/users`) and deactivate
  self-registered or unknown accounts (PRB-020 §7).

## Care teams — run BEFORE deploying the backend of PR #70 (PRB-021, PRB-023 — DRAFT, PENDING owner approval)

After this change a clinician sees only the patients of their care team. Records created by clinicians before it have no
assignment, so their creators would see "No patients are assigned to you yet".
1. Save the account list: `GET /api/v1/auth/users` with an administrator token → `users.json`.
2. Dry run (writes nothing; prints patient ids and creator usernames):
   `python scripts/owner/prb021_backfill_creator_care_team.py --project brain-mri-476110 --users-json users.json --granted-by <your admin user id>`
3. Read the plan and the skipped groups (legacy records without provenance, administrator creators, unknown or inactive
   accounts, existing or revoked rows). Then the same command with `--apply`, type `ASSIGN`; keep the backup file it writes
   (it lists the created ids; to undo, revoke exactly those: `DELETE /api/v1/patients/{id}/care-team/{assignment_id}`).
   Never with the Daita project (the script refuses it); never from an automated agent.
4. Assign the remaining treating clinicians, and triage legacy records (`GET /api/v1/patients/quarantined`), before
   telling users about the change.
5. Only then deploy the backend; after deploy, sign in as a clinician and check that their patients are listed.
