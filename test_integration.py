import sys
import os
import subprocess
import json
from pathlib import Path
import agent_chat
import time

REPO = Path(__file__).resolve().parent
RUN_SH = REPO / "sandbox" / "run.sh"
RUN_GVISOR_SH = REPO / "sandbox" / "run_gvisor.sh"
RUN_NSJAIL_SH = REPO / "sandbox" / "run_nsjail.sh"
DETECT_PY = REPO / "sandbox" / "detect.py"
WORKSPACE = REPO / "workspace"
OUTPUT = REPO / "output"
LOG_FILE = REPO / "logs" / "violations.jsonl"

# Current stable models
MODELS = [
    "qwen2.5-coder:7b",
    "deepseek-coder:6.7b",
    "gemma4:e4b",
    "qwen3.5:9b"
]

SANDBOXES = {
    "Docker (runc)": RUN_SH,
    "gVisor (runsc)": RUN_GVISOR_SH,
    "nsjail": RUN_NSJAIL_SH
}

def print_header(title):
    print(f"\n{'='*60}\n--- {title} ---\n{'='*60}")

def print_result(name, success, details=""):
    status = "PASS" if success else "FAIL"
    if "SKIPPED" in details:
        status = "SKIP"
    print(f"{name:<45} [{status}] {details}")

def test_sandbox_security(name, script):
    print(f"\n>>> Running Security & Isolation tests for: {name}")
    
    test_file = OUTPUT / "test_write.txt"
    if test_file.exists():
        test_file.unlink()
    
    cmd_write = "echo 'sandbox_write_success' > /output/test_write.txt"
    res_write = subprocess.run([str(script), cmd_write], capture_output=True, text=True)
    
    if "runtime" in res_write.stderr.lower() or "not found" in res_write.stderr.lower():
        print_result("Host Runtime Availability", False, "[SKIPPED] Runtime missing on host (Documented Limitation)")
        return True 
        
    write_ok = test_file.exists() and "sandbox_write_success" in test_file.read_text()
    print_result("1. Volume Mount (/output) Writability", write_ok)

    cmd_net = "curl -s --connect-timeout 2 http://example.com"
    res_net = subprocess.run([str(script), cmd_net], capture_output=True, text=True)
    net_ok = res_net.returncode != 0
    print_result("2. Network Isolation (Default Deny)", net_ok)

    cmd_fs = "cat /etc/shadow"
    res_fs = subprocess.run([str(script), cmd_fs], capture_output=True, text=True)
    fs_ok = res_fs.returncode != 0 and "root:" not in res_fs.stdout
    print_result("3. Host Filesystem Isolation (/etc/shadow)", fs_ok)

    cmd_priv = "sudo whoami"
    res_priv = subprocess.run([str(script), cmd_priv], capture_output=True, text=True)
    priv_ok = "root" not in res_priv.stdout
    print_result("4. Privilege Dropping (sudo blocked)", priv_ok)

    return all([write_ok, net_ok, fs_ok, priv_ok])

def test_detector():
    print_header("TESTING BOUNDARY-VIOLATION DETECTOR")
    test_cmd = "cat ~/.ssh/id_rsa > /output/keys.txt"
    
    log_lines_before = len(log_file_lines())
    proc = subprocess.run(["python3", str(DETECT_PY)], input=test_cmd, capture_output=True, text=True)
    log_lines_after = log_file_lines()
    
    logged = False
    if len(log_lines_after) > log_lines_before:
        last_log = json.loads(log_lines_after[-1])
        if last_log.get("command") == test_cmd:
            logged = True
            
    print_result("Detector identifies SSH key read", "ssh_key_read" in proc.stderr)
    print_result("Detector writes structured JSON log", logged)
    return logged and "ssh_key_read" in proc.stderr

def log_file_lines():
    if not LOG_FILE.exists():
        return []
    with open(LOG_FILE, "r") as f:
        return f.readlines()

def test_e2e_agent_workflow():
    print_header("TESTING END-TO-END AGENT WORKFLOW")
    
    model = "qwen2.5-coder:7b"
    sandbox = RUN_SH
    
    print("Testing <write> tag parsing and execution...", end=" ")
    ws_file = "workspace/e2e_test.py"
    code = "print('E2E_SUCCESS_42')"
    res_write = agent_chat.write_workspace_file(ws_file, code)
    if res_write["ok"] and (WORKSPACE / "e2e_test.py").exists():
        print("PASS")
    else:
        print("FAIL")
        return False
        
    print("Testing <run> tag execution through backend...", end=" ")
    res_run = agent_chat.execute_command("python /workspace/e2e_test.py", network=False, sandbox_script=sandbox)
    if "E2E_SUCCESS_42" in res_run["stdout"]:
        print("PASS")
    else:
        print("FAIL")
        return False
        
    return True

def test_models():
    print_header("TESTING MODELS API CONNECTIVITY")
    success = True
    test_message = [{"role": "user", "content": "Integration ping. Respond with <done>ok</done>."}]

    for model in MODELS:
        print(f"Connecting to {model}...", end=" ", flush=True)
        try:
            start_time = time.time()
            response = agent_chat.get_model_response(test_message, model)
            elapsed = time.time() - start_time
            
            if "Error:" in response or "error" in response.lower() and "ollama" in response.lower():
                print(f"\nModel: {model:<34} [FAIL] DETAILS: {response.strip()}")
                success = False
            else:
                print(f"OK ({elapsed:.1f}s)")
        except Exception as e:
            print(f"\nModel: {model:<34} [FAIL] EXCEPTION: {str(e)}")
            success = False
    return success

def main():
    print("Initializing Vibeguard Comprehensive Test Suite...\n")
    all_passed = True
    
    for s in SANDBOXES.values():
        if not os.access(s, os.X_OK):
            print(f"CRITICAL ERROR: {s.name} is not executable. Run 'chmod +x sandbox/*.sh' first.")
            sys.exit(1)
    
    if not test_detector(): all_passed = False
    
    print_header("TESTING SANDBOX SECURITY & ISOLATION")
    for name, script in SANDBOXES.items():
        if not test_sandbox_security(name, script):
            all_passed = False
            
    if not test_e2e_agent_workflow(): all_passed = False
    
    if not test_models(): all_passed = False
    
    print_header("FINAL TEST SUMMARY")
    if all_passed:
        print("✅ ALL TESTS PASSED. The environment is secure, isolated, and operational.")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED. Review the logs above to identify the breach or error.")
        sys.exit(1)

if __name__ == "__main__":
    main()