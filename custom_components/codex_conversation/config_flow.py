"""Config flow — Codex Device Code Auth."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.core import callback
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    TemplateSelector,
)
import voluptuous as vol

from .codex_api.auth import VERIFICATION_URL, CodexDeviceFlow, OAuthToken
from .const import (
    CONF_MODEL,
    CONF_PROMPT,
    CONF_REASONING_EFFORT,
    CONF_REASONING_SUMMARY,
    CONF_RECOMMENDED,
    CONF_TEXT_VERBOSITY,
    DEFAULT_MODEL,
    DOMAIN,
    MODELS,
    RECOMMENDED_CONVERSATION_OPTIONS,
    RECOMMENDED_REASONING_EFFORT,
    RECOMMENDED_REASONING_SUMMARY,
    RECOMMENDED_TEXT_VERBOSITY,
)

_LOGGER = logging.getLogger(__name__)


class CodexConversationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow: request device code, show URL + code, wait for approval."""

    VERSION = 1

    def __init__(self) -> None:
        self._flow: CodexDeviceFlow | None = None
        self._user_code: str = ""
        self._auth_task: asyncio.Task[OAuthToken] | None = None
        self._token: OAuthToken | None = None

    # ── Step 1: request device code ────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        try:
            session = async_get_clientsession(self.hass)
            self._flow = CodexDeviceFlow(session)
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

        return self.async_show_progress_done(next_step_id="finish")

    # ── Step 3: create entry with recommended defaults ─────────────────────────

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_create_entry(
            title="OpenAI Codex",
            data={"auth_implementation": DOMAIN, "token": self._token.as_dict()},
            options=RECOMMENDED_CONVERSATION_OPTIONS,
        )

    # ── Options flow ────────────────────────────────────────────────────────────

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "CodexOptionsFlow":
        return CodexOptionsFlow()


class CodexOptionsFlow(OptionsFlow):

    def __init__(self) -> None:
        self._init_data: dict = {}

    # ── Step 1: recommended toggle + prompt + LLM API ──────────────────────────

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = self.config_entry.options

        if user_input is not None:
            if user_input[CONF_RECOMMENDED]:
                return self.async_create_entry(data={
                    **RECOMMENDED_CONVERSATION_OPTIONS,
                    CONF_LLM_HASS_API: user_input.get(CONF_LLM_HASS_API) or [],
                    CONF_PROMPT: user_input.get(CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT),
                })
            self._init_data = user_input
            return await self.async_step_advanced()

        hass_apis = [
            {"value": api.id, "label": api.name}
            for api in llm.async_get_apis(self.hass)
        ]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_PROMPT,
                    description={
                        "suggested_value": options.get(
                            CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT
                        )
                    },
                ): TemplateSelector(),
                vol.Optional(CONF_LLM_HASS_API): SelectSelector(
                    SelectSelectorConfig(options=hass_apis, multiple=True)
                ),
                vol.Required(
                    CONF_RECOMMENDED,
                    default=options.get(CONF_RECOMMENDED, True),
                ): bool,
            }),
        )

    # ── Step 2: model + reasoning (only when recommended=False) ────────────────

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = self.config_entry.options

        if user_input is not None:
            return self.async_create_entry(data={**self._init_data, **user_input})

        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_MODEL,
                    default=options.get(CONF_MODEL, DEFAULT_MODEL),
                ): SelectSelector(SelectSelectorConfig(options=list(MODELS))),
                vol.Required(
                    CONF_REASONING_EFFORT,
                    default=options.get(CONF_REASONING_EFFORT, RECOMMENDED_REASONING_EFFORT),
                ): SelectSelector(
                    SelectSelectorConfig(options=["low", "medium", "high"])
                ),
                vol.Required(
                    CONF_REASONING_SUMMARY,
                    default=options.get(CONF_REASONING_SUMMARY, RECOMMENDED_REASONING_SUMMARY),
                ): SelectSelector(
                    SelectSelectorConfig(options=["auto", "short", "detailed", "off"])
                ),
                vol.Required(
                    CONF_TEXT_VERBOSITY,
                    default=options.get(CONF_TEXT_VERBOSITY, RECOMMENDED_TEXT_VERBOSITY),
                ): SelectSelector(
                    SelectSelectorConfig(options=["low", "medium", "high"])
                ),
            }),
        )
