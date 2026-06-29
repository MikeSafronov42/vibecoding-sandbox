"""Python wrappers for sandbox operations used by the UI (non-agent paths)."""
import json
import subprocess
from pathlib import Path
from typing import Any

from src.config import LOG_FILE, REPO


def run_in_sandbox(
    cmd: str,
    sandbox_script: Path,
    network: bool = False,
    timeout: int = 60,
) -> tuple[str, str, int]:
    """Run cmd through the given sandbox script. Returns (stdout, stderr, returncode)."""
    args = [str(sandbox_script)]
    if network:
        args.append("--network")
    args.append(cmd)
    try:
        result = subprocess.run(
            args, cwd=str(REPO), capture_output=True, text=True, timeout=timeout
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"TIMEOUT after {timeout}s", -1


def read_log_lines() -> list[dict[str, Any]]:
    """Return all parsed JSONL records from the violations log."""
    if not LOG_FILE.exists():
        return []
    out: list[dict[str, Any]] = []
    with LOG_FILE.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def docker_image_exists(name: str = "aisandbox:v1") -> bool:
    """Return True if the named Docker image is available on the host."""
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False
