"""Vibeguard native agent backend.

Dispatches to an LLM (Ollama, Anthropic, or OpenAI), parses the XML-style
tool tags from the response, routes execution through the sandbox, and
enforces a blocking policy on high-severity boundary violations.
"""
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import requests

from src.config import (
    DETECT_PY,
    LOG_FILE,
    OLLAMA_URL,
    OUTPUT,
    REPO,
    SYSTEM_PROMPT,
    WORKSPACE,
)

_TAG_RE = re.compile(r"<(run|write|read|done)([^>]*)>(.*?)(?:</\1>|/>)", re.DOTALL)
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')

_SEVERITY_ORDER: dict[str, int] = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


# ---------------------------------------------------------------------------
# Tag parsing
# ---------------------------------------------------------------------------


def parse_tags(text: str) -> list[dict[str, Any]]:
    """Extract all XML-style tool tags from an LLM response.

    Returns a list of dicts with keys: tag, attrs, body.
    """
    results: list[dict[str, Any]] = []
    for m in _TAG_RE.finditer(text):
        results.append({
            "tag": m.group(1),
            "attrs": dict(_ATTR_RE.findall(m.group(2))),
            "body": (m.group(3) or "").strip(),
        })
    return results


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


def write_workspace_file(rel_path: str, content: str) -> dict[str, Any]:
    """Write content to a path inside the workspace directory.

    rel_path must start with 'workspace/'.
    """
    if not rel_path.startswith("workspace/"):
        return {"ok": False, "error": f"Path must start with 'workspace/', got: {rel_path}"}
    target = (REPO / rel_path).resolve()
    if not str(target).startswith(str(WORKSPACE.resolve())):
        return {"ok": False, "error": "Path escapes workspace directory"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {"ok": True, "path": rel_path, "bytes": len(content)}


def read_workspace_file(rel_path: str) -> dict[str, Any]:
    """Read a file from workspace/ or output/. Content is capped at 5 000 chars."""
    target = (REPO / rel_path).resolve()
    in_workspace = str(target).startswith(str(WORKSPACE.resolve()))
    in_output = str(target).startswith(str(OUTPUT.resolve()))
    if not (in_workspace or in_output):
        return {"ok": False, "error": "Can only read from workspace/ or output/"}
    if not target.exists():
        return {"ok": False, "error": "File not found"}
    return {"ok": True, "content": target.read_text()[:5000]}


# ---------------------------------------------------------------------------
# Sandbox execution
# ---------------------------------------------------------------------------


def run_detector(cmd: str, network: bool) -> list[dict[str, Any]]:
    """Run detect.py on cmd and return any violations logged for this command."""
    env = {**os.environ, "SANDBOX_NETWORK": "1" if network else "0"}
    subprocess.run(
        ["python3", str(DETECT_PY)],
        input=cmd,
        capture_output=True,
        text=True,
        env=env,
    )
    if not LOG_FILE.exists():
        return []
    with LOG_FILE.open() as f:
        lines = [line for line in f if line.strip()]
    if not lines:
        return []
    last = json.loads(lines[-1])
    if last.get("command") == cmd:
        return last.get("violations", [])
    return []


def execute_command(
    cmd: str,
    network: bool,
    sandbox_script: Path,
    timeout: int = 60,
) -> dict[str, Any]:
    """Execute cmd via the sandbox script and return stdout/stderr/returncode."""
    args = [str(sandbox_script)]
    if network:
        args.append("--network")
    args.append(cmd)
    try:
        proc = subprocess.run(
            args,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"TIMEOUT after {timeout}s", "returncode": -1}


# ---------------------------------------------------------------------------
# LLM dispatch
# ---------------------------------------------------------------------------


def get_model_response(
    messages: list[dict[str, str]],
    model: str,
    provider: str = "ollama",
    api_key: str = "",
) -> str:
    """Dispatch to the appropriate LLM backend and return the assistant text.

    provider: "ollama" | "anthropic" | "openai"
    api_key:  required for anthropic / openai; ignored for ollama
    """
    if provider == "anthropic":
        return _get_response_anthropic(messages, model, api_key)
    if provider == "openai":
        return _get_response_openai(messages, model, api_key)
    return _get_response_ollama(messages, model)


def _get_response_ollama(messages: list[dict[str, str]], model: str) -> str:
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": model, "messages": full_messages, "stream": False, "options": {"temperature": 0.2}},
            timeout=120,
        )
        if resp.status_code != 200:
            ct = resp.headers.get("Content-Type", "")
            error = resp.json().get("error", resp.text) if "application/json" in ct else resp.text
            return f"<done>Ollama API Error: {error}. Check if model '{model}' is pulled.</done>"
        return resp.json()["message"]["content"]
    except Exception as exc:
        return f"<done>Connection Error: {exc}</done>"


