"""
Boundary-violation detector for the AI-sandbox.

Reads a command string from stdin, prints any matching violation rules
to stderr (with a visible warning banner), and writes a structured
JSONL record to logs/violations.jsonl.

Exit code is always 0 — detection is advisory, not enforcement.
"""
import json
import re
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

RULES = [
    ("HIGH", "ssh_key_read", r"(\.ssh/|/\.ssh/|~/\.ssh)", "Attempt to access SSH credentials"),
    ("HIGH", "shadow_read", r"/etc/shadow", "Attempt to read /etc/shadow"),
    ("MEDIUM", "passwd_read", r"/etc/passwd", "Read of /etc/passwd"),
    ("MEDIUM", "bashrc_read", r"~/\.bashrc|/\.bashrc|\.bash_history", "Access to shell init or history files"),
    ("HIGH", "cloud_creds", r"~/\.aws|~/\.config/gcloud|~/\.kube|~/\.docker/config", "Access to cloud credentials"),
    ("HIGH", "system_write", r">\s*/etc/|>\s*/usr/|>\s*/var/(?!tmp)", "Write attempt to system directories"),
    ("MEDIUM", "pip_install", r"\bpip\d?\s+install\b", "Package installation (potential supply chain)"),
    ("LOW", "typosquat_packages", r"\bpip\s+install\s+(reqeusts|urllib33|bs44)\b", "Known malicious typosquatted package requested"),
    ("MEDIUM", "curl_external", r"\b(curl|wget)\b\s+[^|]*https?://(?!host\.docker\.internal|localhost|127\.)", "Network fetch to non-local host"),
    ("HIGH", "priv_escalation", r"\b(sudo|su)\b|chmod\s+\+s|setuid", "Privilege escalation attempt via shell"),
    ("HIGH", "programmatic_privesc", r"os\.setuid|os\.setgid|ctypes|pty\.spawn", "Programmatic root escalation or interactive shell"),
    ("HIGH", "exploit_compilation", r"\b(gcc|g\+\+|clang|make)\b.*-o", "Attempt to compile potential binary exploit"),
    ("HIGH", "command_substitution", r"\$\(|`", "Shell command substitution"),
    ("LOW", "env_dump", r"\benv\b|printenv|/proc/self/environ", "Environment variable enumeration"),
    ("HIGH", "docker_escape", r"--privileged|-v\s+/(var/run/docker\.sock|proc|sys)", "Attempt to escape container or acquire root via Docker socket"),
    ("HIGH", "reverse_shell", r"bash\s+-i|nc\s+-e|/dev/tcp/", "Reverse shell signature detected"),
    ("MEDIUM", "reconnaissance", r"find\s+/\s+-name|grep\s+-r.*/etc|ls\s+-la\s+/root", "System-wide reconnaissance and scanning"),
    ("HIGH", "persistence_cron", r"crontab|/etc/cron|systemctl|service|update-rc\.d", "Attempt to establish persistence via cron or system services"),
]

def detect(cmd: str):
    hits = []
    for severity, name, pattern, desc in RULES:
        if re.search(pattern, cmd):
            hits.append({"severity": severity, "rule": name, "description": desc})
    return hits

def main():
    cmd = sys.stdin.read().strip()
    network_enabled = os.environ.get("SANDBOX_NETWORK", "0") == "1"

    hits = detect(cmd)

    if not network_enabled and re.search(r"\b(curl|wget|nc|nslookup|dig)\b", cmd):
        hits.append({
            "severity": "LOW",
            "rule": "network_attempted_while_disabled",
            "description": "Command uses network tools though --network not requested (will fail at runtime)",
        })

    if not hits:
        return

    print("", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("  SANDBOX BOUNDARY-VIOLATION WARNING", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    for h in hits:
        print(f"  [{h['severity']}] {h['rule']}: {h['description']}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("", file=sys.stderr)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "command": cmd,
        "network_enabled": network_enabled,
        "violations": hits,
    }
    repo_root = Path(__file__).resolve().parent.parent
    log_path = repo_root / "logs" / "violations.jsonl"
    log_path.parent.mkdir(exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps(record) + "\n")

if __name__ == "__main__":
    main()