#!/bin/bash
# run_opencode.sh — run OpenCode inside the aisandbox-opencode container.
#
# OpenCode natively executes code on the host with no isolation. This wrapper
# inverts that: the whole opencode process (LLM calls, file writes, shell execs)
# runs inside a Docker container with the same hardening flags as run.sh.
#
# Required env vars (set by opencode_agent.py or callers):
#   OPENCODE_PROVIDER   anthropic | openai | ollama  (default: anthropic)
#   OPENCODE_MODEL      model ID without provider prefix (default: claude-sonnet-4-5)
#   ANTHROPIC_API_KEY   required when provider=anthropic
#   OPENAI_API_KEY      required when provider=openai
#   OLLAMA_MODEL        local model tag, required when provider=ollama
#
# The container gets --add-host=host.docker.internal because cloud-provider
# API calls need outbound network; Ollama needs access to the host daemon.
# --cap-drop=ALL and --security-opt=no-new-privileges still apply.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROMPT="${1:-}"

if [[ -z "$PROMPT" ]]; then
    echo "Usage: run_opencode.sh <prompt>" >&2
    exit 1
fi

PROVIDER="${OPENCODE_PROVIDER:-anthropic}"
MODEL_ID="${OPENCODE_MODEL:-claude-sonnet-4-5}"

# Build a minimal opencode.json config for the selected provider.
# Injected via OPENCODE_CONFIG_CONTENT (natively supported by opencode).
case "$PROVIDER" in
    ollama)
        OLLAMA_MDL="${OLLAMA_MODEL:-qwen2.5-coder:7b}"
        CFG=$(printf \
            '{"model":"ollama/%s","provider":{"ollama":{"npm":"@ai-sdk/openai-compatible","name":"Ollama","options":{"baseURL":"http://host.docker.internal:11434/v1"},"models":{"%s":{"name":"%s"}}}}}' \
            "$OLLAMA_MDL" "$OLLAMA_MDL" "$OLLAMA_MDL")
        ;;
    openai)
        CFG=$(printf '{"model":"openai/%s"}' "$MODEL_ID")
        ;;
    anthropic|*)
        CFG=$(printf '{"model":"anthropic/%s"}' "$MODEL_ID")
        ;;
esac

docker run --rm \
    --add-host=host.docker.internal:host-gateway \
    --cap-drop=ALL \
    --security-opt=no-new-privileges \
    --memory=4g \
    --cpus=2 \
    -v "${REPO_DIR}/output:/output" \
    -v "${REPO_DIR}/workspace:/workspace" \
    -e "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}" \
    -e "OPENAI_API_KEY=${OPENAI_API_KEY:-}" \
    -e "OPENCODE_CONFIG_CONTENT=${CFG}" \
    -e "HOME=/home/agent" \
    aisandbox-opencode:v1 \
    opencode run --format json "$PROMPT"
