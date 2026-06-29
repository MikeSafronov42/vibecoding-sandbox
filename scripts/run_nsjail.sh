#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NETWORK_FLAG="--network=none"
EXTRA_FLAGS=()
NET_FLAG_VALUE=0

if [[ "${1:-}" == "--network" ]]; then
    NETWORK_FLAG=""
    EXTRA_FLAGS+=(--add-host=host.docker.internal:host-gateway)
    NET_FLAG_VALUE=1
    shift
fi

for arg in "$@"; do
    case "$arg" in
        *'`'*|*'$('*)
            echo "ERROR: command substitution not permitted." >&2
            exit 2
            ;;
    esac
done

CMD="$*"

SANDBOX_NETWORK="${NET_FLAG_VALUE}" echo "${CMD}" | python3 "${REPO_DIR}/sandbox/detect.py" || true

docker run --rm -i \
    ${NETWORK_FLAG} \
    "${EXTRA_FLAGS[@]}" \
    --cap-drop=ALL \
    --security-opt=no-new-privileges \
    --read-only \
    --memory=512m \
    --cpus=1 \
    -v "${REPO_DIR}/output:/output" \
    -v "${REPO_DIR}/workspace:/workspace" \
    aisandbox:v1 \
    bash -c "${CMD}"