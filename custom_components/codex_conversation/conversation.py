"""Conversation platform — OpenAI Codex agent."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import json
import logging
from typing import Literal

from homeassistant.components import conversation
from homeassistant.components.conversation import (
    AssistantContentDeltaDict,
    ChatLog,
    ConversationEntity,
    ConversationInput,
    ConversationResult,
    ConverseError,
    UserContent,
)
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import CONF_LLM_HASS_API, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    config_entry_oauth2_flow,
    device_registry as dr,
    intent,
    llm,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

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
from .transform import (
    async_prepare_files_for_prompt,
    build_input_items,
    extract_instructions,
    format_tool,
)

_LOGGER = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 10


# ── Platform setup ─────────────────────────────────────────────────────────────


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    session: config_entry_oauth2_flow.OAuth2Session = hass.data[DOMAIN][entry.entry_id]

    for subentry in entry.subentries.values():
        if subentry.subentry_type != "conversation":
            continue
        async_add_entities(
            [CodexConversationEntity(hass, entry, session, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


# ── Entity ─────────────────────────────────────────────────────────────────────


class CodexConversationEntity(ConversationEntity):
    """Conversation agent backed by OpenAI Codex (ChatGPT subscription)."""

    _attr_has_entity_name = True
    _attr_name = "Assist"
    _attr_supports_streaming = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
        subentry: ConfigSubentry,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._subentry = subentry
        self._oauth_session = oauth_session
        self._attr_unique_id = subentry.subentry_id
        self._attr_name = subentry.title
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer="OpenAI",
            model=self._options.get(CONF_MODEL, DEFAULT_MODEL),
            entry_type=dr.DeviceEntryType.SERVICE,
        )

        if self._options.get(CONF_LLM_HASS_API):
            self._attr_supported_features = (
                conversation.ConversationEntityFeature.CONTROL
            )

    @property
    def _options(self) -> dict:
        """Return active options for this entity."""
        return self._subentry.data

    # ── HA entity properties ───────────────────────────────────────────────────

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return MATCH_ALL

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
                self._options.get(CONF_LLM_HASS_API),
                self._options.get(CONF_PROMPT),
                user_input.extra_system_prompt,
            )
        except ConverseError as err:
            return err.as_conversation_result()

        model = self._options.get(CONF_MODEL, DEFAULT_MODEL)

        auth = CodexHAAuth(
            session=async_get_clientsession(self.hass),
            oauth_session=self._oauth_session,
        )
        client = CodexClient(auth)
        await async_run_chat_log(
            chat_log=chat_log,
            client=client,
            model=model,
            entity_id=self.entity_id,
            reasoning_effort=self._options.get(
                CONF_REASONING_EFFORT, RECOMMENDED_REASONING_EFFORT
            ),
            reasoning_summary=self._options.get(
                CONF_REASONING_SUMMARY, RECOMMENDED_REASONING_SUMMARY
            ),
            text_verbosity=self._options.get(
                CONF_TEXT_VERBOSITY, RECOMMENDED_TEXT_VERBOSITY
            ),
            error_cls=ConverseError,
        )

        return conversation.async_get_result_from_chat_log(user_input, chat_log)


async def async_run_chat_log(
    *,
    chat_log: ChatLog,
    client: CodexClient,
    model: str,
    entity_id: str,
    reasoning_effort: str,
    reasoning_summary: str,
    text_verbosity: str,
    max_iterations: int = MAX_TOOL_ITERATIONS,
    instructions_suffix: str = "",
    error_cls: type[Exception] = HomeAssistantError,
) -> None:
    """Execute a ChatLog against the Codex Responses API."""
    tools = [format_tool(t) for t in chat_log.llm_api.tools] if chat_log.llm_api else []
    instructions = extract_instructions(chat_log)
    if instructions_suffix:
        instructions = (
            f"{instructions}\n\n{instructions_suffix}"
            if instructions
            else instructions_suffix
        )

    for _iteration in range(max_iterations):
        input_items = build_input_items(chat_log)
        last_content = chat_log.content[-1]
        if isinstance(last_content, UserContent) and last_content.attachments:
            files = await async_prepare_files_for_prompt(
                chat_log.hass,
                [(a.path, a.mime_type) for a in last_content.attachments],
            )
            last_message = input_items[-1]
            if (
                last_message.get("type") == "message"
                and last_message.get("role") == "user"
                and isinstance(last_message.get("content"), list)
            ):
                last_message["content"].extend(files)

        request = CodexRequest(
            model=model,
            input=input_items,
            instructions=instructions,
            tools=tools,
            reasoning_effort=reasoning_effort,
            reasoning_summary=reasoning_summary,
            text_verbosity=text_verbosity,
        )

        try:
            async for _ in chat_log.async_add_delta_content_stream(
                entity_id,
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
            if error_cls is ConverseError:
                raise ConverseError(
                    str(err),
                    chat_log.conversation_id or "",
                    intent.IntentResponse(language="en"),
                ) from err
            raise error_cls(str(err)) from err

        if not chat_log.unresponded_tool_results:
            break


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
