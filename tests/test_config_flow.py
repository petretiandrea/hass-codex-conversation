"""Tests for dynamic model selection in config flows."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType

from custom_components.codex_conversation.codex_api.auth import OAuthToken
from custom_components.codex_conversation.config_flow import (
    CodexConversationConfigFlow,
    CodexConversationSubentryFlow,
    _fallback_model_options,
    _selected_or_first,
)
from custom_components.codex_conversation.const import (
    CONF_MODEL,
    DOMAIN,
    RECOMMENDED_CONVERSATION_OPTIONS,
)


def test_retired_model_falls_back_to_first_available() -> None:
    """A retired configured model should not remain the selector default."""
    options = [
        {"value": "gpt-current", "label": "Current"},
        {"value": "gpt-next", "label": "Next"},
    ]

    assert _selected_or_first("gpt-retired", options) == "gpt-current"
    assert _selected_or_first("gpt-next", options) == "gpt-next"


def test_fallback_options_preserve_retired_model_for_retry_form() -> None:
    """A failed refresh should still render the configured value while retrying."""
    options = _fallback_model_options("gpt-retired")

    assert options[0] == {"value": "gpt-retired", "label": "gpt-retired"}
    assert len({option["value"] for option in options}) == len(options)


async def test_initial_model_step_uses_live_catalog(hass) -> None:
    """The post-OAuth step should show live models and save the selection."""
    flow = CodexConversationConfigFlow()
    flow.hass = hass
    flow._token = OAuthToken(
        access_token="access-token",
        refresh_token="refresh-token",
        account_id="account-id",
        expires_at=9_999_999_999.0,
        expires_in=3600,
    )
    live_options = [
        {"value": "gpt-live", "label": "GPT Live"},
        {"value": "gpt-next", "label": "GPT Next"},
    ]

    with patch(
        "custom_components.codex_conversation.config_flow.async_fetch_model_catalog",
        AsyncMock(return_value=live_options),
    ) as fetch_models:
        result = await flow.async_step_model()
        created = await flow.async_step_model({CONF_MODEL: "gpt-next"})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "model"
    assert created["type"] is FlowResultType.CREATE_ENTRY
    assert all(
        subentry["data"][CONF_MODEL] == "gpt-next" for subentry in created["subentries"]
    )
    fetch_models.assert_awaited_once()


async def test_initial_model_step_recovers_from_catalog_failure(hass) -> None:
    """A discovery failure should keep the flow open and retry next submit."""
    flow = CodexConversationConfigFlow()
    flow.hass = hass
    flow._token = OAuthToken(
        access_token="access-token",
        refresh_token="refresh-token",
        account_id="account-id",
        expires_at=9_999_999_999.0,
        expires_in=3600,
    )

    with patch(
        "custom_components.codex_conversation.config_flow.async_fetch_model_catalog",
        AsyncMock(side_effect=RuntimeError("catalog unavailable")),
    ) as fetch_models:
        result = await flow.async_step_model()
        retry = await flow.async_step_model({CONF_MODEL: "gpt-5.4-codex"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "models_fetch_failed"}
    assert retry["type"] is FlowResultType.FORM
    assert retry["errors"] == {"base": "models_fetch_failed"}
    assert fetch_models.await_count == 2


async def test_subentry_form_refreshes_models_and_replaces_retired_default(
    hass,
) -> None:
    """Every subentry form should refresh models and offer a valid default."""
    flow = CodexConversationSubentryFlow()
    flow.hass = hass
    flow.options = {
        **RECOMMENDED_CONVERSATION_OPTIONS,
        CONF_MODEL: "gpt-retired",
    }
    flow._init_data = {}
    flow._model_options = None

    entry = MagicMock(state=ConfigEntryState.LOADED, entry_id="entry-id")
    flow._get_entry = MagicMock(return_value=entry)
    oauth_session = MagicMock()
    oauth_session.token = {
        "access_token": "access-token",
        "account_id": "account-id",
    }
    oauth_session.async_ensure_token_valid = AsyncMock()
    hass.data[DOMAIN] = {entry.entry_id: oauth_session}
    live_options = [
        {"value": "gpt-current", "label": "GPT Current"},
        {"value": "gpt-next", "label": "GPT Next"},
    ]

    with patch(
        "custom_components.codex_conversation.config_flow.async_fetch_model_catalog",
        AsyncMock(return_value=live_options),
    ) as fetch_models:
        result = await flow.async_step_init()

    model_marker = next(
        marker for marker in result["data_schema"].schema if marker.schema == CONF_MODEL
    )
    assert result["type"] is FlowResultType.FORM
    assert model_marker.default() == "gpt-current"
    oauth_session.async_ensure_token_valid.assert_awaited_once()
    fetch_models.assert_awaited_once()
