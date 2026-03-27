"""Tests for the conversation entity and its helper functions."""

from __future__ import annotations

from datetime import date, datetime
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.conversation import (
    AssistantContent,
    Attachment,
    ConverseError,
    SystemContent,
    ToolResultContent,
    UserContent,
)
from homeassistant.helpers import llm
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.codex_conversation.codex_api import (
    CodexApiError,
    CodexContextWindowExceeded,
    CodexQuotaExceeded,
    CodexRateLimited,
    CodexServerOverloaded,
    FunctionCallAdded,
    FunctionCallArgumentsDone,
    OutputTextDelta,
)
from custom_components.codex_conversation.const import (
    CONF_MODEL,
    DOMAIN,
)
from custom_components.codex_conversation.conversation import async_run_chat_log
from custom_components.codex_conversation.transform import (
    build_input_items,
    extract_instructions,
    format_tool,
    json_default,
)

from .conftest import make_chat_log

# ── extract_instructions ───────────────────────────────────────────────────────


def test_extract_instructions_returns_system_content():
    chat_log = make_chat_log(
        [
            SystemContent(content="You are helpful."),
            UserContent(content="Hi"),
        ]
    )
    assert extract_instructions(chat_log) == "You are helpful."


def test_extract_instructions_returns_empty_when_no_system():
    chat_log = make_chat_log([UserContent(content="Hi")])
    assert extract_instructions(chat_log) == ""


def test_extract_instructions_returns_first_system_only():
    chat_log = make_chat_log(
        [
            SystemContent(content="First"),
            SystemContent(content="Second"),
        ]
    )
    assert extract_instructions(chat_log) == "First"


# ── build_input_items ──────────────────────────────────────────────────────────


def test_build_input_items_user_message():
    chat_log = make_chat_log([UserContent(content="Hello")])
    items = build_input_items(chat_log)

    assert len(items) == 1
    assert items[0] == {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": "Hello"}],
    }


def test_build_input_items_skips_system_content():
    chat_log = make_chat_log(
        [
            SystemContent(content="System prompt"),
            UserContent(content="Hello"),
        ]
    )
    items = build_input_items(chat_log)

    assert len(items) == 1
    assert items[0]["role"] == "user"


def test_build_input_items_assistant_text():
    chat_log = make_chat_log(
        [
            AssistantContent(
                agent_id="conversation.codex",
                content="I'm here to help.",
                tool_calls=None,
            ),
        ]
    )
    items = build_input_items(chat_log)

    assert len(items) == 1
    assert items[0] == {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "I'm here to help."}],
    }


def test_build_input_items_assistant_empty_content_skipped():
    chat_log = make_chat_log(
        [AssistantContent(agent_id="conversation.codex", content=None, tool_calls=None)]
    )
    assert build_input_items(chat_log) == []


def test_build_input_items_assistant_tool_calls():
    tool_call = llm.ToolInput(
        id="call_1", tool_name="turn_on", tool_args={"entity_id": "light.living_room"}
    )
    chat_log = make_chat_log(
        [
            AssistantContent(
                agent_id="conversation.codex", content=None, tool_calls=[tool_call]
            )
        ]
    )
    items = build_input_items(chat_log)

    assert len(items) == 1
    assert items[0]["type"] == "function_call"
    assert items[0]["name"] == "turn_on"
    assert items[0]["call_id"] == "call_1"
    assert json.loads(items[0]["arguments"]) == {"entity_id": "light.living_room"}


def test_build_input_items_multiple_tool_calls():
    calls = [
        llm.ToolInput(id="call_1", tool_name="tool_a", tool_args={}),
        llm.ToolInput(id="call_2", tool_name="tool_b", tool_args={}),
    ]
    chat_log = make_chat_log(
        [
            AssistantContent(
                agent_id="conversation.codex", content=None, tool_calls=calls
            )
        ]
    )
    items = build_input_items(chat_log)

    assert len(items) == 2
    assert items[0]["call_id"] == "call_1"
    assert items[1]["call_id"] == "call_2"


def test_build_input_items_tool_result():
    chat_log = make_chat_log(
        [
            ToolResultContent(
                agent_id="conversation.codex",
                tool_call_id="call_1",
                tool_name="turn_on",
                tool_result={"success": True},
            ),
        ]
    )
    items = build_input_items(chat_log)

    assert len(items) == 1
    assert items[0]["type"] == "function_call_output"
    assert items[0]["call_id"] == "call_1"
    assert json.loads(items[0]["output"]) == {"success": True}


