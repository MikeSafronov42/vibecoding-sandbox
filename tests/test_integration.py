"""Comprehensive integration test suite for the vibecoding-sandbox."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from src.agents import native as native_agent
from src.config import DETECT_PY, LOG_FILE, OUTPUT, REPO, WORKSPACE
from src.sandbox import docker_image_exists

SANDBOX_SCRIPTS: dict[str, Path] = {
    "Docker (runc)": REPO / "sandbox" / "run.sh",
    "gVisor (runsc)": REPO / "sandbox" / "run_gvisor.sh",
    "nsjail": REPO / "sandbox" / "run_nsjail.sh",
}

TEST_MODELS: list[str] = [
    "qwen2.5-coder:7b",
    "deepseek-coder:6.7b",
    "gemma4:e4b",
    "qwen3.5:9b",
]


def _print_header(title: str) -> None:
    print(f"\n{'='*60}\n--- {title} ---\n{'='*60}")


def _print_result(name: str, success: bool, details: str = "") -> None:
    """Print a single test result line."""
    status = "SKIP" if "SKIPPED" in details else ("PASS" if success else "FAIL")
    print(f"{name:<45} [{status}] {details}")


def _log_file_lines() -> list[str]:
    if not LOG_FILE.exists():
        return []
    with open(LOG_FILE) as f:
        return f.readlines()


def test_detector() -> bool:
    """Verify that detect.py flags SSH key reads and writes a JSONL log entry."""
    _print_header("TESTING VIOLATION DETECTOR")
    test_cmd = "cat ~/.ssh/id_rsa > /output/keys.txt"

    lines_before = len(_log_file_lines())
    proc = subprocess.run(
        ["python3", str(DETECT_PY)],
        input=test_cmd,
        capture_output=True,
        text=True,
    )
    lines_after = _log_file_lines()

    logged = False
    if len(lines_after) > lines_before:
        last = json.loads(lines_after[-1])
        logged = last.get("command") == test_cmd

    _print_result("Detects SSH key read", "ssh_key_read" in proc.stderr)
    _print_result("Writes JSON log entry", logged)
    return logged and "ssh_key_read" in proc.stderr


def test_sandbox_security(name: str, script: Path) -> bool:
    """Run four isolation checks against the given sandbox runtime.

    Returns True only if all checks pass (or the runtime is unavailable).
    """
    print(f"\n>>> Security & Isolation tests: {name}")

    test_file = OUTPUT / "test_write.txt"
    if test_file.exists():
        test_file.unlink()

    res_write = subprocess.run(
        [str(script), "echo 'sandbox_write_success' > /output/test_write.txt"],
        capture_output=True,
        text=True,
    )
    if "runtime" in res_write.stderr.lower() or "not found" in res_write.stderr.lower():
        _print_result("Host Runtime Availability", False, "[SKIPPED] Runtime missing on host")
        return True

    write_ok = test_file.exists() and "sandbox_write_success" in test_file.read_text()
    _print_result("1. Volume Mount (/output) Writability", write_ok)

    res_net = subprocess.run(
        [str(script), "curl -s --connect-timeout 2 http://example.com"],
        capture_output=True,
        text=True,
    )
    net_ok = res_net.returncode != 0
    _print_result("2. Network Isolation (Default Deny)", net_ok)

    res_fs = subprocess.run(
        [str(script), "cat /etc/shadow"],
        capture_output=True,
        text=True,
    )
    fs_ok = res_fs.returncode != 0 and "root:" not in res_fs.stdout
    _print_result("3. Host Filesystem Isolation (/etc/shadow)", fs_ok)

    res_priv = subprocess.run(
        [str(script), "sudo whoami"],
        capture_output=True,
        text=True,
    )
    priv_ok = "root" not in res_priv.stdout
    _print_result("4. Privilege Dropping (sudo blocked)", priv_ok)

    return all([write_ok, net_ok, fs_ok, priv_ok])


def test_e2e_agent_workflow() -> bool:
    """Verify the write→run agent workflow end-to-end against Docker (runc)."""
    _print_header("TESTING END-TO-END AGENT WORKFLOW")
    sandbox = SANDBOX_SCRIPTS["Docker (runc)"]

    print("Testing <write> tag parsing and execution...", end=" ")
    res_write = native_agent.write_workspace_file("workspace/e2e_test.py", "print('E2E_SUCCESS_42')")
    if res_write["ok"] and (WORKSPACE / "e2e_test.py").exists():
        print("PASS")
    else:
        print("FAIL")
        return False

    print("Testing <run> tag execution through backend...", end=" ")
    res_run = native_agent.execute_command("python /workspace/e2e_test.py", network=False, sandbox_script=sandbox)
    if "E2E_SUCCESS_42" in res_run["stdout"]:
        print("PASS")
    else:
        print("FAIL")
        return False

    return True


def test_models() -> bool:
    """Ping each local Ollama model to verify connectivity."""
    _print_header("TESTING MODELS API CONNECTIVITY")
    success = True
    test_message = [{"role": "user", "content": "Integration ping. Respond with <done>ok</done>."}]

    for model in TEST_MODELS:
        print(f"Connecting to {model}...", end=" ", flush=True)
        try:
            t0 = time.time()
            response = native_agent.get_model_response(test_message, model)
            elapsed = time.time() - t0
            if "Error:" in response or ("error" in response.lower() and "ollama" in response.lower()):
                print(f"\n{model:<34} [FAIL] {response.strip()}")
                success = False
            else:
                print(f"OK ({elapsed:.1f}s)")
        except Exception as exc:
            print(f"\n{model:<34} [FAIL] {exc}")
            success = False

    return success


def main() -> None:
    """Run all integration tests and exit with 0 (all passed) or 1 (failures)."""
    print("Initializing Vibeguard Comprehensive Test Suite...\n")
    all_passed = True

    for name, script in SANDBOX_SCRIPTS.items():
        if not os.access(script, os.X_OK):
            print(f"CRITICAL ERROR: {script.name} is not executable. Run 'chmod +x scripts/*.sh' first.")
            sys.exit(1)

    if not test_detector():
        all_passed = False

    _print_header("TESTING SANDBOX SECURITY & ISOLATION")
    for name, script in SANDBOX_SCRIPTS.items():
        if not test_sandbox_security(name, script):
            all_passed = False

    if not test_e2e_agent_workflow():
        all_passed = False

    if not test_models():
        all_passed = False

    _print_header("FINAL TEST SUMMARY")
    if all_passed:
        print("ALL TESTS PASSED. The environment is secure, isolated, and operational.")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED. Review the logs above to identify the breach or error.")
        sys.exit(1)


if __name__ == "__main__":
    main()
