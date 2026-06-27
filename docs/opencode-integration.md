# OpenCode + Cloud Providers — Integration Guide

This document explains how OpenCode (and cloud LLM providers) were integrated into
the vibecoding-sandbox project, what every added file does, and how to run the experiment.

---

## 1. Why This Integration?

### The problem with OpenCode natively

OpenCode (`npm install -g opencode-ai`) is a terminal AI coding agent that supports
multiple providers — Anthropic Claude, OpenAI GPT, Ollama, and others. When you ask it
to write a Python script and run it, it executes the shell command **directly on your
host machine**. There is no built-in sandbox.

### What this project adds

The vibecoding-sandbox already isolates code execution inside Docker containers with:
- `--cap-drop=ALL` (no Linux capabilities)
- `--security-opt=no-new-privileges` (no privilege escalation)
- `--network=none` by default (no outbound network)
- Non-root user matching host UID/GID
- Volume-limited workspace (`/workspace` and `/output` only)

This integration runs the **entire OpenCode process** inside one of those containers.
Every file write, every shell command, every Python script that OpenCode executes is
automatically sandboxed — without needing to patch OpenCode itself.

---

## 2. Architecture Overview

```
User (Streamlit UI)
        │
        ▼
demo_app.py — agent type selector in sidebar
        │
        ├── agent_type == "Vibeguard Native"
        │       │
        │       ▼
        │   agent_chat.py  ──── provider routing ────►  Ollama  (localhost:11434)
        │       │                                    ►  Anthropic API
        │       │                                    ►  OpenAI API
        │       ▼
        │   sandbox/run.sh  (or gvisor / nsjail)
        │       └── docker run aisandbox:v1  (existing image)
        │
        └── agent_type == "OpenCode (Sandboxed)"
                │
                ▼
            opencode_agent.py
                │
                ▼
            sandbox/run_opencode.sh
                └── docker run aisandbox-opencode:v1
                        ├── opencode run --format json "<prompt>"
                        ├── opencode calls LLM API  (outbound network allowed)
                        ├── opencode writes files   → /workspace  (host volume)
                        ├── opencode runs shell     → contained in container
                        └── output files            → /output  (host volume)
```

Cloud LLM API keys flow as environment variables into the container; they are **never
written to disk**.

---

## 3. New and Changed Files

### `sandbox/Dockerfile.opencode`  *(new)*

Builds `aisandbox-opencode:v1`. Layered on top of `python:3.12-slim`:

| Layer | Purpose |
|---|---|
| Node.js 22 LTS | Required by the `opencode-ai` npm package |
| `npm install -g opencode-ai` | Installs the OpenCode CLI |
| Python packages | Needed for any Python code OpenCode writes/runs |
| Non-root user `agent` (UID/GID 1000) | Matches host UID, prevents privilege issues on volume mounts |

### `sandbox/run_opencode.sh`  *(new)*

Shell wrapper that `docker run`s the opencode image with hardening flags.

Key flags:
- `--add-host=host.docker.internal:host-gateway` — allows OpenCode to reach the LLM API
  (Anthropic/OpenAI over HTTPS, or Ollama on the host)
- `--cap-drop=ALL` — all Linux capabilities dropped
- `--security-opt=no-new-privileges` — no privilege escalation via setuid/setgid
- `--memory=4g --cpus=2` — resource limits
- `-v workspace:/workspace -v output:/output` — only these two host directories are visible

The provider-specific `opencode.json` is assembled inline and injected via the
`OPENCODE_CONFIG_CONTENT` environment variable (OpenCode reads this natively).

### `opencode_agent.py`  *(new)*

Python module called from `demo_app.py`.

```
run_opencode(prompt, provider, model, api_key, ollama_model, timeout)
    └── sets OPENCODE_PROVIDER, OPENCODE_MODEL, API key env vars
    └── subprocess.run([run_opencode.sh, prompt])
    └── parses --format json event stream
    └── returns { ok, returncode, summary, text_parts, tool_calls, events, stderr }
```

Event types parsed from OpenCode's JSON stream:
- `message.part` with `part.type == "text"` → assistant text
- `message.part` with `part.type == "tool-invocation"` → recorded tool calls
- Fallback: plain-text lines passed through as output

### `agent_chat.py`  *(modified)*

Added `provider` and `api_key` parameters to `get_model_response()` and
`handle_assistant_turn()`. Both default to `"ollama"` / `""` so existing code and tests
are fully backward-compatible.

New internal functions:

| Function | Backend |
|---|---|
| `_get_response_ollama()` | Original Ollama path (unchanged) |
| `_get_response_anthropic()` | Uses `anthropic` Python SDK |
| `_get_response_openai()` | HTTP call to `api.openai.com/v1/chat/completions` |

`PROVIDER_MODELS` dict is exported so `demo_app.py` can populate the model dropdown
dynamically.

### `demo_app.py`  *(modified)*

Sidebar additions:
- **Agent Backend** — "Vibeguard Native" or "OpenCode (Sandboxed)"
- **AI Provider** — Ollama (Local) / Anthropic Claude / OpenAI GPT
- **Model** — dynamically populated from `PROVIDER_MODELS`
- **API Key** — password field, shown only for cloud providers
- Build-status check for `aisandbox-opencode:v1`

