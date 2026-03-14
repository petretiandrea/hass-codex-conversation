"""JWT decoding utilities — no external dependencies beyond the stdlib."""

from __future__ import annotations

import base64
import json
import time


def decode_jwt_exp(token: str) -> float:
    """Extract the ``exp`` Unix timestamp from a JWT; returns now+1h on failure."""
    parts = token.split(".")
    if len(parts) != 3:
        return time.time() + 3600
    try:
        pad = 4 - len(parts[1]) % 4
        payload = base64.urlsafe_b64decode(parts[1] + "=" * pad)
        return float(json.loads(payload).get("exp", time.time() + 3600))
    except Exception:
        return time.time() + 3600


def extract_account_id(access_token: str) -> str:
    """Extract ``chatgpt_account_id`` (or ``sub``) from an OpenAI JWT."""
    parts = access_token.split(".")
    if len(parts) != 3:
        return ""
    try:
        pad = 4 - len(parts[1]) % 4
        payload = base64.urlsafe_b64decode(parts[1] + "=" * pad)
        data = json.loads(payload)
        auth = data.get("https://api.openai.com/auth", {})
        return auth.get("chatgpt_account_id") or data.get("sub", "")
    except Exception:
        return ""
