"""Input sanitization helpers to defend against stored XSS (CWE-20).

React already escapes output by default, but server-side stripping adds
defense-in-depth for any non-React consumer (exports, admin tools,
third-party integrations) and prevents persisted payloads from existing
at all.
"""
from __future__ import annotations

import re
from typing import Optional

# Matches any HTML tag (opening, closing, self-closing)
_TAG_RE = re.compile(r"<[^>]*>")

# Matches "javascript:" URIs (case-insensitive), often used in XSS payloads
_JS_URI_RE = re.compile(r"javascript\s*:", re.IGNORECASE)

# Matches HTML event handler attribute fragments like `onerror=`, `onclick=`
_ON_EVENT_RE = re.compile(r"\bon\w+\s*=", re.IGNORECASE)


def strip_html(value: Optional[str]) -> Optional[str]:
    """Strip HTML tags and obvious XSS payload markers. Returns None if
    input is None, empty string if stripped to nothing, else cleaned text.

    Does NOT attempt to preserve any HTML — this is used on fields that
    should be plain text only (case facts, crime numbers, victim names)."""
    if value is None:
        return None
    cleaned = _TAG_RE.sub("", value)
    cleaned = _JS_URI_RE.sub("", cleaned)
    cleaned = _ON_EVENT_RE.sub("", cleaned)
    return cleaned.strip()
