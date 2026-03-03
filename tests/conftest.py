"""Shared fixtures for the Codex Conversation integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.codex_conversation.const import (
    DOMAIN,
    RECOMMENDED_CONVERSATION_OPTIONS,
)
from custom_components.codex_conversation.conversation import CodexConversationEntity

ENTRY_ID = "test_entry_id"

TOKEN_DICT = {
    "access_token": "test_access_token",
    "refresh_token": "test_refresh_token",
    "account_id": "test_account_id",
    "expires_at": 9_999_999_999.0,
    "expires_in": 3600,
}


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Config entry pre-loaded with recommended options."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id=ENTRY_ID,
        data={"auth_implementation": DOMAIN, "token": TOKEN_DICT},
        options=RECOMMENDED_CONVERSATION_OPTIONS,
    )


@pytest.fixture
def mock_oauth_session() -> MagicMock:
    """Minimal OAuth2Session stub."""
    session = MagicMock()
    session.token = TOKEN_DICT
    session.async_ensure_token_valid = AsyncMock()
    return session


@pytest.fixture
def mock_entity(hass, mock_config_entry, mock_oauth_session) -> CodexConversationEntity:
    """A CodexConversationEntity wired to hass but not added to the entity registry."""
    entity = CodexConversationEntity(hass, mock_config_entry, mock_oauth_session)
    entity.entity_id = f"conversation.{DOMAIN}"
    entity.hass = hass
    return entity


# ── ChatLog helpers ────────────────────────────────────────────────────────────


async def drain_generator(entity_id, gen):
    """Async-generator drop-in for ChatLog.async_add_delta_content_stream.

    Consumes the delta generator (so the code under test actually runs) and
    yields nothing — simulating HA's internal handling without needing a real
    ChatLog instance.
    """
    async for _ in gen:
        pass
    return


def make_chat_log(content: list, *, llm_api=None, unresponded=False) -> MagicMock:
    """Return a minimal ChatLog mock for use in conversation tests."""
    chat_log = MagicMock()
    chat_log.async_provide_llm_data = AsyncMock()
    chat_log.async_add_delta_content_stream = drain_generator
    chat_log.content = content
    chat_log.llm_api = llm_api
    chat_log.unresponded_tool_results = unresponded
    return chat_log
