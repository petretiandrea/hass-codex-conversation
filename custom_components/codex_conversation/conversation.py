"""Conversation platform — OpenAI Codex agent."""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Literal

from homeassistant.components import conversation
from homeassistant.components.conversation import (
    AssistantContent,
    AssistantContentDeltaDict,
    ChatLog,
    ConversationEntity,
    ConversationInput,
    ConversationResult,
    ConverseError,
    SystemContent,
    UserContent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LLM_HASS_API, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .codex_api import (
    CodexApiError,
    CodexClient,
    CodexContextWindowExceeded,
    CodexQuotaExceeded,
    CodexRateLimited,
    CodexRequest,
    CodexServerOverloaded,
    OutputTextDelta,
    ReasoningSummaryDelta,
)
from .const import CONF_MODEL, DEFAULT_MODEL, DOMAIN
from .oauth import CodexHAAuth

_LOGGER = logging.getLogger(__name__)


# ── Platform setup ─────────────────────────────────────────────────────────────

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    session: config_entry_oauth2_flow.OAuth2Session = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CodexConversationEntity(hass, entry, session)])


# ── Entity ─────────────────────────────────────────────────────────────────────

class CodexConversationEntity(ConversationEntity):
    """Conversation agent backed by OpenAI Codex (ChatGPT subscription)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supports_streaming = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
    ) -> None:
        self.hass          = hass
        self._entry        = entry
        self._oauth_session = oauth_session
        self._attr_unique_id = entry.entry_id
        if self._entry.options.get(CONF_LLM_HASS_API):
            self._attr_supported_features = (
                conversation.ConversationEntityFeature.CONTROL
            )

    # ── HA entity properties ───────────────────────────────────────────────────

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return MATCH_ALL

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "OpenAI Codex",
            "manufacturer": "OpenAI",
            "model": self._entry.options.get(CONF_MODEL, DEFAULT_MODEL),
        }

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self._entry, self)

    async def async_will_remove_from_hass(self) -> None:
        conversation.async_unset_agent(self.hass, self._entry)
        await super().async_will_remove_from_hass()

    # ── Conversation handler ───────────────────────────────────────────────────

    async def _async_handle_message(
        self,
        user_input: ConversationInput,
        chat_log: ChatLog,
    ) -> ConversationResult:
        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                self._entry.options.get(CONF_LLM_HASS_API),
                None,
                user_input.extra_system_prompt,
            )
        except ConverseError as err:
            return err.as_conversation_result()

        model = self._entry.options.get(CONF_MODEL, DEFAULT_MODEL)

        # ── Build input items from ChatLog ─────────────────────────────────────
        instructions = ""
        input_items: list[dict] = []

        for content in chat_log.content:
            if isinstance(content, SystemContent):
                instructions = content.content
            elif isinstance(content, UserContent):
                input_items.append({
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": content.content}],
                })
            elif isinstance(content, AssistantContent) and content.content:
                input_items.append({
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": content.content}],
                })

        request = CodexRequest(model=model, input=input_items, instructions=instructions)

        # ── Build auth + client ────────────────────────────────────────────────
        auth = CodexHAAuth(
            session=async_get_clientsession(self.hass),
            oauth_session=self._oauth_session,
        )
        client = CodexClient(auth)

        # ── Stream reply into ChatLog ──────────────────────────────────────────
        try:
            async for _ in chat_log.async_add_delta_content_stream(
                self.entity_id,
                _events_to_deltas(client, request),
            ):
                pass
        except (
            CodexApiError,
            CodexContextWindowExceeded,
            CodexQuotaExceeded,
            CodexRateLimited,
            CodexServerOverloaded,
        ) as err:
            _LOGGER.error("Codex error: %s", err)
            raise ConverseError(str(err)) from err

        return conversation.async_get_result_from_chat_log(user_input, chat_log)


# ── Streaming helpers ──────────────────────────────────────────────────────────

async def _events_to_deltas(
    client: CodexClient,
    request: CodexRequest,
) -> AsyncGenerator[AssistantContentDeltaDict, None]:
    """Convert Codex ResponseEvents to HA's AssistantContentDeltaDict stream."""
    started = False
    async for event in client.stream(request):
        if isinstance(event, OutputTextDelta) and event.delta:
            if not started:
                yield {"role": "assistant"}
                started = True
            yield {"content": event.delta}
        elif isinstance(event, ReasoningSummaryDelta):
            _LOGGER.debug("codex reasoning: %.80s", event.delta)
