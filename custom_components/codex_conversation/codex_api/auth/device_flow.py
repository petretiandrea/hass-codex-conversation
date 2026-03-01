"""Device-code OAuth flow for the Codex CLI authentication endpoint."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import aiohttp

from .token import OAuthToken


@dataclass
class DeviceCodeInfo:
    """User-facing information returned when starting a device-code flow."""
    user_code: str
    interval: int  # recommended polling interval in seconds


class CodexDeviceFlow:
    """Encapsulates the full Codex device-code OAuth flow.

    Callers only need two methods:

    - ``initialize()``         — kick off the flow, returns info to show the user.
    - ``wait_authorization()`` — returns an ``asyncio.Task[OAuthToken]`` that
                                 resolves when the user approves. The task can be
                                 cancelled at any time and passed directly to HA's
                                 ``async_show_progress(progress_task=...)``.

    All protocol details (polling interval, ``device_auth_id``, ``code_verifier``,
    authorization-code exchange, …) are hidden inside this class.

    Example::

        flow = CodexDeviceFlow(session, CLIENT_ID, USERCODE_URL,
                               DEVICE_POLL_URL, TOKEN_URL, DEVICE_REDIRECT)
        info = await flow.initialize()
        print(f"Go to {VERIFICATION_URL} and enter: {info.user_code}")

        task = flow.wait_authorization(timeout=900)
        token: OAuthToken = await task  # or pass task to HA progress
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        usercode_url: str,
        poll_url: str,
        token_url: str,
        redirect_uri: str,
    ) -> None:
        self._session = session
        self._client_id = client_id
        self._usercode_url = usercode_url
        self._poll_url = poll_url
        self._token_url = token_url
        self._redirect_uri = redirect_uri
        self._device_auth_id: str = ""
        self._user_code: str = ""
        self._interval: int = 5

    async def initialize(self) -> DeviceCodeInfo:
        """Request a device code and return user-facing info.

        Must be called once before ``wait_authorization()``.
        Raises ``aiohttp.ClientResponseError`` on HTTP errors.
        """
        resp = await self._session.post(
            self._usercode_url, json={"client_id": self._client_id}
        )
        resp.raise_for_status()
        data = await resp.json()

        self._device_auth_id = data["device_auth_id"]
        self._user_code = data.get("user_code") or data.get("usercode", "")
        self._interval = int(data.get("interval", 5))

        return DeviceCodeInfo(user_code=self._user_code, interval=self._interval)

    def wait_authorization(self, timeout: float = 900) -> asyncio.Task[OAuthToken]:
        """Return a task that resolves to an ``OAuthToken`` when the user approves.

        The task polls the server every ``interval`` seconds and exchanges the
        authorization code for a token automatically. It raises ``asyncio.TimeoutError``
        if *timeout* seconds elapse, and can be cancelled at any time.

        The returned task can be passed directly to HA's ``async_show_progress``
        as ``progress_task=``.
        """
        return asyncio.get_event_loop().create_task(self._poll_loop(timeout))

    async def _poll_loop(self, timeout: float) -> OAuthToken:
        async with asyncio.timeout(timeout):
            while True:
                await asyncio.sleep(self._interval)
                token = await self._poll_once()
                if token is not None:
                    return token

    async def _poll_once(self) -> OAuthToken | None:
        """Single poll + token exchange. Returns ``None`` if still pending."""
        resp = await self._session.post(
            self._poll_url,
            json={"device_auth_id": self._device_auth_id, "user_code": self._user_code},
        )
        if resp.status in (403, 404):
            return None
        resp.raise_for_status()
        data = await resp.json()

        token_resp = await self._session.post(
            self._token_url,
            data={
                "grant_type":    "authorization_code",
                "client_id":     self._client_id,
                "code":          data["authorization_code"],
                "code_verifier": data["code_verifier"],
                "redirect_uri":  self._redirect_uri,
            },
        )
        token_resp.raise_for_status()
        return OAuthToken.from_dict(await token_resp.json())
