"""Constants for the OpenAI Codex Conversation integration."""

from homeassistant.const import CONF_LLM_HASS_API  # noqa: F401
from homeassistant.helpers import llm

DOMAIN = "codex_conversation"

MODELS = [
    "gpt-5.1-codex",
    "gpt-5.2-codex",
    "gpt-5.3-codex",
    "gpt-5.1-codex-mini",
]

# Options keys
CONF_MODEL = "model"
CONF_RECOMMENDED = "recommended"
CONF_PROMPT = "prompt"
CONF_REASONING_EFFORT = "reasoning_effort"
CONF_REASONING_SUMMARY = "reasoning_summary"
CONF_TEXT_VERBOSITY = "text_verbosity"

# Defaults
DEFAULT_MODEL = "gpt-5.1-codex"
RECOMMENDED_REASONING_EFFORT = "medium"
RECOMMENDED_REASONING_SUMMARY = "auto"
RECOMMENDED_TEXT_VERBOSITY = "medium"

RECOMMENDED_CONVERSATION_OPTIONS: dict = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
    CONF_MODEL: DEFAULT_MODEL,
    CONF_REASONING_EFFORT: RECOMMENDED_REASONING_EFFORT,
    CONF_REASONING_SUMMARY: RECOMMENDED_REASONING_SUMMARY,
    CONF_TEXT_VERBOSITY: RECOMMENDED_TEXT_VERBOSITY,
}
