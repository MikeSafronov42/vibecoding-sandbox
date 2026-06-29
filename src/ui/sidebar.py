"""Sidebar configuration widget and result dataclass."""
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from src.agents import opencode as opencode_agent
from src.config import SANDBOX_SCRIPTS


_PROVIDER_LABELS: dict[str, str] = {
    "Ollama (Local)": "ollama",
    "Anthropic Claude": "anthropic",
    "OpenAI GPT": "openai",
}


@dataclass
class SidebarConfig:
    """All user-selected options from the sidebar, resolved to concrete values."""

    agent_type: str
    provider_key: str
    provider_label: str
    model_choice: str
    api_key: str
    sandbox_script: Path
    runtime_label: str
    block_severity: str


def render() -> SidebarConfig:
    """Render the sidebar and return the selected configuration."""
    with st.sidebar:
        st.markdown("### Config")

        agent_type: str = st.selectbox(
            "Agent",
            ["Vibeguard Native", "OpenCode (Sandboxed)"],
            index=0,
            help=(
                "Vibeguard Native calls the LLM directly and routes tool tags through the sandbox.\n\n"
                "OpenCode runs the opencode CLI inside Docker — all file and shell operations are container-isolated."
            ),
        )

        provider_label: str = st.selectbox(
            "Provider",
            list(_PROVIDER_LABELS.keys()),
            index=0,
            help="Ollama runs locally. Anthropic and OpenAI need an API key.",
        )
        provider_key: str = _PROVIDER_LABELS[provider_label]

        live_models = opencode_agent.get_provider_models()
        model_choice: str = st.selectbox(
            "Model",
            live_models.get(provider_key, []),
            index=0,
        )

        api_key: str = ""
        if provider_key in ("anthropic", "openai"):
            api_key = st.text_input(
                f"{provider_label} API Key",
                type="password",
                help="Stored only in session memory, never written to disk.",
            )

        st.markdown("---")

        runtime_label: str = st.selectbox(
            "Sandbox",
            list(SANDBOX_SCRIPTS.keys()),
            index=0,
            help="Isolation runtime for code execution.",
        )

        block_severity: str = st.selectbox(
            "Block at",
            ["HIGH", "MEDIUM", "LOW"],
            index=0,
            help="Commands at this severity or above are refused.",
        )

        if agent_type == "OpenCode (Sandboxed)":
            if opencode_agent.image_exists():
                st.success("`aisandbox-opencode:v1` ready")
            else:
                st.warning(
                    "OpenCode image not built yet.\n\n"
                    "```bash\ndocker build -t aisandbox-opencode:v1 \\\n"
                    "  -f .docker/Dockerfile.opencode .docker/\n```"
                )

        st.markdown("---")
        if st.button("Clear chat"):
            st.session_state.chat_messages = []
            st.session_state.chat_log = []
            st.rerun()

    return SidebarConfig(
        agent_type=agent_type,
        provider_key=provider_key,
        provider_label=provider_label,
        model_choice=model_choice,
        api_key=api_key,
        sandbox_script=SANDBOX_SCRIPTS[runtime_label],
        runtime_label=runtime_label,
        block_severity=block_severity,
    )