Chat tab now dispatches to the correct backend and renders OpenCode results with
tool-call expanders.

### `requirements.txt`  *(modified)*

Added `openai>=1.30.0`. `anthropic` was already present.

---

## 4. Setup Instructions

### Step 1 — Build the standard sandbox image (if not already done)

```bash
cd vibecoding-sandbox
docker build -t aisandbox:v1 sandbox/
```

### Step 2 — Build the OpenCode sandbox image

```bash
docker build -t aisandbox-opencode:v1 -f sandbox/Dockerfile.opencode sandbox/
```

This takes 2–4 minutes on first build (downloads Node.js + npm installs opencode-ai).

### Step 3 — Install Python dependencies (project venv)

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Step 4 — Start the dashboard

```bash
# Optional: start Ollama if you want local models
ollama run qwen2.5-coder:7b

# Launch Streamlit
streamlit run demo_app.py
```

---

## 5. Selecting a Provider

### Ollama (local, no API key)

1. In the sidebar, set **AI Provider** to *Ollama (Local)*.
2. Choose the model (must already be pulled with `ollama pull <model>`).
3. Ollama is reached at `http://host.docker.internal:11434` from inside the container.

### Anthropic Claude

1. Set **AI Provider** to *Anthropic Claude*.
2. Paste your `ANTHROPIC_API_KEY` into the API Key field.
3. Choose a Claude model (e.g. `claude-sonnet-4-5`).
4. The key is passed as a container environment variable; never written to disk.

### OpenAI GPT

1. Set **AI Provider** to *OpenAI GPT*.
2. Paste your `OPENAI_API_KEY`.
3. Choose a GPT model (e.g. `gpt-4o`).

---

## 6. Running the OpenCode Experiment

1. Build `aisandbox-opencode:v1` (Step 2 above).
2. In the sidebar select **Agent Backend → OpenCode (Sandboxed)**.
3. Pick a provider and model; enter API key if using a cloud provider.
4. Open the **Chat with agent** tab.
5. Type a task, e.g. *"Write a Python script that generates a Fibonacci sequence and saves
   it to /output/fibonacci.txt"*.
6. OpenCode will write the file and run it — entirely inside the container.
7. The result (summary + any tool calls) is displayed in the chat.
8. Check `output/fibonacci.txt` on the host to confirm the file was written through the
   volume mount.

---

## 7. Security Properties of the OpenCode Container

| Property | How achieved |
|---|---|
| No host filesystem access | Only `/workspace` and `/output` volumes mounted |
| No privilege escalation | `--cap-drop=ALL` + `--security-opt=no-new-privileges` |
| Memory / CPU bounded | `--memory=4g --cpus=2` |
| LLM API calls allowed | `--add-host=host.docker.internal:host-gateway` (no `--network=none`) |
| API key not on disk | Passed as ephemeral env var; container destroyed after run |
| Non-root execution | `USER agent` (UID 1000) |

**Trade-off vs. Vibeguard Native**: the OpenCode container needs outbound network to
reach cloud APIs, so `--network=none` cannot be used. The `sandbox/detect.py` violation
detector is not applied to OpenCode's individual shell calls (OpenCode manages its own
tool loop). The container isolation layer still prevents host access.

---

## 8. About OpenClaw

OpenClaw (`npm install -g openclaw@latest`) is a self-hosted gateway that connects
messaging apps (Telegram, Slack, Discord, WhatsApp, etc.) to AI agents. It is not a
coding agent itself, but it can be used as an **access layer** on top of the sandbox:

```
Telegram / Slack message
        │
        ▼
  OpenClaw gateway  (running on host)
        │
        ▼
  vibecoding-sandbox API  (future: expose opencode_agent.run_opencode via HTTP)
        │
        ▼
  aisandbox-opencode container  (sandboxed execution)
```

A future extension would add a small Flask/FastAPI server that accepts a task prompt
over HTTP, calls `opencode_agent.run_opencode()`, and returns the result. OpenClaw
skills can then POST to that endpoint, giving you a messaging-app front-end to the
sandboxed coding agent.

---

## 9. Limitations and Known Issues

- **Interactive authentication**: OpenCode normally uses `/connect` for browser-based
  OAuth flows. In headless Docker mode only environment-variable API keys work.
  All listed providers (Anthropic, OpenAI, Ollama) support env-var auth.
- **OpenCode config home**: OpenCode writes session state to `~/.config/opencode`.
  The container creates `/home/agent/.config/opencode` for this; it is discarded when
  the container exits.
- **Long-running tasks**: The default timeout is 300 s. Increase `timeout` in
  `opencode_agent.run_opencode()` for complex tasks.
- **Event format**: OpenCode's `--format json` event schema is internal and may change
  across versions. `opencode_agent.py` includes a plain-text fallback for forward
  compatibility.
- **Violation detector**: `sandbox/detect.py` is not applied to individual commands
  inside the OpenCode container. If you need per-command detection, mount the detector
  script and wrap shell execution (advanced).
