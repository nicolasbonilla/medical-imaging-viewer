#!/bin/bash
# MSTool-AI Endpoint Verification Script
# Run BEFORE and AFTER every backend deploy to ensure nothing is broken
# Usage: bash test_endpoints.sh

BASE="https://brain-mri-7bp6oqdu7a-uc.a.run.app/api/v1"
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

# 1. Health check
echo "[1/8] Health check..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE%/api/v1}/")
check "Root health" "200" "$STATUS"

# 2. Login
echo "[2/8] Login..."
LOGIN_RESPONSE=$(curl -s "$BASE/auth/login" -X POST -H "Content-Type: application/json" --data-raw '{"username":"admin","password":"Admin123!@2024"}')
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

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "WARNING: Some endpoints failed!"
    exit 1
else
    echo "All endpoints working correctly."
    exit 0
fi
