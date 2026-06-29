"""Violation detector for the AI sandbox.

Reads a command string from stdin, prints matching rules to stderr,
and appends a JSONL record to logs/violations.jsonl.

Exit code is always 0 — detection is advisory, not enforcement.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

RULES: list[tuple[str, str, str, str]] = [
    ("HIGH",   "ssh_key_read",               r"(\.ssh/|/\.ssh/|~/\.ssh)",                                    "SSH key access"),
    ("HIGH",   "shadow_read",                r"/etc/shadow",                                                  "Reading /etc/shadow"),
    ("MEDIUM", "passwd_read",                r"/etc/passwd",                                                  "Reading /etc/passwd"),
    ("MEDIUM", "bashrc_read",                r"~/\.bashrc|/\.bashrc|\.bash_history",                          "Shell config or history access"),
    ("HIGH",   "cloud_creds",                r"~/\.aws|~/\.config/gcloud|~/\.kube|~/\.docker/config",         "Cloud credential access"),
    ("HIGH",   "system_write",               r">\s*/etc/|>\s*/usr/|>\s*/var/(?!tmp)",                         "Write to system directory"),
    ("MEDIUM", "pip_install",                r"\bpip\d?\s+install\b",                                         "Package install"),
    ("LOW",    "typosquat_packages",         r"\bpip\s+install\s+(reqeusts|urllib33|bs44)\b",                 "Known fake package name"),
    ("MEDIUM", "curl_external",              r"\b(curl|wget)\b\s+[^|]*https?://(?!host\.docker\.internal|localhost|127\.)", "Network fetch to external host"),
    ("HIGH",   "priv_escalation",            r"\b(sudo|su)\b|chmod\s+\+s|setuid",                            "Privilege escalation"),
    ("HIGH",   "programmatic_privesc",       r"os\.setuid|os\.setgid|ctypes|pty\.spawn",                     "Root access via code"),
    ("HIGH",   "exploit_compilation",        r"\b(gcc|g\+\+|clang|make)\b.*-o",                              "Binary compilation"),
    ("HIGH",   "command_substitution",       r"\$\(|`",                                                       "Shell command substitution"),
    ("LOW",    "env_dump",                   r"\benv\b|printenv|/proc/self/environ",                          "Environment dump"),
    ("HIGH",   "docker_escape",              r"--privileged|-v\s+/(var/run/docker\.sock|proc|sys)",           "Docker escape attempt"),
    ("HIGH",   "reverse_shell",              r"bash\s+-i|nc\s+-e|/dev/tcp/",                                  "Reverse shell"),
    ("MEDIUM", "reconnaissance",             r"find\s+/\s+-name|grep\s+-r.*/etc|ls\s+-la\s+/root",           "File system scan"),
    ("HIGH",   "persistence_cron",           r"crontab|/etc/cron|systemctl|service|update-rc\.d",            "Backdoor via cron or services"),
]


def detect(cmd: str) -> list[dict[str, str]]:
    """Return all rules that match cmd."""
    return [
        {"severity": sev, "rule": name, "description": desc}
        for sev, name, pattern, desc in RULES
        if re.search(pattern, cmd)
    ]


def main() -> None:
    """Read a command from stdin, detect violations, and log any hits."""
    cmd = sys.stdin.read().strip()
    network_enabled = os.environ.get("SANDBOX_NETWORK", "0") == "1"

    hits = detect(cmd)

    if not network_enabled and re.search(r"\b(curl|wget|nc|nslookup|dig)\b", cmd):
        hits.append({
            "severity": "LOW",
            "rule": "network_tool_without_flag",
            "description": "Network tool used without --network flag (will fail at runtime)",
        })

    if not hits:
        return

    print("", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("  SANDBOX VIOLATION WARNING", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    for h in hits:
        print(f"  [{h['severity']}] {h['rule']}: {h['description']}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("", file=sys.stderr)

    repo_root = Path(__file__).resolve().parent.parent
    log_path = repo_root / "logs" / "violations.jsonl"
    log_path.parent.mkdir(exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "command": cmd,
        "network_enabled": network_enabled,
        "violations": hits,
    }
    with log_path.open("a") as f:
        f.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    main()
