"""Conversation platform — OpenAI Codex agent."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date, datetime
import json
import logging
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
    ToolResultContent,
    UserContent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LLM_HASS_API, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow, llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from voluptuous_openapi import convert

from .codex_api import (
    CodexApiError,
    CodexClient,
    CodexContextWindowExceeded,
    CodexQuotaExceeded,
    CodexRateLimited,
    CodexRequest,
    CodexServerOverloaded,
    FunctionCallAdded,
    FunctionCallArgumentsDone,
    OutputTextDelta,
    ReasoningSummaryDelta,
)
from .const import (
    CONF_MODEL,
    CONF_PROMPT,
    CONF_REASONING_EFFORT,
    CONF_REASONING_SUMMARY,
    CONF_TEXT_VERBOSITY,
    DEFAULT_MODEL,
    DOMAIN,
    RECOMMENDED_REASONING_EFFORT,
    RECOMMENDED_REASONING_SUMMARY,
    RECOMMENDED_TEXT_VERBOSITY,
)
from .oauth import CodexHAAuth

_LOGGER = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 10


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
        self.hass = hass
        self._entry = entry
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
                self._entry.options.get(CONF_PROMPT),
                user_input.extra_system_prompt,
            )
        except ConverseError as err:
            return err.as_conversation_result()

        model = self._entry.options.get(CONF_MODEL, DEFAULT_MODEL)

        auth = CodexHAAuth(
            session=async_get_clientsession(self.hass),
            oauth_session=self._oauth_session,
        )
        client = CodexClient(auth)

        # ── Tool loop ──────────────────────────────────────────────────────────
        tools = (
            [_format_tool(t) for t in chat_log.llm_api.tools]
            if chat_log.llm_api
            else []
        )
        instructions = _extract_instructions(chat_log)

        for _iteration in range(MAX_TOOL_ITERATIONS):
            input_items = _build_input_items(chat_log)
            request = CodexRequest(
                model=model,
                input=input_items,
                instructions=instructions,
                tools=tools,
                reasoning_effort=self._entry.options.get(
                    CONF_REASONING_EFFORT, RECOMMENDED_REASONING_EFFORT
                ),
                reasoning_summary=self._entry.options.get(
                    CONF_REASONING_SUMMARY, RECOMMENDED_REASONING_SUMMARY
                ),
                text_verbosity=self._entry.options.get(
                    CONF_TEXT_VERBOSITY, RECOMMENDED_TEXT_VERBOSITY
                ),
            )

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

            if not chat_log.unresponded_tool_results:
                break

        return conversation.async_get_result_from_chat_log(user_input, chat_log)


# ── Request building ───────────────────────────────────────────────────────────


def _json_default(obj: object) -> str:
    """Fallback serialiser for types json.dumps can't handle natively."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return str(obj)


def _format_tool(tool: llm.Tool) -> dict:
    """Format an HA LLM tool as an OpenAI Responses API function definition."""
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description or "",
        "parameters": convert(tool.parameters),
        "strict": False,
    }


def _extract_instructions(chat_log: ChatLog) -> str:
    """Return the system instructions from the ChatLog (stable across iterations)."""
    for content in chat_log.content:
        if isinstance(content, SystemContent):
            return content.content
    return ""


def _build_input_items(chat_log: ChatLog) -> list[dict]:
    """Build the input items list from the ChatLog (rebuilt each iteration)."""
    items: list[dict] = []

    for content in chat_log.content:
        if isinstance(content, SystemContent):
            pass  # handled separately as instructions
        elif isinstance(content, UserContent):
            items.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": content.content}],
                }
            )
        elif isinstance(content, AssistantContent):
            if content.tool_calls:
                for tc in content.tool_calls:
                    items.append(
                        {
                            "type": "function_call",
                            "name": tc.tool_name,
                            "arguments": json.dumps(tc.tool_args),
                            "call_id": tc.id,
                        }
                    )
            elif content.content:
                items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": content.content}],
                    }
                )
        elif isinstance(content, ToolResultContent):
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": content.tool_call_id,
                    "output": json.dumps(content.tool_result, default=_json_default),
                }
            )

    return items


# ── Streaming helpers ──────────────────────────────────────────────────────────


async def _events_to_deltas(
    client: CodexClient,
    request: CodexRequest,
) -> AsyncGenerator[AssistantContentDeltaDict, None]:
    """Convert Codex ResponseEvents to HA's AssistantContentDeltaDict stream."""
    started = False
    # Maps item_id → (call_id, tool_name) so we can reconstruct ToolInput on done.
    pending_calls: dict[str, tuple[str, str]] = {}

    async for event in client.stream(request):
        if isinstance(event, OutputTextDelta) and event.delta:
            if not started:
                yield {"role": "assistant"}
                started = True
            yield {"content": event.delta}

        elif isinstance(event, FunctionCallAdded):
            pending_calls[event.item_id] = (event.call_id, event.name)
            if not started:
                yield {"role": "assistant"}
                started = True

        elif isinstance(event, FunctionCallArgumentsDone):
            call_id, name = pending_calls.get(event.item_id, ("", ""))
            try:
                tool_args = json.loads(event.arguments or "{}")
            except json.JSONDecodeError:
                tool_args = {}
            yield {
                "tool_calls": [
                    llm.ToolInput(
                        id=call_id,
                        tool_name=name,
                        tool_args=tool_args,
                    )
                ]
            }

        elif isinstance(event, ReasoningSummaryDelta):
            _LOGGER.debug("codex reasoning: %.80s", event.delta)
