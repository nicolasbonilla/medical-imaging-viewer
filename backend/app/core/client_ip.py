"""
Client IP address behind Google's front end — CAPA-015 review m9 / re-review N1 (RC-067, RC-068; HAZ-010).

THE DEFECTS
-----------
1. (review m9) Every caller (rate-limit key, IP block list, audit records, CAPTCHA binding, login
   logs) took the FIRST entry of `X-Forwarded-For` — whatever the client sent.
2. (re-review N1) The first fix chose how many right-hand entries to trust from
   `X-Forwarded-Host` — also a header the client sends: a direct call to run.app with
   `X-Forwarded-For: 6.6.6.6` and `X-Forwarded-Host: app.mstool-ai.com` recorded 6.6.6.6. A wrong
   hop count would also have put every user into one per-IP rate-limit bucket (429 at the morning
   login wave).

THE CONTROL
-----------
No header the client can write decides anything. Proxies APPEND to `X-Forwarded-For`:
- the RIGHT-MOST entry is appended by Google's front end in front of Cloud Run: the address that
  actually connected — the client when the call is direct;
- when that right-most address is a published Firebase Hosting (Fastly) EGRESS address, the request
  came through the Hosting rewrite and Hosting appended the client one step to the left; step left,
  and keep stepping only while the entry is such an egress address (a chain through two egress
  hops never collapses to a proxy address).
An egress-looking address written by the client further left is never reached: stepping stops at
the first address that is not an egress address.

THE LIST (EGRESS_CIDRS)
-----------------------
Source: Fastly's published public IP list, EGRESS_SOURCE_URL (JSON keys "addresses" and
"ipv6_addresses"); Firebase Hosting has been served through Fastly (an assumption the preview-channel
check below confirms). Fetched from EGRESS_SOURCE_URL on EGRESS_LIST_DATE (2026-10-24) by the
coordinating agent; EGRESS_CIDRS matches it exactly (21 + 3 ranges). The list changes from time to
time, so it must still be refreshed before go-live.
Update procedure: (1) open EGRESS_SOURCE_URL; (2) replace EGRESS_CIDRS with "addresses" +
"ipv6_addresses" and set EGRESS_LIST_DATE; (3) update the pinned count and addresses in
tests/unit/test_capa015_review2_fixes.py and run it;
(4) at deployment, confirm the real `X-Forwarded-For` through a Firebase Hosting PREVIEW channel
(DEPLOYMENT_CHECKLIST.md). Without a rebuild, the list can be replaced by the Cloud Run setting
TRUSTED_PROXY_CIDRS (comma-separated CIDRs). Local runs without a proxy: TRUST_FORWARDED_FOR=0.

@module core.client_ip (outside core.security: that package imports the audit logger, which imports this)
"""

import ipaddress
import os
from functools import lru_cache
from typing import Optional, Tuple

EGRESS_SOURCE_URL = "https://api.fastly.com/public-ip-list"
EGRESS_LIST_DATE = "2026-10-24"
EGRESS_CIDRS: Tuple[str, ...] = (
    # "addresses" (21)
    "23.235.32.0/20", "43.249.72.0/22", "90.98.0.0/17", "90.98.128.0/18", "103.244.50.0/24",
    "103.245.222.0/23", "103.245.224.0/24", "104.156.80.0/20", "140.248.64.0/18", "140.248.128.0/17",
    "146.75.0.0/17", "151.101.0.0/16", "157.52.64.0/18", "167.82.0.0/17", "167.82.128.0/20",
    "167.82.160.0/20", "167.82.224.0/20", "172.111.64.0/18", "185.31.16.0/22", "199.27.72.0/21",
    "199.232.0.0/16",
    # "ipv6_addresses" (3)
    "2a04:4e40::/32", "2a04:4e42::/31", "2a04:4e44::/32",
)
_MAX_STEPS = 3


@lru_cache(maxsize=8)
def _networks(spec: str):
    nets = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return tuple(nets)


def trusted_networks():
    override = os.environ.get("TRUSTED_PROXY_CIDRS")
    return _networks(override if override is not None else ",".join(EGRESS_CIDRS))


def _is_egress(value: str, nets) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(addr.version == n.version and addr in n for n in nets)


def client_ip(request) -> Optional[str]:
    """The client's address (see module doc). Never decided by a header the client controls."""
    if request is None:
        return None
    xff = [h.strip() for h in (request.headers.get("x-forwarded-for") or "").split(",") if h.strip()]
    if xff and os.environ.get("TRUST_FORWARDED_FOR", "1") != "0":
        nets = trusted_networks()
        i = len(xff) - 1                     # appended by Google's front end
        steps = 0
        while i > 0 and steps < _MAX_STEPS and _is_egress(xff[i], nets):
            i -= 1                           # appended by Firebase Hosting: the client is to the left
            steps += 1
        return xff[i]
    client = getattr(request, "client", None)
    return client.host if client else None
