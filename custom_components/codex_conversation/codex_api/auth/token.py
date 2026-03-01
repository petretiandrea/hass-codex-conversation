"""Token types, refresh and normalisation helpers."""
from __future__ import annotations

import time
from dataclasses import dataclass

import aiohttp

from .jwt import decode_jwt_exp, extract_account_id


@dataclass
class OAuthToken:
    """Typed representation of a Codex OAuth token."""
    access_token: str
    refresh_token: str
    account_id: str
    expires_at: float
    expires_in: int

    def as_dict(self) -> dict:
        """Serialise to the dict format expected by HA's OAuth2Session."""
        return {
            "access_token":  self.access_token,
            "refresh_token": self.refresh_token,
            "account_id":    self.account_id,
            "expires_at":    self.expires_at,
            "expires_in":    self.expires_in,
        }

    @classmethod
    def from_dict(cls, data: dict, previous: "OAuthToken | None" = None) -> "OAuthToken":
        """Build an ``OAuthToken`` from a raw server response dict."""
        access_token  = data.get("access_token", "")
        refresh_token = data.get("refresh_token") or (previous.refresh_token if previous else "")
        account_id    = (
            data.get("account_id")
            or extract_account_id(access_token)
            or (previous.account_id if previous else "")
        )

        expires_in = data.get("expires_in")
        if not expires_in:
            expires_in = max(0, int(decode_jwt_exp(access_token) - time.time()))

        expires_at = data.get("expires_at", time.time() + expires_in)

        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            account_id=account_id,
            expires_at=float(expires_at),
            expires_in=int(expires_in),
        )


async def refresh_token(
    session: aiohttp.ClientSession,
    token: OAuthToken,
    token_url: str,
    client_id: str,
) -> OAuthToken:
    """Refresh an access token. Raises ``aiohttp.ClientResponseError`` on failure."""
    resp = await session.post(
        token_url,
        data={
            "grant_type":    "refresh_token",
            "client_id":     client_id,
            "refresh_token": token.refresh_token,
        },
    )
    resp.raise_for_status()
    return OAuthToken.from_dict(await resp.json(), previous=token)