def test_build_input_items_tool_result_with_date_value():
    """date objects in tool_result must be serialised as ISO strings."""
    chat_log = make_chat_log(
        [
            ToolResultContent(
                agent_id="conversation.codex",
                tool_call_id="c1",
                tool_name="get_date",
                tool_result={"today": date(2026, 3, 3)},
            ),
        ]
    )
    items = build_input_items(chat_log)
    output = json.loads(items[0]["output"])
    assert output["today"] == "2026-03-03"


def test_build_input_items_full_conversation():
    """Multi-turn conversation with tool call round-trip."""
    tool_call = llm.ToolInput(id="c1", tool_name="get_time", tool_args={})
    chat_log = make_chat_log(
        [
            SystemContent(content="System"),
            UserContent(content="What time is it?"),
            AssistantContent(
                agent_id="conversation.codex", content=None, tool_calls=[tool_call]
            ),
            ToolResultContent(
                agent_id="conversation.codex",
                tool_call_id="c1",
                tool_name="get_time",
                tool_result={"time": "15:00"},
            ),
            AssistantContent(
                agent_id="conversation.codex", content="It's 3pm.", tool_calls=None
            ),
        ]
    )
    items = build_input_items(chat_log)

    types = [i["type"] for i in items]
    assert types == ["message", "function_call", "function_call_output", "message"]
    assert items[0]["role"] == "user"
    assert items[-1]["role"] == "assistant"


# ── json_default ───────────────────────────────────────────────────────────────


def test_json_default_date():
    assert json_default(date(2026, 3, 3)) == "2026-03-03"


def test_json_default_datetime():
    assert json_default(datetime(2026, 3, 3, 15, 0, 0)) == "2026-03-03T15:00:00"


def test_json_default_fallback_to_str():
    class Custom:
        def __str__(self):
            return "custom_value"

    assert json_default(Custom()) == "custom_value"


# ── format_tool ────────────────────────────────────────────────────────────────


def test_format_tool():
    import voluptuous as vol

    tool = MagicMock(spec=llm.Tool)
    tool.name = "turn_on"
    tool.description = "Turn on a device"
    tool.parameters = vol.Schema({vol.Required("entity_id"): str})

    result = format_tool(tool)

    assert result["type"] == "function"
    assert result["name"] == "turn_on"
    assert result["description"] == "Turn on a device"
    assert result["strict"] is False
    assert "parameters" in result


def test_format_tool_empty_description():
    import voluptuous as vol

    tool = MagicMock(spec=llm.Tool)
    tool.name = "ping"
    tool.description = None
    tool.parameters = vol.Schema({})

    result = format_tool(tool)
    assert result["description"] == ""


# ── _async_handle_message — integration ───────────────────────────────────────


async def test_handle_message_simple_text(mock_entity):
    """Happy path: model streams text, entity returns a ConversationResult."""
    chat_log = make_chat_log(
        [
            SystemContent(content="You are helpful."),
            UserContent(content="Hello"),
        ]
    )
    user_input = MagicMock()
    user_input.as_llm_context.return_value = MagicMock()
    user_input.extra_system_prompt = None

    expected = MagicMock()

    async def fake_stream(request):
        yield OutputTextDelta(delta="Hi there!", content_index=0)

    with (
        patch(
            "custom_components.codex_conversation.conversation.CodexClient"
        ) as MockClient,
        patch(
            "custom_components.codex_conversation.conversation.conversation"
            ".async_get_result_from_chat_log",
            return_value=expected,
        ),
    ):
        MockClient.return_value.stream = fake_stream
        result = await mock_entity._async_handle_message(user_input, chat_log)

    assert result is expected
    chat_log.async_provide_llm_data.assert_called_once()


