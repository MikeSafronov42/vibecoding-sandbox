"""
Agent chat backend for the demo dashboard.

Sends conversation to Ollama, parses the response for tagged tool calls,
routes execution through the sandbox, and enforces a blocking policy
on high-severity boundary violations.
"""
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Dict
import requests

REPO = Path(__file__).resolve().parent
DETECT_PY = REPO / "sandbox" / "detect.py"
WORKSPACE = REPO / "workspace"
OUTPUT = REPO / "output"

OLLAMA_URL = "http://localhost:11434/api/chat"

SYSTEM_PROMPT = """You are a coding agent operating inside a SECURITY-CONSTRAINED sandbox.

Every command you propose is screened. HIGH-severity attempts
(reading SSH keys, /etc/shadow, cloud credentials, writes to /etc, sudo)
WILL BE REFUSED. Do not waste turns trying to bypass the sandbox.

## File system layout - IMPORTANT

You have TWO ways to put files in place:

1. The <write> tag writes a file on the HOST. The path is RELATIVE to
   the project root. It must start with "workspace/". Inside the sandbox
   that file becomes visible at /workspace/<filename>.

2. The <run> tag runs a shell command INSIDE the sandbox container.
   Inside the container:
     - /workspace/    is your code (mirrors what <write> creates on the host)
     - /output/       is where your final outputs MUST go (the user sees these)
     - your shell home is /home/agent  (empty by default - no keys, no creds)

You do NOT need to mkdir /workspace or workspace anywhere. Both already exist.

## Protocol - exactly one tag per response

WARNING: The examples below are syntax demonstrations. DO NOT copy-paste them. Write your own code based on the user's request!

- Run a command (no network):
  <run net="0">python /workspace/app.py</run>

- Run a command (with network):
  <run net="1">curl -s http://example.com/api/data</run>

- Write a file (path starts with workspace/):
  <write path="workspace/app.py">
  print("Hello")
  </write>

- Read a file you previously wrote:
  <read path="workspace/app.py"/>

- When the user task is complete:
  <done>brief summary of what you did</done>

## Rules

- ONE tag per response. After the tag you may add a short plain text comment, nothing else.
- Wait for the result of each action before issuing the next one.
- If a command is refused, do not retry it. Reconsider.
- To write a file then run it: first emit <write>, wait for confirmation, then emit <run> referencing /workspace/<filename>.
- Final results (HTML files, CSV files, summaries) must be saved to /output/, NOT /workspace/.
"""

def run_detector(cmd: str, network: bool) -> List[Dict]:
    env = {"SANDBOX_NETWORK": "1" if network else "0"}
    subprocess.run(
        ["python3", str(DETECT_PY)],
        input=cmd,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, **env},
    )
    log_file = REPO / "logs" / "violations.jsonl"
    if not log_file.exists():
        return []
    with log_file.open() as f:
        lines = [l for l in f if l.strip()]
    if not lines:
        return []
    last = json.loads(lines[-1])
    if last.get("command") == cmd:
        return last.get("violations", [])
    return []

def execute_command(cmd: str, network: bool, sandbox_script: Path, timeout: int = 60) -> Dict:
    args = [str(sandbox_script)]
    if network:
        args.append("--network")
    args.append(cmd)
    try:
        proc = subprocess.run(
            args, cwd=str(REPO),
            capture_output=True, text=True, timeout=timeout,
        )
        return {"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"TIMEOUT after {timeout}s", "returncode": -1}

def write_workspace_file(rel_path: str, content: str) -> Dict:
    if not rel_path.startswith("workspace/"):
        return {"ok": False, "error": f"Path must start with 'workspace/', got: {rel_path}"}
    target = (REPO / rel_path).resolve()
    if not str(target).startswith(str(WORKSPACE.resolve())):
        return {"ok": False, "error": "Path escapes workspace directory"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {"ok": True, "path": rel_path, "bytes": len(content)}

def read_workspace_file(rel_path: str) -> Dict:
    target = (REPO / rel_path).resolve()
    if not str(target).startswith(str(WORKSPACE.resolve())) and not str(target).startswith(str(OUTPUT.resolve())):
        return {"ok": False, "error": "Can only read from workspace/ or output/"}
    if not target.exists():
        return {"ok": False, "error": "File not found"}
    return {"ok": True, "content": target.read_text()[:5000]}

TAG_RE = re.compile(r'<(run|write|read|done)([^>]*)>(.*?)(?:</\1>|/>)', re.DOTALL)
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')

def parse_tags(text: str) -> List[Dict]:
    results = []
    for m in TAG_RE.finditer(text):
        tag = m.group(1)
        attrs = dict(ATTR_RE.findall(m.group(2)))
        body = m.group(3) or ""
        results.append({"tag": tag, "attrs": attrs, "body": body.strip()})
    return results

def get_model_response(messages: List[Dict], model: str) -> str:
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": model, "messages": full_messages, "stream": False, "options": {"temperature": 0.2}},
            timeout=120,
        )
        if resp.status_code != 200:
            error_msg = resp.json().get("error", resp.text) if "application/json" in resp.headers.get("Content-Type", "") else resp.text
            return f"<done>Ollama API Error: {error_msg}. Check if model '{model}' is pulled.</done>"
        return resp.json()["message"]["content"]
    except Exception as e:
        return f"<done>Connection Error: {str(e)}</done>"

def handle_assistant_turn(messages: List[Dict], model: str, sandbox_script: Path, block_severity: str = "HIGH") -> Dict:
    reply = get_model_response(messages, model)
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
        severity_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        threshold = severity_order.get(block_severity, 3)
        blocked = any(severity_order.get(v["severity"], 0) >= threshold for v in violations)

        if blocked:
            return {"assistant_text": reply, "action_kind": "run", "result": {"blocked": True, "violations": violations, "command": cmd, "network": network}}

        exec_result = execute_command(cmd, network, sandbox_script)
        return {"assistant_text": reply, "action_kind": "run", "result": {"blocked": False, "violations": violations, "command": cmd, "network": network, **exec_result}}

    return {"assistant_text": reply, "action_kind": "unknown", "result": {"tag": tag["tag"]}}

def format_action_for_model(action_kind: str, result: Dict) -> str:
    if action_kind == "write":
        if result.get("ok"): return f"FILE WRITTEN: {result['path']} ({result['bytes']} bytes). Next step?"
        return f"WRITE FAILED: {result.get('error')}."
    if action_kind == "read":
        if result.get("ok"): return f"FILE CONTENTS:\n```\n{result['content']}\n```\nNext step?"
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