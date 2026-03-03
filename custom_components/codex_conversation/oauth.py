"""
Home Assistant OAuth2 adapter for the OpenAI Codex integration.

Provides two classes:

- ``CodexHAAuth`` — concrete ``AbstractAuth`` implementation that delegates
  token refresh to HA's ``OAuth2Session``.  This is what ``CodexClient``
  receives inside the integration.

- ``CodexOAuth2Implementation`` — thin ``LocalOAuth2Implementation`` subclass
  that wires the Codex token-refresh HTTP call into HA's OAuth2 machinery.
"""
from __future__ import annotations

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .codex_api.auth import (
    CLIENT_ID,
    TOKEN_URL,
    AbstractAuth,
    OAuthToken,
    refresh_token,
)
from .codex_api.client import CODEX_ENDPOINT
from .const import DOMAIN

# ── HA-aware AbstractAuth implementation ───────────────────────────────────────

class CodexHAAuth(AbstractAuth):
    """``AbstractAuth`` backed by an HA ``OAuth2Session``.

    Calls ``async_ensure_token_valid()`` before every token read so that HA's
    built-in refresh logic runs transparently — ``CodexClient`` never needs to
    know about token expiry.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
    ) -> None:
        super().__init__(session, CODEX_ENDPOINT)
        self._oauth_session = oauth_session

    async def async_get_access_token(self) -> str:
        await self._oauth_session.async_ensure_token_valid()
        return self._oauth_session.token["access_token"]

    async def async_get_account_id(self) -> str:
        return self._oauth_session.token.get("account_id", "")


# ── HA OAuth2 token-refresh implementation ─────────────────────────────────────

class CodexOAuth2Implementation(config_entry_oauth2_flow.LocalOAuth2Implementation):
    """Minimal ``LocalOAuth2Implementation`` — only the refresh path is used.

    The initial token is obtained through the device-code flow in
    ``config_flow.py``; HA calls ``_async_refresh_token`` automatically via
    ``OAuth2Session.async_ensure_token_valid``.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass=hass,
            domain=DOMAIN,
            client_id=CLIENT_ID,
            client_secret="",
            authorize_url="",   # unused — device-code flow
            token_url=TOKEN_URL,
        )

    @property
    def name(self) -> str:
        return "OpenAI Codex"

    async def _async_refresh_token(self, token: dict) -> dict:
        session = async_get_clientsession(self.hass)
        refreshed = await refresh_token(
            session,
            token=OAuthToken.from_dict(token),
            token_url=TOKEN_URL,
            client_id=CLIENT_ID,
        )
        return refreshed.as_dict()
