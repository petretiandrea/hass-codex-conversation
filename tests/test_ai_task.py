"""Tests for the AI Task entity."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.components import ai_task as ai_task_component
from homeassistant.components.conversation import AssistantContent
import pytest
import voluptuous as vol

from custom_components.codex_conversation.ai_task import (
    CodexAITaskEntity,
    _format_structure_instruction,
)
from custom_components.codex_conversation.codex_api import OutputTextDelta
from custom_components.codex_conversation.const import DOMAIN

from .conftest import make_chat_log


@pytest.fixture
def mock_ai_task_entity(hass, mock_config_entry, mock_oauth_session) -> CodexAITaskEntity:
    """A CodexAITaskEntity wired to hass but not added to the entity registry."""
    entity = CodexAITaskEntity(hass, mock_config_entry, mock_oauth_session)
    entity.entity_id = f"ai_task.{DOMAIN}"
    entity.hass = hass
    return entity


async def test_generate_data_returns_text_result(mock_ai_task_entity):
    """The entity should return plain text when no structure is requested."""
    chat_log = make_chat_log([AssistantContent(content="Result text", tool_calls=None)])
    chat_log.conversation_id = "conv-1"
    task = MagicMock(spec=ai_task_component.GenDataTask)
    task.structure = None
    task.name = "summarize"

    async def fake_stream(request):
        yield OutputTextDelta(delta="Result text", content_index=0)

    with patch("custom_components.codex_conversation.ai_task.CodexClient") as MockClient:
        MockClient.return_value.stream = fake_stream
        result = await mock_ai_task_entity._async_generate_data(task, chat_log)

    assert result.conversation_id == "conv-1"
    assert result.data == "Result text"


async def test_generate_data_parses_json_result(mock_ai_task_entity):
    """Structured tasks should parse the assistant text as JSON."""
    chat_log = make_chat_log(
        [AssistantContent(content='{"answer":"ok"}', tool_calls=None)]
    )
    chat_log.conversation_id = "conv-2"
    task = MagicMock(spec=ai_task_component.GenDataTask)
    task.structure = vol.Schema({vol.Required("answer"): str})
    task.name = "extract"

    async def fake_stream(request):
        yield OutputTextDelta(delta='{"answer":"ok"}', content_index=0)

    with patch("custom_components.codex_conversation.ai_task.CodexClient") as MockClient:
        MockClient.return_value.stream = fake_stream
        result = await mock_ai_task_entity._async_generate_data(task, chat_log)

    assert result.conversation_id == "conv-2"
    assert result.data == {"answer": "ok"}


def test_format_structure_instruction():
    """The structured output helper should request JSON-only output."""
    task = MagicMock(spec=ai_task_component.GenDataTask)
    task.structure = vol.Schema({vol.Required("name"): str, vol.Optional("age"): int})

    instruction = _format_structure_instruction(task)

    assert "Return only valid JSON." in instruction
    assert "name" in instruction
    assert "age" in instruction
