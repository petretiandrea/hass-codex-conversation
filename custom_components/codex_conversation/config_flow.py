"""Config flow — Codex Device Code Auth."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
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
    RECOMMENDED_AI_TASK_OPTIONS,
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Request a device code from Codex API."""
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

    async def async_step_activate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show verification URL/code and wait for authorization."""
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

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create entry with auth data only and default subentries."""
        return self.async_create_entry(
            title="OpenAI Codex",
            data={"auth_implementation": DOMAIN, "token": self._token.as_dict()},
            subentries=[
                {
                    "subentry_type": "conversation",
                    "data": RECOMMENDED_CONVERSATION_OPTIONS,
                    "title": "Codex Conversation",
                    "unique_id": None,
                },
                {
                    "subentry_type": "ai_task_data",
                    "data": RECOMMENDED_AI_TASK_OPTIONS,
                    "title": "Codex AI Task",
                    "unique_id": None,
                },
            ],
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            "conversation": CodexConversationSubentryFlow,
            "ai_task_data": CodexAITaskSubentryFlow,
        }


class _BaseCodexSubentryFlow(ConfigSubentryFlow):
    """Base flow for Codex subentries using model settings."""

    options: dict[str, Any]
    _init_data: dict[str, Any]

    @property
    def _is_new(self) -> bool:
        """Return if this is a new subentry."""
        return self.source == "user"

    @property
    def _default_data(self) -> dict[str, Any]:
        """Default data for a new subentry."""
        raise NotImplementedError

    @property
    def _supports_prompt_and_apis(self) -> bool:
        """Whether this subentry has prompt and Home Assistant controls."""
        return False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle creation of a new subentry."""
        self.options = self._default_data.copy()
        self._init_data = {}
        return await self.async_step_init()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguration of an existing subentry."""
        self.options = self._get_reconfigure_subentry().data.copy()
        self._init_data = {}
        return await self.async_step_init()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manage initial options."""
        if self._get_entry().state != ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        options = self.options

        if user_input is not None:
            if user_input[CONF_RECOMMENDED]:
                data = self._default_data.copy()
                if self._supports_prompt_and_apis:
                    data[CONF_PROMPT] = user_input.get(
                        CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT
                    )
                    data[CONF_LLM_HASS_API] = user_input.get(CONF_LLM_HASS_API) or []
                return self._finalize_subentry(data)

            self._init_data = user_input
            return await self.async_step_advanced()

        if self._supports_prompt_and_apis:
            hass_apis = [
                {"value": api.id, "label": api.name}
                for api in llm.async_get_apis(self.hass)
            ]
            step_schema: dict = {
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
            }
        else:
            step_schema = {
                vol.Required(
                    CONF_RECOMMENDED,
                    default=options.get(CONF_RECOMMENDED, True),
                ): bool,
            }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(step_schema))

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manage advanced options."""
        options = self.options

        if user_input is not None:
            data = {**self._init_data, **user_input}
            return self._finalize_subentry(data)

        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MODEL,
                        default=options.get(CONF_MODEL, DEFAULT_MODEL),
                    ): SelectSelector(SelectSelectorConfig(options=list(MODELS))),
                    vol.Required(
                        CONF_REASONING_EFFORT,
                        default=options.get(
                            CONF_REASONING_EFFORT, RECOMMENDED_REASONING_EFFORT
                        ),
                    ): SelectSelector(
                        SelectSelectorConfig(options=["low", "medium", "high"])
                    ),
                    vol.Required(
                        CONF_REASONING_SUMMARY,
                        default=options.get(
                            CONF_REASONING_SUMMARY, RECOMMENDED_REASONING_SUMMARY
                        ),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=["auto", "short", "detailed", "off"]
                        )
                    ),
                    vol.Required(
                        CONF_TEXT_VERBOSITY,
                        default=options.get(
                            CONF_TEXT_VERBOSITY, RECOMMENDED_TEXT_VERBOSITY
                        ),
                    ): SelectSelector(
                        SelectSelectorConfig(options=["low", "medium", "high"])
                    ),
                }
            ),
        )

    def _finalize_subentry(self, data: dict[str, Any]) -> SubentryFlowResult:
        """Create or update subentry depending on source."""
        model = data.get(CONF_MODEL, DEFAULT_MODEL)
        title = f"Codex ({model})"

        if self._is_new:
            return self.async_create_entry(title=title, data=data)

        return self.async_update_and_abort(
            self._get_entry(),
            self._get_reconfigure_subentry(),
            data=data,
            title=title,
        )


class CodexConversationSubentryFlow(_BaseCodexSubentryFlow):
    """Flow for Codex conversation subentries."""

    @property
    def _default_data(self) -> dict[str, Any]:
        return RECOMMENDED_CONVERSATION_OPTIONS

    @property
    def _supports_prompt_and_apis(self) -> bool:
        return True


class CodexAITaskSubentryFlow(_BaseCodexSubentryFlow):
    """Flow for Codex AI task subentries."""

    @property
    def _default_data(self) -> dict[str, Any]:
        return RECOMMENDED_AI_TASK_OPTIONS
