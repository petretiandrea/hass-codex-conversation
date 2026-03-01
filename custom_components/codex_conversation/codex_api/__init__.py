"""
codex_api — Python client for the OpenAI Codex Responses API.

Package structure (mirrors the Rust codex-rs crate layout):

    errors.py    — exception hierarchy        (≈ codex-api/src/error.rs)
    models.py    — typed SSE event dataclasses (≈ codex-api/src/sse/responses.rs)
    requests.py  — CodexRequest               (≈ codex-api/src/endpoint/responses.rs)
    sse.py       — SSE parsing + iteration    (≈ codex-client + codex-api SSE layer)
    client.py    — CodexClient                (≈ codex-api ResponsesClient)

All public symbols are re-exported here so that callers can simply write::

    from .codex_api import CodexClient, CodexRequest, OutputTextDelta, ...
"""
from __future__ import annotations

from .auth import (
    AbstractAuth,
    CodexAuth,
    CodexDeviceFlow,
    DeviceCodeInfo,
    OAuthToken,
)
from .client import CODEX_ENDPOINT, CodexClient
from .errors import (
    CodexApiError,
    CodexContextWindowExceeded,
    CodexError,
    CodexQuotaExceeded,
    CodexRateLimited,
    CodexServerOverloaded,
    CodexStreamError,
    CodexUsageNotIncluded,
)
from .models import (
    OutputItemAdded,
    OutputItemDone,
    OutputTextDelta,
    RateLimits,
    ReasoningContentDelta,
    ReasoningSummaryDelta,
    ResponseCompleted,
    ResponseCreated,
    ResponseEvent,
)
from .requests import CodexRequest

__all__ = [
    # auth
    "AbstractAuth",
    "CodexAuth",
    "CodexDeviceFlow",
    "DeviceCodeInfo",
    "OAuthToken",
    # client
    "CODEX_ENDPOINT",
    "CodexClient",
    # errors
    "CodexError",
    "CodexApiError",
    "CodexContextWindowExceeded",
    "CodexQuotaExceeded",
    "CodexUsageNotIncluded",
    "CodexRateLimited",
    "CodexServerOverloaded",
    "CodexStreamError",
    # models
    "ResponseCreated",
    "OutputItemAdded",
    "OutputTextDelta",
    "ReasoningContentDelta",
    "ReasoningSummaryDelta",
    "OutputItemDone",
    "ResponseCompleted",
    "RateLimits",
    "ResponseEvent",
    # requests
    "CodexRequest",
]
