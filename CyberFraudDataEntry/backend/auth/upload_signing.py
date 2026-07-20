"""HMAC-signed URL helper for /uploads/* routes.

Why:
  The `/uploads/*` static mount used to be public — any UUID-guessed
  request would return the file. UUIDs are effectively unguessable
  in practice, but URLs leak (Excel/PDF exports, screenshots, browser
  history), and once a URL is out the file is exposed forever.

Design:
  - `sign_path("uploads/photos/xxx.jpg")` returns the path with `?exp=&sig=`
    query params. Middleware in cyber_fraud.py verifies both on inbound
    GET/HEAD to /uploads/*.
  - HMAC-SHA256 keyed with `settings.JWT_SECRET` (already ≥32 chars,
    fail-loud on default — no new secret to manage).
  - 1-hour default expiry. Short enough that a leaked URL (e.g. baked
    into a downloaded Excel) dies fast; long enough that a user opening
    the record and clicking through in the same session works.
  - Signature is NOT bound to a user — anyone with the URL within the
    validity window can fetch. Justification: internal KSWAN network,
    per-PS access already enforced at the record endpoint that hands
    out the signed URL. This is defence-in-depth against URL leaks,
    not user-identity enforcement.

Verify NEVER trusts the client on the exp value; it recomputes the
HMAC over `<path>:<exp>` and only accepts if the pair matches and
`exp` is in the future. `hmac.compare_digest` is used to keep the
comparison timing-safe.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional
from urllib.parse import urlencode

from config import settings


DEFAULT_TTL_SECONDS = 3600  # 1 hour


def _digest(path: str, exp: int) -> str:
    """HMAC-SHA256 of `<path>:<exp>` keyed with JWT_SECRET, hex-encoded."""
    msg = f"{path}:{exp}".encode("utf-8")
    key = settings.JWT_SECRET.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def sign_path(path: Optional[str], ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Optional[str]:
    """Return `path` with `?exp=&sig=` appended, or None if `path` is None/blank.

    `path` should be the value stored in the DB — no leading slash,
    e.g. "uploads/photos/abc-123.jpg". Downstream response builders
    call this to hand a time-limited URL to the client instead of the
    raw path."""
    if not path:
        return None
    exp = int(time.time()) + ttl_seconds
    sig = _digest(path, exp)
    return f"{path}?{urlencode({'exp': exp, 'sig': sig})}"


def verify_signature(path: str, exp_str: Optional[str], sig: Optional[str]) -> bool:
    """Return True iff `sig` is the correct HMAC for `<path>:<exp>` AND
    `exp` is in the future. Used by the middleware in cyber_fraud.py.

    `path` should be the request path with the leading slash stripped
    (e.g. "uploads/photos/abc-123.jpg") so it matches what `sign_path`
    signed."""
    if not exp_str or not sig:
        return False
    try:
        exp = int(exp_str)
    except (TypeError, ValueError):
        return False
    if exp < int(time.time()):
        return False
    expected = _digest(path, exp)
    return hmac.compare_digest(expected, sig)


def strip_signature(v: Optional[str]) -> Optional[str]:
    """Drop any `?exp=&sig=` tail so we always store the clean path in
    the DB. Called on write in create/update handlers — the frontend
    round-trips the signed value it received on read, and we don't
    want stale query strings piling up in the column."""
    if not v:
        return None
    return v.split("?", 1)[0] or None
