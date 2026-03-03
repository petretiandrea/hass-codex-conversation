"""AbstractAuth and the simple static-token implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod

import aiohttp

_CODEX_FIXED_HEADERS = {
    "openai-beta": "responses=experimental",
    "openai-originator": "codex_cli_rs",
}


class AbstractAuth(ABC):
    """Abstract base class for Codex API authentication.

    Follows the HA API library auth pattern:
    https://developers.home-assistant.io/docs/api_lib_auth

    Subclasses implement ``async_get_access_token()`` (and optionally
    ``async_get_account_id()``) to supply fresh credentials; this class
    handles assembling the Codex-specific request headers.

    ``CodexClient`` depends only on ``AbstractAuth``, never on raw tokens,
    so token refresh is fully transparent to the client.
    """

    def __init__(self, session: aiohttp.ClientSession, endpoint: str) -> None:
        self._session = session
        self._endpoint = endpoint

    @abstractmethod
    async def async_get_access_token(self) -> str:
        """Return a currently-valid bearer token.

        Refresh the token here if needed before returning.
        """

    async def async_get_account_id(self) -> str:
        """Return the OpenAI account / organisation ID (may be empty)."""
        return ""

    async def request(self, method: str, **kwargs: object) -> aiohttp.ClientResponse:
        """Make an authenticated request to the Codex endpoint.

        Injects ``Authorization``, ``openai-beta``, ``openai-originator``, and
        (when available) ``openai-organization`` into every request.
        Extra headers passed via ``headers=`` are merged on top.
        """
        extra_headers = dict(kwargs.pop("headers", {}))  # type: ignore[arg-type]

        access_token = await self.async_get_access_token()
        account_id = await self.async_get_account_id()

        headers = {
            **_CODEX_FIXED_HEADERS,
            "Authorization": f"Bearer {access_token}",
            **extra_headers,
        }
        if account_id:
            headers["openai-organization"] = account_id

        return await self._session.request(
            method,
            self._endpoint,
            headers=headers,
            **kwargs,  # type: ignore[arg-type]
        )


class CodexAuth(AbstractAuth):
    """Concrete ``AbstractAuth`` backed by a static access token.

    Useful for standalone scripts and unit tests where HA is not present::

        async with aiohttp.ClientSession() as session:
            auth = CodexAuth(session, CODEX_ENDPOINT, access_token, account_id)
            client = CodexClient(auth)
            async for event in client.stream(request):
                ...
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        endpoint: str,
        access_token: str,
        account_id: str = "",
    ) -> None:
        super().__init__(session, endpoint)
        self._access_token = access_token
        self._account_id = account_id

    async def async_get_access_token(self) -> str:
        return self._access_token

    async def async_get_account_id(self) -> str:
        return self._account_id
