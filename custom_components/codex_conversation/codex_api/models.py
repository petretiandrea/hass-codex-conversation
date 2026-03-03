"""
Typed event models for the Codex Responses API SSE stream.

Mirrors the ``ResponseEvent`` enum from codex-api/src/sse/responses.rs.
Each dataclass corresponds to one SSE event type emitted by the server.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union


@dataclass
class ResponseCreated:
    """Response object has been created; stream is starting."""
    response_id: str


@dataclass
class OutputItemAdded:
    """A new output item has been added to the response."""
    item: dict[str, Any]


@dataclass
class OutputTextDelta:
    """Incremental text chunk from the model — the main streaming payload."""
    delta: str
    content_index: int = 0


@dataclass
class ReasoningContentDelta:
    """Incremental encrypted reasoning content chunk."""
    delta: str


@dataclass
class ReasoningSummaryDelta:
    """Incremental reasoning-summary text chunk (human-readable chain-of-thought)."""
    delta: str
    summary_index: int = 0


@dataclass
class OutputItemDone:
    """An output item has finished streaming."""
    item: dict[str, Any]


@dataclass
class ResponseCompleted:
    """The full response has completed successfully."""
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class RateLimits:
    """Rate-limit metadata received from the server."""
    data: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FunctionCallAdded:
    """A function-call output item has been added to the response."""
    call_id: str
    name: str
    item_id: str


@dataclass
class FunctionCallArgumentsDelta:
    """Incremental chunk of function-call arguments JSON."""
    delta: str
    item_id: str


@dataclass
class FunctionCallArgumentsDone:
    """Function-call arguments streaming completed; ``arguments`` is the full JSON string."""
    arguments: str
    item_id: str


# Convenience union — use with isinstance() checks
ResponseEvent = Union[
    ResponseCreated,
    OutputItemAdded,
    OutputTextDelta,
    ReasoningContentDelta,
    ReasoningSummaryDelta,
    OutputItemDone,
    ResponseCompleted,
    RateLimits,
    FunctionCallAdded,
    FunctionCallArgumentsDelta,
    FunctionCallArgumentsDone,
]
