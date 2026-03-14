# hass-codex-conversation

A [Home Assistant](https://www.home-assistant.io/) custom integration that brings **OpenAI Codex** models into your smart home as a conversation agent, without an API key or separate billing.

## The Idea

OpenAI's **Codex CLI** is a developer tool that lets you use powerful reasoning models such as `gpt-5.1-codex` and `gpt-5.3-codex` directly from the terminal.
Access to these models is included in a ChatGPT Plus or Pro subscription, so there is no separate OpenAI API key and no per-token billing on top of that subscription.

This integration reuses the same authenticated Codex backend flow and exposes it as a native Home Assistant conversation agent.

## Features

- No API key required, authentication happens with your existing ChatGPT account through OAuth2 device flow.
- Streaming responses, so text appears progressively in the Home Assistant conversation UI.
- Support for the `gpt-5.*-codex` model family.
- Multi-turn conversations with full chat history.
- Home Assistant Assist integration.
- Automatic token refresh.
- Initial `ai_task` support for `generate_data`.

## Requirements

| Requirement | Details |
| --- | --- |
| Home Assistant | 2026.2.0 or newer |
| Subscription | ChatGPT Plus or Pro |

## Installation

### HACS

1. Open HACS and go to **Integrations**.
2. Open the menu and choose **Custom repositories**.
3. Add your repository URL as an **Integration** repository.
4. Search for **OpenAI Codex Conversation** and install it.
5. Restart Home Assistant.

### Manual

1. Copy `custom_components/codex_conversation` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Setup

1. Go to **Settings -> Devices & Services -> Add Integration**.
2. Search for **OpenAI Codex Conversation**.
3. A device code and URL will be shown during setup, for example:

   ```text
   Go to https://auth.openai.com/codex/device and enter code: XXXX-XXXX
   ```

4. Open the URL in your browser, log in with your ChatGPT account, and enter the code.
5. Approve the login and complete the integration setup.

## Configuration

After setup, you can change options from **Settings -> Devices & Services -> OpenAI Codex Conversation -> Configure**.

| Option | Description | Default |
| --- | --- | --- |
| Model | Codex model used for the conversation agent | `gpt-5.1-codex` |

### Available Models

| Model | Notes |
| --- | --- |
| `gpt-5.1-codex` | Balanced speed and reasoning |
| `gpt-5.2-codex` | More capable reasoning |
| `gpt-5.3-codex` | Most capable |
| `gpt-5.1-codex-mini` | Faster and lighter |

## How It Works

```text
Home Assistant Assist
        |
        v
CodexConversationEntity
        |  builds CodexRequest from ChatLog history
        v
CodexClient  --(AbstractAuth)-->  CodexHAAuth
        |                               |
        |                    asks OAuth2Session for a
        |                    valid token (refresh if needed)
        v
chatgpt.com/backend-api/codex/responses
        |
        |  Server-Sent Events stream
        v
SSE parser  -->  OutputTextDelta events
        |
        v
ChatLog delta stream  -->  HA Assist UI
```

The integration code is layered under `custom_components/codex_conversation/codex_api/`:

| Module | Responsibility |
| --- | --- |
| `auth` | `AbstractAuth`, JWT helpers, raw OAuth2 HTTP calls |
| `client.py` | `CodexClient`, streams requests using authenticated transport |
| `models.py` | Typed SSE event dataclasses |
| `requests.py` | `CodexRequest` builder |
| `sse.py` | SSE frame parsing |
| `errors.py` | Exception hierarchy |

Home Assistant-specific glue lives outside that client package:

| File | Responsibility |
| --- | --- |
| `oauth.py` | `CodexHAAuth` and OAuth2 implementation |
| `conversation.py` | `ConversationEntity` bridge between `ChatLog` and Codex |
| `ai_task.py` | AI Task entity support |
| `config_flow.py` | Device-code OAuth flow |

## Development

The repository setup has been aligned with a more modern HACS integration blueprint style.

### Local Bootstrap

```bash
bash script/setup/bootstrap
```

### Run Home Assistant

```bash
bash script/develop
```

This starts Home Assistant using `config/configuration.yaml`.

### Useful Scripts

- `script/lint` formats and lints the repository with Ruff.
- `script/lint-check` runs lint checks without modifying files.
- `script/test` runs the test suite.
- `script/check` runs a quick validation pass.

### Repository Tooling

- GitHub Actions workflows for `Tests`, `Lint`, and `Validate`.
- `Validate` includes both `hassfest` and HACS validation.
- Pre-commit now uses Ruff, codespell, JSON/YAML checks, and Prettier for repository files.
- Dependabot is configured for GitHub Actions and Python dependencies.

## Disclaimer

This integration uses an unofficial internal endpoint, `chatgpt.com/backend-api/codex/responses`, which is not publicly documented by OpenAI.
It may break if OpenAI changes that backend without notice.
This project is not affiliated with or endorsed by OpenAI.

## License

MIT