async def test_handle_message_uses_model_from_options(hass, mock_oauth_session):
    """The CodexRequest model must come from conversation subentry data."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="custom_entry",
        data={"auth_implementation": DOMAIN, "token": {}},
    )
    from custom_components.codex_conversation.conversation import (
        CodexConversationEntity,
    )

    subentry = SimpleNamespace(
        subentry_id="conversation_subentry_id",
        title="Codex Conversation",
        subentry_type="conversation",
        data={CONF_MODEL: "gpt-5.3-codex"},
    )
    entity = CodexConversationEntity(hass, entry, mock_oauth_session, subentry)
    entity.entity_id = "conversation.test"
    entity.hass = hass

    captured: list = []

    async def capturing_stream(request):
        captured.append(request)
        yield OutputTextDelta(delta="ok", content_index=0)

    chat_log = make_chat_log([UserContent(content="Hi")])
    user_input = MagicMock()
    user_input.as_llm_context.return_value = MagicMock()
    user_input.extra_system_prompt = None

    with (
        patch(
            "custom_components.codex_conversation.conversation.CodexClient"
        ) as MockClient,
        patch(
            "custom_components.codex_conversation.conversation.conversation"
            ".async_get_result_from_chat_log",
            return_value=MagicMock(),
        ),
    ):
        MockClient.return_value.stream = capturing_stream
        await entity._async_handle_message(user_input, chat_log)

    assert len(captured) == 1
    assert captured[0].model == "gpt-5.3-codex"


@pytest.mark.parametrize(
    "error_cls,args",
    [
        (CodexApiError, (503, "Service unavailable")),
        (CodexContextWindowExceeded, ("Too long",)),
        (CodexQuotaExceeded, ("Quota exceeded",)),
        (CodexRateLimited, ("Rate limited",)),
        (CodexServerOverloaded, ("Overloaded",)),
    ],
)
async def test_handle_message_api_errors_raise_converse_error(
    mock_entity, error_cls, args
):
    """Any CodexError subclass must be re-raised as ConverseError."""
    chat_log = make_chat_log([UserContent(content="Hi")])
    user_input = MagicMock()
    user_input.as_llm_context.return_value = MagicMock()
    user_input.extra_system_prompt = None

    async def error_stream(request):
        raise error_cls(*args)
        if False:
            yield None

    with patch(
        "custom_components.codex_conversation.conversation.CodexClient"
    ) as MockClient:
        MockClient.return_value.stream = error_stream

        with pytest.raises(ConverseError):
            await mock_entity._async_handle_message(user_input, chat_log)


async def test_handle_message_tool_call_loop(mock_entity):
    """When the model makes a tool call, the loop should repeat once for the result."""
    call_counts = [0]

    async def tool_then_text(request):
        call_counts[0] += 1
        if call_counts[0] == 1:
            # First call: model requests a tool
            yield FunctionCallAdded(call_id="c1", name="get_time", item_id="item1")
            yield FunctionCallArgumentsDone(arguments="{}", item_id="item1")
        else:
            # Second call: model responds with text after seeing the tool result
            yield OutputTextDelta(delta="It's 3pm.", content_index=0)

    # Simulate chat_log that has unresponded tool results after first iteration
    unresponded_sequence = [True, False]

    chat_log = make_chat_log([UserContent(content="What time is it?")])
    chat_log.unresponded_tool_results = True  # will be checked after first iteration

    # Override unresponded_tool_results to change between iterations
    side_effects = iter(unresponded_sequence)

    async def drain_and_flip(entity_id, gen):
        async for _ in gen:
            pass
        chat_log.unresponded_tool_results = next(side_effects, False)
        return
        yield

    chat_log.async_add_delta_content_stream = drain_and_flip

    user_input = MagicMock()
    user_input.as_llm_context.return_value = MagicMock()
    user_input.extra_system_prompt = None

    with (
        patch(
            "custom_components.codex_conversation.conversation.CodexClient"
        ) as MockClient,
        patch(
            "custom_components.codex_conversation.conversation.conversation"
            ".async_get_result_from_chat_log",
            return_value=MagicMock(),
        ),
    ):
        MockClient.return_value.stream = tool_then_text
        await mock_entity._async_handle_message(user_input, chat_log)

    assert call_counts[0] == 2


async def test_handle_message_provide_llm_data_error(mock_entity):
    """If async_provide_llm_data raises ConverseError, return its result directly."""
    from homeassistant.helpers import intent

    expected = MagicMock()
    err = ConverseError("llm error", "conv-1", intent.IntentResponse(language="en"))
    err.as_conversation_result = MagicMock(return_value=expected)

    chat_log = make_chat_log([UserContent(content="Hi")])
    chat_log.async_provide_llm_data = AsyncMock(side_effect=err)

    user_input = MagicMock()
    user_input.as_llm_context.return_value = MagicMock()
    user_input.extra_system_prompt = None

    result = await mock_entity._async_handle_message(user_input, chat_log)
    assert result is expected


async def test_async_run_chat_log_appends_attachment_items(tmp_path):
    """The last user message must include attachment items in the request input."""
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake-png-data")

    chat_log = make_chat_log(
        [
            UserContent(
                content="Describe this image",
                attachments=[
                    Attachment(
                        media_content_id="media://camera/image",
                        mime_type="image/png",
                        path=image_path,
                    )
                ],
            )
        ]
    )

    captured_requests: list = []

    class _Client:
        async def stream(self, request):
            captured_requests.append(request)
            yield OutputTextDelta(delta="done", content_index=0)

    await async_run_chat_log(
        chat_log=chat_log,
        client=_Client(),
        model="gpt-5.1-codex",
        entity_id="conversation.codex",
        reasoning_effort="medium",
        reasoning_summary="auto",
        text_verbosity="medium",
    )

    assert len(captured_requests) == 1
    content = captured_requests[0].input[-1]["content"]
    assert any(item["type"] == "input_image" for item in content)
