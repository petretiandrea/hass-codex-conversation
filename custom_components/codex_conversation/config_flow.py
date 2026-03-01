"""Config flow — Codex Device Code Auth."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .codex_api.auth import CodexDeviceFlow, OAuthToken
from .const import (
    CLIENT_ID,
    CONF_MODEL,
    DEFAULT_MODEL,
    DEVICE_POLL_URL,
    DEVICE_REDIRECT,
    DOMAIN,
    MODELS,
    TOKEN_URL,
    USERCODE_URL,
    VERIFICATION_URL,
)

_LOGGER = logging.getLogger(__name__)


class CodexConversationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow: request device code, show URL + code, wait for approval."""

    VERSION = 1

    def __init__(self) -> None:
        self._flow: CodexDeviceFlow | None = None
        self._user_code: str = ""
        self._auth_task: asyncio.Task[OAuthToken] | None = None

    # ── Step 1: request device code ────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        try:
            session = async_get_clientsession(self.hass)
            self._flow = CodexDeviceFlow(
                session, CLIENT_ID, USERCODE_URL, DEVICE_POLL_URL, TOKEN_URL, DEVICE_REDIRECT
            )
            info = await self._flow.initialize()
            self._user_code = info.user_code
        except Exception:
            _LOGGER.exception("Failed to request device code")
            return self.async_show_form(
                step_id="user",
                errors={"base": "token_exchange_failed"},
                data_schema=vol.Schema({}),
            )

        return await self.async_step_activate()

    # ── Step 2: show URL + code, wait for approval ─────────────────────────────

    async def async_step_activate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if not self._auth_task:
            self._auth_task = self._flow.wait_authorization(timeout=900)

        if not self._auth_task.done():
            return self.async_show_progress(
                step_id="activate",
                progress_action="waiting_for_auth",
                description_placeholders={
                    "url": VERIFICATION_URL,
                    "code": self._user_code or "—",
                },
                progress_task=self._auth_task,
            )

        try:
            self._token = self._auth_task.result()
            _LOGGER.info("Device code flow succeeded.")
        except Exception:
            _LOGGER.exception("Device code flow failed")
            return self.async_abort(reason="oauth_error")

        return self.async_show_progress_done(next_step_id="options")

    # ── Step 3: pick model ──────────────────────────────────────────────────────

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="OpenAI Codex",
                data={"auth_implementation": DOMAIN, "token": self._token.as_dict()},
                options={CONF_MODEL: user_input[CONF_MODEL]},
            )

        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema({
                vol.Required(CONF_MODEL, default=DEFAULT_MODEL): vol.In(MODELS),
            }),
        )

    # ── Options flow ────────────────────────────────────────────────────────────

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "CodexOptionsFlow":
        return CodexOptionsFlow()


class CodexOptionsFlow(OptionsFlow):

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_MODEL,
                    default=self.config_entry.options.get(CONF_MODEL, DEFAULT_MODEL),
                ): vol.In(MODELS),
            }),
        )
