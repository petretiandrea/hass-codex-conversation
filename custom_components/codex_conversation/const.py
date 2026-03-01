"""Constants for the OpenAI Codex Conversation integration."""

DOMAIN = "codex_conversation"

# OAuth — Codex Device Code Auth
CLIENT_ID        = "app_EMoamEEZ73f0CkXaXp7hrann"
_ISSUER          = "https://auth.openai.com"
_AUTH_BASE       = f"{_ISSUER}/api/accounts"
USERCODE_URL     = f"{_AUTH_BASE}/deviceauth/usercode"   # POST → device_auth_id, user_code
DEVICE_POLL_URL  = f"{_AUTH_BASE}/deviceauth/token"      # POST → authorization_code, code_verifier
TOKEN_URL        = f"{_ISSUER}/oauth/token"              # final exchange + refresh
DEVICE_REDIRECT  = f"{_ISSUER}/deviceauth/callback"      # redirect_uri for code exchange
VERIFICATION_URL = f"{_ISSUER}/codex/device"             # URL shown to the user

# API
CODEX_ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"

MODELS = [
    "gpt-5.1-codex",
    "gpt-5.2-codex",
    "gpt-5.3-codex",
    "gpt-5.1-codex-mini",
]

# Config entry keys (stored encrypted by HA)
CONF_ACCESS_TOKEN  = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_ACCOUNT_ID    = "account_id"
CONF_EXPIRES_AT    = "expires_at"

# Options keys
CONF_MODEL    = "model"

# Defaults
DEFAULT_MODEL = "gpt-5.1-codex"
