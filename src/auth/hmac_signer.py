"""HMAC signing — implemented but NOT required.

Verification during suite setup (see AUTH_FINDINGS.md) showed the gateway
accepts plain bearer-token auth on every service probed, with no
x-hmac-meta/x-hmac-signature headers at all. This module exists so the
suite can turn signing back on in one place (SEND_HMAC_HEADERS=1) if some
endpoint is ever found that does enforce it — without touching every
client or test.

The signing scheme below is UNVERIFIED — it mirrors the Postman
collection's pre-request script guess (meta-only, HMAC-SHA256 hex). If you
ever need this, re-run tools/probe/probe_auth.py's step 2 against the
specific endpoint that's rejecting bearer-only auth to find the real
payload before trusting this.
"""
import hashlib
import hmac
import time
import uuid
from typing import Dict


def build_hmac_headers(secret: str) -> Dict[str, str]:
    ts = int(time.time())
    nonce = uuid.uuid4().hex[:16]
    meta = f"ts={ts};nonce={nonce}"
    signature = hmac.new(secret.encode(), meta.encode(), hashlib.sha256).hexdigest()
    return {"x-hmac-meta": meta, "x-hmac-signature": signature}
