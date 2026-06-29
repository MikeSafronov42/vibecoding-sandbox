#!/bin/bash
# Smoke test for the AI sandbox. Run from the repo root:
#   ./scripts/smoke_test.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="${REPO_DIR}/scripts/run.sh"
PASS=0
FAIL=0

# ── helpers ──────────────────────────────────────────────────────────────────

green() { printf '\033[32m  PASS\033[0m  %s\n' "$1"; }
red()   { printf '\033[31m  FAIL\033[0m  %s\n' "$1"; }

# expect_exit <expected_code> <label> <cmd...>
expect_exit() {
    local expected=$1 label=$2; shift 2
    local actual=0
    "$@" >/dev/null 2>&1 || actual=$?
    if [[ $actual -eq $expected ]]; then
        green "$label"
        (( PASS++ )) || true
    else
        red "$label (expected exit $expected, got $actual)"
        (( FAIL++ )) || true
    fi
}

# expect_success <label> <cmd...>
expect_success() { expect_exit 0 "$@"; }

# expect_failure <label> <cmd...>  — any non-zero exit counts
expect_failure() {
    local label=$1; shift
    local actual=0
    "$@" >/dev/null 2>&1 || actual=$?
    if [[ $actual -ne 0 ]]; then
        green "$label"
        (( PASS++ )) || true
    else
        red "$label (expected non-zero exit, got 0)"
        (( FAIL++ )) || true
    fi
}

# expect_output_contains <label> <pattern> <cmd...>
expect_output_contains() {
    local label=$1 pattern=$2; shift 2
    local out
    out=$("$@" 2>&1) || true
    if echo "$out" | grep -q "$pattern"; then
        green "$label"
        (( PASS++ )) || true
    else
        red "$label (pattern '$pattern' not found in output)"
        (( FAIL++ )) || true
    fi
}

# expect_output_not_contains <label> <pattern> <cmd...>
expect_output_not_contains() {
    local label=$1 pattern=$2; shift 2
    local out
    out=$("$@" 2>&1) || true
    if ! echo "$out" | grep -q "$pattern"; then
        green "$label"
        (( PASS++ )) || true
    else
        red "$label (pattern '$pattern' unexpectedly found in output)"
        (( FAIL++ )) || true
    fi
}

echo ""
echo "=== AI Sandbox Smoke Test ==="
echo ""

# ── T0: prerequisites ─────────────────────────────────────────────────────────
echo "--- Prerequisites ---"

if docker image inspect aisandbox:v1 --format "{{.Id}}" >/dev/null 2>&1; then
    green "Docker image aisandbox:v1 exists"
    (( PASS++ )) || true
else
    red "Docker image aisandbox:v1 not found — build it first"
    (( FAIL++ )) || true
    echo ""
    echo "ABORTED: cannot run container tests without the image."
    exit 1
fi

echo ""
echo "--- T1: Basic execution ---"
expect_success "echo inside container" \
    "$RUN" echo "sandbox alive"

echo ""
echo "--- T2: Output mount ---"
rm -f "${REPO_DIR}/output/smoke_test_marker.txt"
expect_success "write to /output inside container" \
    "$RUN" bash -c "echo smoketest > /output/smoke_test_marker.txt"
if [[ -f "${REPO_DIR}/output/smoke_test_marker.txt" ]]; then
    green "output file persisted to host"
    (( PASS++ )) || true
else
    red "output file not found on host after container write"
    (( FAIL++ )) || true
fi
rm -f "${REPO_DIR}/output/smoke_test_marker.txt"

echo ""
echo "--- T3: Network blocked by default ---"
expect_failure "curl fails without --network flag" \
    "$RUN" curl -s --max-time 3 http://example.com

echo ""
echo "--- T4: Network allowed with --network flag ---"
expect_success "curl succeeds with --network flag" \
    "$RUN" --network curl -s --max-time 10 http://example.com

echo ""
echo "--- T5: Host SSH keys unreachable ---"
# ~ inside the container resolves to /home/agent, not the host home.
# cat ~/.ssh/id_rsa should fail because /home/agent/.ssh/id_rsa doesn't exist.
expect_failure "host ~/.ssh/id_rsa is unreachable inside container" \
    "$RUN" cat ~/.ssh/id_rsa

echo ""
echo "--- T6: Host filesystem isolation ---"
# /etc/shadow is host-only; the container has its own minimal /etc/shadow.
# Even if the container's shadow exists, it must not contain host user data.
expect_output_not_contains \
    "host username not in container /etc/passwd" \
    "$(whoami)" \
    "$RUN" cat /etc/passwd

echo ""
echo "--- T7: Runs as non-root ---"
expect_output_contains "whoami returns 'agent' (non-root)" "agent" \
    "$RUN" whoami

echo ""
echo "--- T8: Command substitution rejected by run.sh ---"
# run.sh must reject arguments containing \$( or backticks before reaching docker.
expect_failure "run.sh rejects backtick substitution" \
    "$RUN" echo "\`id\`"
expect_failure "run.sh rejects \$() substitution" \
    "$RUN" echo "\$(id)"

echo ""
echo "--- T9: Workspace mount ---"
TMP_FILE="${REPO_DIR}/workspace/smoke_test_ws.txt"
echo "hello" > "$TMP_FILE"
expect_output_contains "host file readable at /workspace inside container" "hello" \
    "$RUN" cat /workspace/smoke_test_ws.txt
rm -f "$TMP_FILE"

echo ""
echo "--- T10: Capabilities dropped ---"
# ping requires CAP_NET_RAW; with --cap-drop=ALL it must fail.
expect_failure "ping fails (CAP_NET_RAW dropped)" \
    "$RUN" ping -c 1 127.0.0.1

echo ""
echo "============================================"
printf "  Results: \033[32m%d passed\033[0m, \033[31m%d failed\033[0m\n" "$PASS" "$FAIL"
echo "============================================"
echo ""

[[ $FAIL -eq 0 ]]
