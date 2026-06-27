"""
OpenCode agent backend.

Drives the opencode CLI *inside* the Docker sandbox so that all file
operations and shell executions are contained — OpenCode natively has no
sandbox of its own.

Supported providers:
  anthropic  — Claude (requires ANTHROPIC_API_KEY)
  openai     — GPT / o-series (requires OPENAI_API_KEY)
  ollama     — any local Ollama model (no API key)
"""
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List

import requests as _requests

REPO = Path(__file__).resolve().parent
RUN_OPENCODE_SH = REPO / "sandbox" / "run_opencode.sh"

_ANTHROPIC_FALLBACK = [
    "claude-sonnet-4-6",
    "claude-opus-4-8",
    "claude-haiku-4-5-20251001",
]
_OPENAI_FALLBACK = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3-mini"]
_OLLAMA_FALLBACK = ["qwen2.5-coder:7b", "deepseek-coder:6.7b", "gemma4:e4b", "qwen3.5:9b"]


def get_ollama_models(base_url: str = "http://localhost:11434") -> List[str]:
    """Return model names currently pulled in Ollama, falling back to defaults."""
    try:
        r = _requests.get(f"{base_url}/api/tags", timeout=3)
        if r.status_code == 200:
            names = [m["name"] for m in r.json().get("models", [])]
            return names if names else _OLLAMA_FALLBACK
    except Exception:
        pass
    return _OLLAMA_FALLBACK


def get_provider_models() -> Dict[str, List[str]]:
    """Return the model list for every provider, querying Ollama dynamically."""
    return {
        "anthropic": _ANTHROPIC_FALLBACK,
        "openai": _OPENAI_FALLBACK,
        "ollama": get_ollama_models(),
    }


# Cached copy used by demo_app.py on import — refreshed each Streamlit rerun
PROVIDER_MODELS: Dict[str, List[str]] = get_provider_models()


def image_exists(name: str = "aisandbox-opencode:v1") -> bool:
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", name],
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def run_opencode(
    prompt: str,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
    api_key: str = "",
    ollama_model: str = "qwen2.5-coder:7b",
    timeout: int = 120,
) -> Dict:
    """Run OpenCode in the sandbox and return a structured result dict.

    Returns:
        ok          bool    — True if opencode exited 0
        returncode  int
        summary     str     — assembled assistant text (≤3 000 chars)
        text_parts  list    — individual text segments from the event stream
        tool_calls  list    — tool invocations OpenCode made
        events      list    — raw parsed JSON events (up to 200)
        stderr      str
    """
    env = dict(os.environ)
    env["OPENCODE_PROVIDER"] = provider

    if provider == "ollama":
        env["OPENCODE_MODEL"] = ollama_model
        env["OLLAMA_MODEL"] = ollama_model
    else:
        env["OPENCODE_MODEL"] = model
        if provider == "anthropic" and api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        elif provider == "openai" and api_key:
            env["OPENAI_API_KEY"] = api_key

    try:
        proc = subprocess.run(
            [str(RUN_OPENCODE_SH), prompt],
            env=env,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return _parse_output(proc.stdout, proc.stderr, proc.returncode)
    except subprocess.TimeoutExpired:
        return _error(f"TIMEOUT after {timeout}s")
    except Exception as exc:
        return _error(str(exc))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_output(stdout: str, stderr: str, returncode: int) -> Dict:
    text_parts: List[str] = []
    tool_calls: List[Dict] = []
    events: List[Dict] = []

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
            if len(events) < 200:
                events.append(ev)
            ev_type = ev.get("type", "")
            part = ev.get("part", {})

            # OpenCode 1.x event format: type="text" with part.text
            if ev_type == "text" and isinstance(part, dict):
                t = part.get("text", "")
                if t:
                    text_parts.append(t)

            # Tool-use events: type="tool_input" / "tool_result" or part.type=="tool-invocation"
            elif ev_type in ("tool_input", "tool_call"):
                tool_calls.append(ev)
            elif ev_type == "message.part":
                if part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
                elif part.get("type") == "tool-invocation":
                    tool_calls.append(part.get("toolInvocation", {}))

            # Older / alternative shapes
            elif ev_type in ("assistant", "message"):
                content = ev.get("content", "")
                if isinstance(content, str) and content:
                    text_parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))

        except json.JSONDecodeError:
            if line and not line.startswith("==="):
                text_parts.append(line)

    assembled = " ".join(t for t in text_parts if t.strip())
    summary = (assembled or stdout[:500] or "(no output)").strip()

    return {
        "ok": returncode == 0,
        "returncode": returncode,
        "summary": summary[:3000],
        "text_parts": text_parts,
        "tool_calls": tool_calls,
        "events": events,
        "stderr": stderr[:2000],
    }


def _error(msg: str) -> Dict:
    return {
        "ok": False,
        "returncode": -1,
        "summary": msg,
        "text_parts": [],
        "tool_calls": [],
        "events": [],
        "stderr": msg,
    }
