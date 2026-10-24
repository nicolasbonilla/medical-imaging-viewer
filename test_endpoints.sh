#!/bin/bash
# MSTool-AI Endpoint Verification Script
# Run BEFORE and AFTER every backend deploy to ensure nothing is broken
# Usage: bash test_endpoints.sh

BASE="${MSTOOL_API_BASE:-https://brain-mri-7bp6oqdu7a-uc.a.run.app/api/v1}"
# CAPA-015: the auth routes are also served on the app's own origin (Firebase Hosting rewrite).
APP_ORIGIN="${MSTOOL_APP_ORIGIN:-https://app.mstool-ai.com}"
PASS=0
FAIL=0

check() {
    local name="$1"
    local expected="$2"
    local actual="$3"
    if [ "$actual" = "$expected" ]; then
        echo "  PASS: $name ($actual)"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $name (expected $expected, got $actual)"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== MSTool-AI Endpoint Verification ==="
echo "Base: $BASE"
echo ""

# 0. Hosting rewrite of /api/v1/auth/** (CAPA-015 RC-068) — needs NO password.
# Without a cookie, POST /refresh must reach FastAPI and answer its 401 JSON — not index.html
# (rewrite missing) and not 404/405 (backend older than the change).
echo "[0] Session refresh through the app origin ($APP_ORIGIN)..."
REFRESH_OUT=$(curl -s -o /tmp/mstool_refresh_body.$$ -w "%{http_code} %{content_type}" -X POST "$APP_ORIGIN/api/v1/auth/refresh")
REFRESH_CODE="${REFRESH_OUT%% *}"
REFRESH_TYPE="${REFRESH_OUT#* }"
if [ "$REFRESH_CODE" = "401" ] && echo "$REFRESH_TYPE" | grep -qi "application/json" && grep -q '"detail"' /tmp/mstool_refresh_body.$$; then
    echo "  PASS: POST /api/v1/auth/refresh without cookie -> 401 JSON from the API"
    PASS=$((PASS + 1))
else
    echo "  FAIL: POST /api/v1/auth/refresh without cookie -> $REFRESH_CODE ($REFRESH_TYPE); expected 401 application/json with \"detail\""
    FAIL=$((FAIL + 1))
fi
rm -f /tmp/mstool_refresh_body.$$
if [ "${1:-}" = "--hosting-only" ]; then
    echo "=== Results: $PASS passed, $FAIL failed ==="
    [ "$FAIL" -gt 0 ] && exit 1 || exit 0
fi

# Never hardcode the production admin password. Require it from the environment
# and fail fast if it is not set (checks below need it; check [0] above does not).
ADMIN_PASSWORD="${ADMIN_DEFAULT_PASSWORD:?ADMIN_DEFAULT_PASSWORD must be set (export it before running; do not hardcode the production admin password)}"

# 1. Health check
echo "[1/8] Health check..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE%/api/v1}/")
check "Root health" "200" "$STATUS"

# 2. Login
echo "[2/8] Login..."
LOGIN_RESPONSE=$(curl -s "$BASE/auth/login" -X POST -H "Content-Type: application/json" --data-raw "{\"username\":\"admin\",\"password\":\"$ADMIN_PASSWORD\"}")
TOKEN=$(echo "$LOGIN_RESPONSE" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('token',{}).get('access_token',''))" 2>/dev/null)
if [ -n "$TOKEN" ] && [ "$TOKEN" != "" ]; then
    echo "  PASS: Login (token received)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: Login (no token)"
    FAIL=$((FAIL + 1))
    echo "  Response: $LOGIN_RESPONSE"
    echo ""
    echo "ABORTING: Cannot continue without valid token"
    echo "Results: $PASS passed, $FAIL failed"
    exit 1
fi

# 3. Auth/me
echo "[3/8] Auth/me..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/auth/me" -H "Authorization: Bearer $TOKEN")
check "GET /auth/me" "200" "$STATUS"

# 4. Protected endpoint (auth.py - uses get_current_active_user)
echo "[4/8] Protected endpoints (auth.py)..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/auth/users" -H "Authorization: Bearer $TOKEN")
check "GET /auth/users" "200" "$STATUS"

# 5. WebAuthn endpoints
echo "[5/8] WebAuthn..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/auth/webauthn/credentials" -H "Authorization: Bearer $TOKEN")
check "GET /auth/webauthn/credentials" "200" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/auth/webauthn/register/begin" -X POST -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{}')
check "POST /auth/webauthn/register/begin" "200" "$STATUS"

# 6. Segmentation endpoints
echo "[6/8] Segmentation..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/segmentation/list?file_ids=test" -H "Authorization: Bearer $TOKEN")
check "GET /segmentation/list" "200" "$STATUS"

# 7. WebAuthn login flow
echo "[7/8] WebAuthn login/begin..."
# 200 if user has passkeys, 400 if no passkeys registered — both are valid
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/auth/webauthn/login/begin" -X POST -H "Content-Type: application/json" -d '{"username":"admin"}')
if [ "$STATUS" = "200" ] || [ "$STATUS" = "400" ]; then
    echo "  PASS: POST /auth/webauthn/login/begin ($STATUS — endpoint responsive)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: POST /auth/webauthn/login/begin ($STATUS)"
    FAIL=$((FAIL + 1))
fi

# 8. CAPTCHA
echo "[8/8] CAPTCHA..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/auth/captcha" -X POST -H "Content-Type: application/json" -d '{"difficulty":"medium"}')
check "POST /auth/captcha" "200" "$STATUS"

# 9. Login through the app origin sets the refresh cookie (CAPA-015 RC-068)
echo "[9] Login on $APP_ORIGIN sets the __session cookie..."
COOKIE_HDR=$(curl -s -D - -o /dev/null "$APP_ORIGIN/api/v1/auth/login" -X POST -H "Content-Type: application/json" --data-raw "{\"username\":\"admin\",\"password\":\"$ADMIN_PASSWORD\"}" | grep -i '^set-cookie: __session=' | tr 'A-Z' 'a-z')
if echo "$COOKIE_HDR" | grep -q "httponly" && echo "$COOKIE_HDR" | grep -q "secure" && echo "$COOKIE_HDR" | grep -q "samesite=strict"; then
    echo "  PASS: Set-Cookie __session (HttpOnly; Secure; SameSite=Strict)"
    PASS=$((PASS + 1))
else
    echo "  FAIL: no __session cookie with HttpOnly, Secure, SameSite=Strict on login through $APP_ORIGIN"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "WARNING: Some endpoints failed!"
    exit 1
else
    echo "All endpoints working correctly."
    exit 0
fi
