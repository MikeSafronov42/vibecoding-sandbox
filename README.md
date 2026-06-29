# AI Coding Agent Sandbox

A sandboxed execution environment for evaluating AI coding agents under security constraints. Agent-generated commands are routed through Docker isolation and screened by a violation detector before execution.

## Screenshots

| Agent Chat | Dashboard Overview | Live Sandbox |
|---|---|---|
| ![Chat](docs/images/streamlit-chat.png) | ![Dashboard](docs/images/streamlit-dashboard.png) | ![Live](docs/images/streamlit-live.png) |

---

## Setup

### Prerequisites

- Python 3.12+
- Docker
- Ollama (for local models) — optional if using Anthropic or OpenAI

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Build the Docker sandbox image

```bash
docker build -t aisandbox:v1 .docker/
chmod +x scripts/*.sh
```

### 3. (Optional) Build the OpenCode image

Required only if you use the **OpenCode (Sandboxed)** agent backend.

```bash
docker build -t aisandbox-opencode:v1 -f .docker/Dockerfile.opencode .docker/
```

### 4. (Optional) Start a local Ollama model

```bash
ollama pull qwen2.5-coder:7b
```

Any model in `src/config.py → PROVIDER_MODELS["ollama"]` works. Anthropic and OpenAI require an API key entered in the sidebar at runtime.

### 5. Launch the dashboard

```bash
streamlit run demo_app.py
```

Open [http://localhost:8501](http://localhost:8501).

---

## Run tests

```bash
python tests/test_integration.py
# or with pytest
pytest tests/
```

To run the sandbox smoke test:

```bash
./scripts/smoke_test.sh
```

---

## Project layout

```
src/
  config.py          # Shared constants (paths, models, system prompt)
  sandbox.py         # Python wrappers for sandbox utilities
  agents/
    native.py        # Vibeguard tag-based agent backend
    opencode.py      # OpenCode agent backend
  ui/
    styles.py        # Dashboard CSS
    sidebar.py       # Sidebar widget + SidebarConfig dataclass
    tabs.py          # Tab render functions
.docker/
  Dockerfile         # Base sandbox image
  Dockerfile.opencode
scripts/
  run.sh             # Standard Docker (runc) wrapper
  run_gvisor.sh      # gVisor (runsc) wrapper
  run_nsjail.sh      # nsjail wrapper
  run_opencode.sh    # OpenCode container wrapper
  smoke_test.sh      # Sanity check for the sandbox image
sandbox/
  detect.py          # Boundary-violation detector (reads stdin, writes logs/)
tests/
  test_integration.py
tasks/               # Task scenarios (safe/ and attacks/)
workspace/           # Agent-writable code directory (mounted in container)
output/              # Agent output directory (mounted in container)
logs/                # violations.jsonl — structured violation log
docs/                # Observations and screenshots
demo_app.py          # Streamlit entry point
```

## Supported providers

| Provider | Key required | Notes |
|---|---|---|
| Ollama (local) | No | Pull model via `ollama pull <name>` |
| Anthropic Claude | Yes | Enter key in sidebar at runtime |
| OpenAI GPT | Yes | Enter key in sidebar at runtime |
