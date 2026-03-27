"""Unit tests for HA <-> Codex payload transformations."""

from __future__ import annotations

from pathlib import Path

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.codex_conversation.transform import (
    async_prepare_files_for_prompt,
)


class _FakeHass:
    """Minimal HomeAssistant-like object for executor job calls."""

    async def async_add_executor_job(self, target, *args):
        return target(*args)


@pytest.mark.parametrize(
    ("filename", "mime_type", "expected_type"),
    [
        ("image.png", None, "input_image"),
        ("document.pdf", None, "input_file"),
    ],
)
async def test_async_prepare_files_for_prompt_supported_types(
    tmp_path: Path, filename: str, mime_type: str | None, expected_type: str
) -> None:
    file_path = tmp_path / filename
    file_path.write_bytes(b"test-bytes")

    result = await async_prepare_files_for_prompt(
        _FakeHass(),
        [(file_path, mime_type)],
    )

    assert len(result) == 1
    assert result[0]["type"] == expected_type


async def test_async_prepare_files_for_prompt_rejects_unsupported_file_type(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("hello")

    with pytest.raises(HomeAssistantError, match="Only images and PDF"):
        await async_prepare_files_for_prompt(
            _FakeHass(),
            [(file_path, None)],
        )


async def test_async_prepare_files_for_prompt_missing_file() -> None:
    with pytest.raises(HomeAssistantError, match="does not exist"):
        await async_prepare_files_for_prompt(
            _FakeHass(),
            [(Path("/tmp/definitely-missing-file.png"), "image/png")],
        )
