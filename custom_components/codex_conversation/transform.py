"""Helpers to transform Home Assistant chat objects into Codex API payloads."""

from __future__ import annotations

import base64
from datetime import date, datetime
import json
from mimetypes import guess_file_type
from pathlib import Path
from typing import Any

from homeassistant.components.conversation import (
    AssistantContent,
    ChatLog,
    SystemContent,
    ToolResultContent,
    UserContent,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from voluptuous_openapi import convert


def json_default(obj: object) -> str:
    """Fallback serializer for types json.dumps cannot handle natively."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return str(obj)


def format_tool(tool: llm.Tool) -> dict[str, Any]:
    """Format an HA LLM tool as a Responses API function definition."""
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description or "",
        "parameters": convert(tool.parameters),
        "strict": False,
    }


def extract_instructions(chat_log: ChatLog) -> str:
    """Return the system instructions from the chat log."""
    for content in chat_log.content:
        if isinstance(content, SystemContent):
            return content.content
    return ""


def build_input_items(chat_log: ChatLog) -> list[dict[str, Any]]:
    """Build input items in Responses API format from a chat log."""
    items: list[dict[str, Any]] = []

    for content in chat_log.content:
        if isinstance(content, SystemContent):
            continue
        if isinstance(content, UserContent):
            items.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": content.content}],
                }
            )
            continue
        if isinstance(content, AssistantContent):
            if content.tool_calls:
                for tool_call in content.tool_calls:
                    items.append(
                        {
                            "type": "function_call",
                            "name": tool_call.tool_name,
                            "arguments": json.dumps(tool_call.tool_args),
                            "call_id": tool_call.id,
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
            continue
        if isinstance(content, ToolResultContent):
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": content.tool_call_id,
                    "output": json.dumps(content.tool_result, default=json_default),
                }
            )

    return items


async def async_prepare_files_for_prompt(
    hass: HomeAssistant, files: list[tuple[Path, str | None]]
) -> list[dict[str, Any]]:
    """Convert user attachments into Responses API input items."""

    def append_files_to_content() -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []

        for file_path, mime_type in files:
            if not file_path.exists():
                raise HomeAssistantError(f"`{file_path}` does not exist")

            if mime_type is None:
                mime_type = guess_file_type(file_path)[0]

            if not mime_type or not mime_type.startswith(("image/", "application/pdf")):
                raise HomeAssistantError(
                    "Only images and PDF are supported by the Codex API, "
                    f"`{file_path}` is not an image file or PDF"
                )

            base64_file = base64.b64encode(file_path.read_bytes()).decode("utf-8")
            if mime_type.startswith("image/"):
                content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{base64_file}",
                        "detail": "auto",
                    }
                )
            elif mime_type.startswith("application/pdf"):
                content.append(
                    {
                        "type": "input_file",
                        "filename": str(file_path),
                        "file_data": f"data:{mime_type};base64,{base64_file}",
                    }
                )

        return content

    return await hass.async_add_executor_job(append_files_to_content)
