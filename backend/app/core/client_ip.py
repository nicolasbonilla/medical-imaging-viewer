"""
Client IP address behind Google's front end — CAPA-015 review m9 (RC-067, RC-068; HAZ-010).

THE DEFECT
----------
Every caller (rate-limit key, IP block list, audit records, CAPTCHA binding, login logs) took the
FIRST entry of `X-Forwarded-For`. That entry is whatever the client sent: anyone could pick the
IP recorded in the audit trail and dodge the per-IP rate limit by changing it on every request.

THE CONTROL
-----------
Proxies APPEND to `X-Forwarded-For`; only the entries appended by proxies we operate are
trustworthy. Counting from the RIGHT:
- direct to Cloud Run: Google's front end appends the address it saw, so the client is the
  right-most entry (TRUSTED_PROXY_HOPS = 1, the default);
- through the Firebase Hosting rewrite (requests carrying `X-Forwarded-Host` equal to one of the
  app's hosting domains): Hosting appends the client, then Google's front end appends Hosting's
  egress address, so the client is the second entry from the right
  (FIREBASE_HOSTING_PROXY_HOPS = 2, the default).
The Hosting hop count is an ASSUMPTION from the documented proxy behaviour; it has not been
observed on the deployed service (no cloud access during the change). DEPLOYMENT_CHECKLIST.md
asks to verify it after deployment (compare the recorded IP with your own, on both paths) and the
counts are configurable. With fewer entries than expected hops the left-most entry is used.
Local runs without a proxy: set TRUSTED_PROXY_HOPS=0 to ignore the header.

@module core.client_ip (outside core.security: that package imports the audit logger, which imports this)
"""

import os
from typing import Optional


def _hops(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _hosting_hosts() -> set:
    raw = os.environ.get("FIREBASE_HOSTING_HOSTS",
                         "app.mstool-ai.com,brain-mri-476110.web.app,brain-mri-476110.firebaseapp.com")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def client_ip(request) -> Optional[str]:
    """The client's address: the right-most untrusted hop of X-Forwarded-For (see module doc)."""
    if request is None:
        return None
    headers = request.headers
    xff = [h.strip() for h in (headers.get("x-forwarded-for") or "").split(",") if h.strip()]
    forwarded_host = (headers.get("x-forwarded-host") or "").split(",")[0].strip().lower()
    hops = (_hops("FIREBASE_HOSTING_PROXY_HOPS", 2) if forwarded_host and forwarded_host in _hosting_hosts()
            else _hops("TRUSTED_PROXY_HOPS", 1))
    if xff and hops > 0:
        return xff[max(len(xff) - hops, 0)]
    client = getattr(request, "client", None)
    return client.host if client else None
