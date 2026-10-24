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

## Audit trail and session refresh (CAPA-015 — DRAFT, PENDING owner approval)

No new **required** variable. Optional variables (defaults shown):

| Variable | Default | Purpose |
|---|---|---|
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access-token lifetime (was 60) |
| `REFRESH_TOKEN_IDLE_MINUTES` | `30` | Refresh session dies after this long without a refresh (owner decision D-2) |
| `REFRESH_TOKEN_ABSOLUTE_HOURS` | `12` | Fresh sign-in at least once per shift (owner decision D-2) |
| `AUDIT_SINK_BACKEND` | `firestore` | `memory` / `off` only for tests and local runs — the admin banner then says "not durable" |
| `AUDIT_FLUSH_WAIT_MS` | `500` | Longest wait for a request's own audit records (Cloud Run throttles CPU between requests) |
| `AUDIT_READ_DEDUP_SECONDS` | `300` | One durable record per actor, route and resource for repeated reads |
| `REFRESH_TOKEN_BACKEND` | `firestore` | `memory` only for tests |

More optional variables (review of PR #65): `REFRESH_TOKEN_REUSE_GRACE_SECONDS` (`30`),
`AUDIT_HASH_KEY` (secret for the keyed hashes in audit records; if unset it is derived from
`JWT_SECRET_KEY` — rotating that secret then changes every hash), `AUDIT_SOURCE_BUDGET` /
`AUDIT_SOURCE_WINDOW_S` (`30` / `60`: durable failed-or-anonymous records per source IP),
`TRUSTED_PROXY_HOPS` (`1`), `FIREBASE_HOSTING_PROXY_HOPS` (`2`), `FIREBASE_HOSTING_HOSTS`.

**Session lifetimes check (review M1).** The service refuses to start when
`REFRESH_TOKEN_IDLE_MINUTES` ≤ `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` + 2 (Cloud Run then keeps the
previous revision). Before deploying, read the current values:
`gcloud run services describe brain-mri --region=us-central1 --project=brain-mri-476110 --format="value(spec.template.spec.containers[0].env)"`
— neither variable set means 15 / 30 (fine). Never set the access lifetime back to 60 without
raising the idle limit above 62.

Deployment window and order (the owner runs it; nothing was run by the change):

1. **Outside clinical hours, back to back**: deploy the backend (`bash scripts/deploy_backend.sh`),
   then hosting at once (`cd frontend && npm run build && npx firebase deploy --only hosting`).
   `firebase.json` rewrites `/api/v1/auth/**` on the app's own origin to the Cloud Run service
   `brain-mri` (same project), so the `__session` refresh cookie (HttpOnly, Secure,
   SameSite=Strict) is first-party; Firebase Hosting forwards no other cookie name. Between the
   two steps the new page may meet the old backend: a 404/405 from `/refresh` opens the re-login
   dialog and keeps the work (review M4), it never discards it.
2. Ask users to **reload** the app (a tab still running the old page gets 15-minute sessions and
   no silent renewal until it reloads).
3. **Firestore indexes only**: `firebase deploy --only firestore:indexes` — the three composite
   indexes that filtered `/auth/audit-logs` queries (by actor, event type, outcome) need; without
   them a filtered read answers 503.
4. **Do NOT deploy `firestore.rules` as part of this change** unless the owner decides so after a
   diff. The repository's rules let ANY Firebase-authenticated user read and write `patients`,
   `studies` and `documents`; deploying them could CHANGE the live rules. First compare with the
   live rules (Firebase console → Firestore → Rules, or `firebase firestore:rules:get` if
   available); the backend uses the Admin SDK and does not need the rule changes to work.
5. Optional, recommended: Firestore TTL policies on `refresh_tokens.expires_at` and
   `refresh_token_families.absolute_expires_at`; a log-based alert on
   `AUDIT_SINK_WRITE_FAILED`, `AUDIT_RECORD_DROPPED`, `REFRESH_STORE_UNAVAILABLE`.
6. Verify on **https://app.mstool-ai.com**:
   - `bash test_endpoints.sh --hosting-only` (no password needed): `POST /api/v1/auth/refresh`
     without a cookie must answer FastAPI's **401 JSON** (`{"detail": …}`) — not `index.html`
     (rewrite missing) and not 404/405 (old backend);
   - `bash test_endpoints.sh` (with `ADMIN_DEFAULT_PASSWORD`): check [9] — login through the app
     origin returns `Set-Cookie: __session=…; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`;
   - as administrator, `GET /api/v1/auth/audit-status` answers `"state": "ok"` and
     `GET /api/v1/auth/audit-logs?limit=5` lists the sign-in;
   - **client IP (review m9)**: sign in once through the app origin and once directly against
     the Cloud Run URL, and check that the `ip_address` of both audit records is YOUR address. The
     Firebase Hosting hop count (2) is an assumption not observed before deployment; adjust
     `FIREBASE_HOSTING_PROXY_HOPS` / `TRUSTED_PROXY_HOPS` if not.
   - if the app is also opened on `brain-mri-476110.firebaseapp.com`, add that origin to
     `CORS_ORIGINS` (refresh refuses origins outside it).

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| "Incorrect username or password" | `ENCRYPTION_MASTER_KEY` missing or wrong | Re-set from `backend/.env` |
| CORS blocked in browser | `CORS_ORIGINS` uses `;` instead of `,` | Re-set with comma separator |
| Login works via curl but not browser | CORS + different URL aliases | Add ALL Cloud Run URLs to CORS_ORIGINS |
| 500 on all endpoints | Missing required env var | Check the 9-var list above |
| Users asked to sign in again every 15 min; no `__session` cookie | Hosting deployed without the `/api/v1/auth/**` rewrite, or backend older than the rewrite | Deploy backend, then hosting (CAPA-015) |
| Red "Audit trail" banner for administrators | Firestore writes of `audit_logs` failing (records kept in the server log) | Check the service account's Firestore access and the logs for `AUDIT_SINK_WRITE_FAILED` |
