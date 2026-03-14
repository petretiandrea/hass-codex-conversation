"""Tests for integration setup / teardown (__init__.py)."""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, patch

from custom_components.codex_conversation import (
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.codex_conversation.const import DOMAIN

# ── async_setup ────────────────────────────────────────────────────────────────


async def test_async_setup_registers_oauth_implementation(hass):
    """async_setup must register the Codex OAuth2 implementation with HA."""
    with patch(
        "custom_components.codex_conversation.config_entry_oauth2_flow"
        ".async_register_implementation"
    ) as mock_register:
        result = await async_setup(hass, {})

    assert result is True
    mock_register.assert_called_once_with(hass, DOMAIN, ANY)


# ── async_setup_entry ──────────────────────────────────────────────────────────


async def test_async_setup_entry_stores_session(hass, mock_config_entry):
    """Setup must store an OAuth2Session in hass.data[DOMAIN][entry_id]."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.codex_conversation"
            ".config_entry_oauth2_flow.async_get_config_entry_implementation",
            return_value=AsyncMock(),
        ),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", return_value=True
        ),
    ):
        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True
    assert DOMAIN in hass.data
    assert mock_config_entry.entry_id in hass.data[DOMAIN]


async def test_async_setup_entry_registers_update_listener(hass, mock_config_entry):
    """Setup must register an options-update listener so reloads are triggered."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.codex_conversation"
            ".config_entry_oauth2_flow.async_get_config_entry_implementation",
            return_value=AsyncMock(),
        ),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", return_value=True
        ),
    ):
        await async_setup_entry(hass, mock_config_entry)

    # HA registers listeners via entry.async_on_unload; verify at least one was added
    assert len(mock_config_entry._on_unload) >= 1


# ── async_unload_entry ────────────────────────────────────────────────────────


async def test_async_unload_entry_removes_session(hass, mock_config_entry):
    """Unload must remove the session from hass.data and return True."""
    hass.data.setdefault(DOMAIN, {})[mock_config_entry.entry_id] = MagicMock()

    with patch.object(hass.config_entries, "async_unload_platforms", return_value=True):
        result = await async_unload_entry(hass, mock_config_entry)

    assert result is True
    assert mock_config_entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_async_unload_entry_returns_false_on_platform_failure(
    hass, mock_config_entry
):
    """If platform unload fails, the session must not be removed."""
    hass.data.setdefault(DOMAIN, {})[mock_config_entry.entry_id] = MagicMock()

    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        result = await async_unload_entry(hass, mock_config_entry)

    assert result is False
    assert mock_config_entry.entry_id in hass.data[DOMAIN]
