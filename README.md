# Yolo: Personal Self-Improving AI Assistant

Yolo is a persistent, tool-using personal AI assistant designed to run 24/7 on a low-cost server.

It supports:
- Persistent cross-session memory and profile modeling
- Self-improving behaviors (experience learning + skill authoring/optimization)
- Pluggable LLM providers (OpenAI, OpenRouter, Anthropic, OpenAI-compatible endpoints)
- Multi-gateway access (CLI, Telegram, Discord)
- Background missions and recurring schedules (including daily tasks)
- Optional webhook mode + lightweight health endpoint for production observability

## Architecture

- `agent.py`: Core planning/acting loop with tool calls and HITL confirmation support
- `llm_router.py`: Provider-agnostic model routing
- `session.py`: Session lifecycle + persistence hooks
- `tools/*`: Capabilities (files, web, browser, memory, skills, scheduling, artifacts)
- Browser automation is powered by Camoufox (anti-detect Firefox wrapper)
- `bot.py`: Telegram gateway + uploads (documents, photos OCR, audio/voice transcript)
- `discord_gateway.py`: Discord chat gateway
- `cli.py`: Local terminal REPL gateway
- `server.py`: Unified process entrypoint for Telegram/Discord/all

## Quick Start

1) Create environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Browser runtime setup (Camoufox):

For standard/stable releases, you can use `camoufox`.
To make full use of per-context fingerprints and hardware spoofing, use `cloverlabs-camoufox`.
This project is configured for `cloverlabs-camoufox`.

Use a dedicated virtual environment to avoid conflicts between Camoufox package variants.

```bash
pip install -r requirements.txt
python -m camoufox fetch
```

On fresh Linux machines you may also need:

```bash
sudo apt install -y libgtk-3-0 libx11-xcb1 libasound2
```

2) Create `.env` from the template below and set your keys.

3) Run a gateway:

- CLI:

```bash
python cli.py --user-id 1
```

- Telegram:

```bash
python bot.py
```

- Discord:

```bash
python server.py --mode discord
```

- All gateways in one process:

```bash
python server.py --mode all
```

## LLM Provider Switching

Set `LLM_PROVIDER` and corresponding keys. You can switch providers without code changes.

Supported values for `LLM_PROVIDER`:
- `openai`
- `openrouter`
- `anthropic`
- `compatible` (local proxy or OpenAI-compatible API)
- `auto` (default; chooses based on available keys)

Examples:

### OpenAI

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=...
MODEL_NAME=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

### OpenRouter

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=...
MODEL_NAME=openai/gpt-4o-mini
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=https://your-app.example
OPENROUTER_X_TITLE=Yolo Assistant
```

### Anthropic

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
MODEL_NAME=claude-3-5-sonnet-20241022
```

### Local/OpenAI-Compatible Proxy

```env
LLM_PROVIDER=compatible
LLM_API_KEY=not-required-or-your-key
LLM_BASE_URL=http://localhost:4141/v1
MODEL_NAME=your-local-model-name
```

## Telegram + Discord Configuration

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_IDS=123456789

DISCORD_BOT_TOKEN=...
DISCORD_ALLOWED_USER_IDS=123456789012345678
```

## Telegram Webhook Mode (Optional)

Default is polling. For production, webhook mode is recommended behind a reverse proxy.

```env
TELEGRAM_USE_WEBHOOK=true
TELEGRAM_WEBHOOK_URL=https://your-domain.example
TELEGRAM_WEBHOOK_PATH=telegram
TELEGRAM_WEBHOOK_PORT=8080
TELEGRAM_WEBHOOK_LISTEN=0.0.0.0
TELEGRAM_WEBHOOK_SECRET_TOKEN=your-random-secret
```

When webhook mode is enabled, `bot.py` will call `run_webhook`.

## Health Endpoint

When running `server.py`, a lightweight health endpoint is started by default.

```env
ENABLE_HEALTH_SERVER=true
HEALTH_SERVER_HOST=0.0.0.0
HEALTH_SERVER_PORT=8787
```

Endpoints:
- `/health`
- `/status`
- `/metrics`

Example:

```bash
curl http://127.0.0.1:8787/health
```

The payload includes active cron counts, running background tasks, pending notifications, and the latest audit log entry.

## Scheduling / Automation

You can schedule tasks with tools:
- `schedule_task(task_description, interval_minutes)`
- `schedule_daily_task(task_description)`
- `get_scheduled_tasks()`
- `cancel_scheduled_task(cron_id)`

Example prompt:
- "Schedule a daily task to send me a morning market summary"

## Persistent Learning Features

- Long-term memory: `memory_add`, `memory_list`, `memory_wipe`
- Experience capture: `learn_experience`, `list_experiences`
- Identity profile: `read_user_identity`, `update_user_identity`
- Skill creation/evolution: `develop_new_skill`, `optimize_skill`, `list_skills`, `read_skill`

## Cloud Deployment (Low-Cost VPS)

Recommended: 1 vCPU / 1-2 GB RAM Ubuntu VM.

Install and run with systemd:

1) Put project at `/opt/yolo`
2) Create `/etc/systemd/system/yolo.service`:

```ini
[Unit]
Description=Yolo Personal AI Assistant
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/yolo
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/yolo/.venv/bin/python server.py --mode all
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

3) Enable service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable yolo
sudo systemctl start yolo
sudo systemctl status yolo
```

Health service (optional separate unit):

```ini
[Unit]
Description=Yolo Health Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/yolo
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/yolo/.venv/bin/python health_server.py --host 0.0.0.0 --port 8787
Restart=always

[Install]
WantedBy=multi-user.target
```

## Notes

- Uploads from Telegram are stored in `artifacts/uploads`.
- Photos can be OCR-processed and audio/voice can be transcribed when media AI pipeline is enabled.
- Use `/mode yolo` in Telegram for autonomous execution, or safe mode for confirmations.
- Browser tools use Camoufox. Optional tuning envs:
  - `CAMOUFOX_HEADLESS=true` (or `virtual` on Linux)
  - `CAMOUFOX_HUMANIZE=true`
  - `CAMOUFOX_BLOCK_IMAGES=false`
  - `CAMOUFOX_OS=windows,macos,linux`
