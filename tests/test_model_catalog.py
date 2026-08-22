"""Tests for account-scoped Codex model discovery."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.codex_conversation.model_catalog import (
    MODEL_CATALOG_CLIENT_VERSION,
    MODEL_CATALOG_ENDPOINT,
    ModelCatalogError,
    async_fetch_model_catalog,
    parse_model_catalog,
)


def test_parse_model_catalog_returns_picker_visible_models() -> None:
    """Only unique picker-visible models should become selector options."""
    payload = {
        "models": [
            {
                "slug": "gpt-new",
                "display_name": "GPT New",
                "visibility": "list",
            },
            {
                "slug": "gpt-hidden",
                "display_name": "Hidden",
                "visibility": "hide",
            },
            {"slug": "gpt-fallback-label", "visibility": "list"},
            {
                "slug": "gpt-new",
                "display_name": "Duplicate",
                "visibility": "list",
            },
            {"display_name": "Missing slug", "visibility": "list"},
        ]
    }

    assert parse_model_catalog(payload) == [
        {"value": "gpt-new", "label": "GPT New"},
        {"value": "gpt-fallback-label", "label": "gpt-fallback-label"},
    ]


@pytest.mark.parametrize(
    "payload",
    [None, {}, {"models": {}}, {"models": []}, {"models": [{"visibility": "hide"}]}],
)
def test_parse_model_catalog_rejects_unusable_responses(payload) -> None:
    """Malformed or empty catalogs should produce a recoverable flow error."""
    with pytest.raises(ModelCatalogError):
        parse_model_catalog(payload)


async def test_fetch_model_catalog_uses_account_credentials() -> None:
    """Discovery should call the Codex endpoint with the authenticated account."""
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = AsyncMock(
        return_value={
            "models": [
                {
                    "slug": "gpt-account-model",
                    "display_name": "Account Model",
                    "visibility": "list",
                }
            ]
        }
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=response)

    result = await async_fetch_model_catalog(
        session,
        access_token="access-token",
        account_id="account-id",
    )

    assert result == [{"value": "gpt-account-model", "label": "Account Model"}]
    session.get.assert_awaited_once_with(
        MODEL_CATALOG_ENDPOINT,
        params={"client_version": MODEL_CATALOG_CLIENT_VERSION},
        headers={
            "Authorization": "Bearer access-token",
            "Accept": "application/json",
            "User-Agent": (f"hass-codex-conversation/{MODEL_CATALOG_CLIENT_VERSION}"),
            "openai-beta": "responses=experimental",
            "openai-originator": "codex_cli_rs",
            "originator": "codex_cli_rs",
            "ChatGPT-Account-Id": "account-id",
        },
    )
    response.raise_for_status.assert_called_once_with()
