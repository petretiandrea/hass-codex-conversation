# hass-codex-conversation

A [Home Assistant](https://www.home-assistant.io/) custom integration that brings **OpenAI Codex** models into your smart home as a conversation agent — without an API key or separate billing.

---

## The idea

OpenAI's **Codex CLI** is a developer tool that lets you use powerful reasoning models (`gpt-5.1-codex`, `gpt-5.2-codex`, …) directly from the terminal.
Access to these models is **included in any ChatGPT Plus or Pro subscription** — no OpenAI API key needed, no per-token billing on top of what you already pay.

This integration reverse-engineers the same authenticated endpoint the Codex CLI uses and exposes it as a native Home Assistant conversation agent.
If you already pay for ChatGPT Plus or Pro, you get a state-of-the-art reasoning model in Home Assistant for free.

---

## Features

- **No API key** — authenticates with your existing ChatGPT account via OAuth2 device-code flow
- **Streaming responses** — text appears word by word, same as the ChatGPT web interface
- **Reasoning models** — supports the full `gpt-5.*-codex` family, including models with extended chain-of-thought reasoning
- **Multi-turn conversations** — full conversation history is sent on every turn
- **HA Assist integration** — works as a drop-in conversation agent in the Home Assistant Assist pipeline
- **Automatic token refresh** — OAuth2 tokens are refreshed transparently in the background

---

## Requirements

| Requirement | Details |
|---|---|
| Home Assistant | 2024.11 or newer |
| Subscription | ChatGPT Plus or Pro |

---

## Installation

### HACS (recommended)

1. Open HACS → **Integrations** → menu → **Custom repositories**
2. Add `https://github.com/your-username/hass-codex-conversation` as an **Integration**
3. Search for *OpenAI Codex Conversation* and install it
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/codex_conversation` folder into your HA `config/custom_components/` directory
2. Restart Home Assistant

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for *OpenAI Codex Conversation*
3. A device code and a URL will appear in the HA log (and shortly in the UI):
   ```
   Go to https://auth.openai.com/codex/device and enter code: XXXX-XXXX
   ```
4. Open that URL in your browser, log in with your ChatGPT account, and enter the code
5. Once approved, select your preferred Codex model and finish the setup

---

## Configuration

The following option can be changed after setup via **Settings → Devices & Services → OpenAI Codex Conversation → Configure**:

| Option | Description | Default |
|---|---|---|
| Model | The Codex model to use | `gpt-5.1-codex` |

### Available models

| Model | Notes |
|---|---|
| `gpt-5.1-codex` | Balanced speed and reasoning |
| `gpt-5.2-codex` | More capable reasoning |
| `gpt-5.3-codex` | Most capable |
| `gpt-5.1-codex-mini` | Faster and lighter |

---

## How it works

```
Home Assistant Assist
        │
        ▼
CodexConversationEntity
        │  builds CodexRequest from ChatLog history
        ▼
CodexClient  ──(AbstractAuth)──▶  CodexHAAuth
        │                               │
        │                    asks OAuth2Session for a
        │                    valid token (refresh if needed)
        ▼
chatgpt.com/backend-api/codex/responses
        │
        │  Server-Sent Events stream
        ▼
SSE parser  ──▶  OutputTextDelta events
        │
        ▼
ChatLog delta stream  ──▶  HA Assist UI
```

The integration is built as a clean layered Python library inside `custom_components/codex_conversation/codex_api/`:

| Module | Responsibility |
|---|---|
| `auth.py` | `AbstractAuth` ABC, JWT helpers, raw OAuth2 HTTP calls |
| `client.py` | `CodexClient` — streams requests, depends only on `AbstractAuth` |
| `models.py` | Typed SSE event dataclasses |
| `requests.py` | `CodexRequest` builder |
| `sse.py` | SSE frame parsing |
| `errors.py` | Exception hierarchy |

HA-specific code lives outside the library:

| File | Responsibility |
|---|---|
| `oauth.py` | `CodexHAAuth` + `CodexOAuth2Implementation` |
| `conversation.py` | `ConversationEntity` — bridges ChatLog ↔ CodexClient |
| `config_flow.py` | Device-code OAuth UI flow |

---

## Disclaimer

This integration uses an **unofficial, internal API** (`chatgpt.com/backend-api/codex/responses`) that is not publicly documented by OpenAI.
It may break if OpenAI changes the API without notice.
Use at your own risk. This project is not affiliated with or endorsed by OpenAI.

---

## License

MIT