def _get_response_anthropic(messages: list[dict[str, str]], model: str, api_key: str) -> str:
    try:
        import anthropic as _sdk
        client = _sdk.Anthropic(api_key=api_key or None)
        resp = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=messages,
            temperature=0.2,
        )
        return resp.content[0].text
    except ImportError:
        return "<done>anthropic package not installed. Run: pip install anthropic</done>"
    except Exception as exc:
        return f"<done>Anthropic API Error: {exc}</done>"


def _get_response_openai(messages: list[dict[str, str]], model: str, api_key: str) -> str:
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": full_messages, "temperature": 0.2},
            timeout=120,
        )
        if resp.status_code != 200:
            return f"<done>OpenAI API Error: {resp.status_code} — {resp.text[:300]}</done>"
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        return f"<done>OpenAI Error: {exc}</done>"


# ---------------------------------------------------------------------------
# Agent turn orchestration
# ---------------------------------------------------------------------------


def handle_assistant_turn(
    messages: list[dict[str, str]],
    model: str,
    sandbox_script: Path,
    block_severity: str = "HIGH",
    provider: str = "ollama",
    api_key: str = "",
) -> dict[str, Any]:
    """Run one agent turn: call LLM, parse the first tag, execute the action.

    Returns a dict with keys: assistant_text, action_kind, result.
    """
    reply = get_model_response(messages, model, provider=provider, api_key=api_key)
    tags = parse_tags(reply)

    if not tags:
        return {"assistant_text": reply, "action_kind": "none", "result": {"note": "No tags found."}}

    tag = tags[0]

    if tag["tag"] == "done":
        return {"assistant_text": reply, "action_kind": "done", "result": {"summary": tag["body"]}}

    if tag["tag"] == "write":
        rel = tag["attrs"].get("path", "")
        return {"assistant_text": reply, "action_kind": "write", "result": write_workspace_file(rel, tag["body"])}

    if tag["tag"] == "read":
        rel = tag["attrs"].get("path", "")
        return {"assistant_text": reply, "action_kind": "read", "result": read_workspace_file(rel)}

    if tag["tag"] == "run":
        cmd = tag["body"]
        network = tag["attrs"].get("net", "0") == "1"
        violations = run_detector(cmd, network)
        threshold = _SEVERITY_ORDER.get(block_severity, 3)
        blocked = any(_SEVERITY_ORDER.get(v["severity"], 0) >= threshold for v in violations)

        if blocked:
            return {
                "assistant_text": reply,
                "action_kind": "run",
                "result": {"blocked": True, "violations": violations, "command": cmd, "network": network},
            }

        exec_result = execute_command(cmd, network, sandbox_script)
        return {
            "assistant_text": reply,
            "action_kind": "run",
            "result": {"blocked": False, "violations": violations, "command": cmd, "network": network, **exec_result},
        }

    return {"assistant_text": reply, "action_kind": "unknown", "result": {"tag": tag["tag"]}}


def format_action_for_model(action_kind: str, result: dict[str, Any]) -> str:
    """Format the result of an agent action as a feedback message for the LLM."""
    if action_kind == "write":
        if result.get("ok"):
            return f"FILE WRITTEN: {result['path']} ({result['bytes']} bytes). Next step?"
        return f"WRITE FAILED: {result.get('error')}."

    if action_kind == "read":
        if result.get("ok"):
            return f"FILE CONTENTS:\n```\n{result['content']}\n```\nNext step?"
        return f"READ FAILED: {result.get('error')}."

    if action_kind == "run":
        if result.get("blocked"):
            rules = ", ".join(f"{v['severity']} {v['rule']}" for v in result["violations"])
            return f"COMMAND REFUSED. Violations: {rules}. Reconsider approach."
        rc = result.get("returncode", -1)
        out = result.get("stdout", "")[:2000]
        err = result.get("stderr", "")[:1000]
        return f"COMMAND EXECUTED. exit={rc}\nSTDOUT:\n{out}\nSTDERR:\n{err}\nNext step?"

    return "No action taken."
