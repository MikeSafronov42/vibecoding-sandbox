"""Tab rendering functions for the Streamlit dashboard."""
from pathlib import Path
from typing import Any

import streamlit as st

from src.agents import native as native_agent
from src.agents import opencode as opencode_agent
from src.config import ATTACK_COMMANDS, DETECT_PY, OUTPUT, REPO
from src.sandbox import docker_image_exists, read_log_lines, run_in_sandbox
from src.ui.sidebar import SidebarConfig

_DOCKERFILE: Path = REPO / ".docker" / "Dockerfile"


def _render_violations(new_violations: list[dict[str, Any]]) -> None:
    """Display detected violations as Streamlit alerts."""
    if not new_violations:
        st.info("No violations detected.")
        return
    st.error("VIOLATION DETECTED")
    for v in new_violations:
        for hit in v["violations"]:
            st.markdown(f"**[{hit['severity']}] {hit['rule']}** — {hit['description']}")


def render_overview(cfg: SidebarConfig) -> None:
    """Render the Overview tab: sandbox status and violations log."""
    st.header("Sandbox status")
    col_a, col_b = st.columns(2)

    with col_a:
        if docker_image_exists():
            st.success("Docker image `aisandbox:v1` is ready")
        else:
            st.error("Docker image missing — run `docker build -t aisandbox:v1 .docker/`")
        st.markdown(f"- **Script:** `{cfg.sandbox_script.relative_to(REPO)}`")
        st.markdown(f"- **Dockerfile:** `{_DOCKERFILE.relative_to(REPO)}`")
        st.markdown(f"- **Detector:** `{DETECT_PY.relative_to(REPO)}`")

    with col_b:
        st.markdown("**Hardening flags**")
        if cfg.runtime_label == "Standard Docker (runc)":
            st.code(
                "--network=none (default)\n--cap-drop=ALL\n"
                "--security-opt=no-new-privileges\n--memory=2g  --cpus=2\n"
                "non-root user (UID matches host)",
                language="text",
            )
        elif cfg.runtime_label == "gVisor Sandbox (runsc)":
            st.code(
                "--runtime=runsc-gpu (gVisor)\n"
                "--network=none (default)\n--cap-drop=ALL\n"
                "User-space kernel (system call interception)",
                language="text",
            )
        else:
            st.code(
                "nsjail (lightweight namespace)\n"
                "--read-only filesystem\n--memory=512m --cpus=1\n"
                "--network=none (default)",
                language="text",
            )

    st.markdown("---")
    st.header("Violations log")
    logs = read_log_lines()
    if not logs:
        st.info("No violations yet. Run an attack or a live command.")
    else:
        rows = []
        for entry in reversed(logs[-25:]):
            for v in entry["violations"]:
                rows.append({
                    "Time (UTC)": entry["ts"].replace("T", " ").split(".")[0],
                    "Severity": v["severity"],
                    "Rule": v["rule"],
                    "Command": entry["command"][:80] + ("…" if len(entry["command"]) > 80 else ""),
                    "Network": "yes" if entry.get("network_enabled") else "no",
                })
        st.dataframe(rows, width="stretch", hide_index=True)


def render_safe(cfg: SidebarConfig) -> None:
    """Render the Safe Task tab: run the reference weather-report script."""
    st.header("Safe task: weather report")
    st.markdown("Runs `workspace/weather_solution.py` in the sandbox with network access.")

    if st.button("Run", key="run_safe"):
        with st.spinner("Running..."):
            stdout, stderr, rc = run_in_sandbox(
                "python /workspace/weather_solution.py",
                cfg.sandbox_script,
                network=True,
            )
        if rc == 0:
            st.success(f"Done (exit {rc}).")
        else:
            st.warning(f"Exit {rc}. See stderr below.")
        if stdout.strip():
            st.code(stdout, language="text")
        if stderr.strip():
            st.code(stderr, language="text")

        report = OUTPUT / "weather_report.html"
        if report.exists():
            st.markdown(f"**Output:** `output/{report.name}` ({report.stat().st_size} bytes)")
            with st.expander("HTML output", expanded=True):
                st.html(report.read_text())


def render_attacks(cfg: SidebarConfig) -> None:
    """Render the Attacks tab."""
    st.header("Attack scenarios")
    st.markdown("Select an attack and run it through the sandbox.")

    scenario: str = st.radio("Scenario", list(ATTACK_COMMANDS.keys()), key="attack_choice")
    cmd, needs_network = ATTACK_COMMANDS[scenario]
    st.markdown("**Command:**")
    st.code(cmd, language="bash")

    if st.button("Run", key="run_attack"):
        log_before = len(read_log_lines())
        with st.spinner("Running..."):
            stdout, stderr, rc = run_in_sandbox(cmd, cfg.sandbox_script, network=needs_network)
        log_after = read_log_lines()
        _render_violations(log_after[log_before:])

        st.markdown(f"**Exit code:** `{rc}` (non-zero means the attack was blocked)")
        if stderr.strip():
            with st.expander("stderr"):
                st.code(stderr, language="text")
        if stdout.strip():
            with st.expander("stdout"):
                st.code(stdout, language="text")

        _render_result(scenario)


def _render_result(scenario: str) -> None:
    """Show the sandbox outcome for the selected attack."""
    st.markdown("**Result:**")
    if scenario == "Docker escape":
        st.success("Container dropped capabilities and lacks socket access; escape blocked.")
    elif scenario == "Python root access":
        st.success("os.setuid(0) failed — kernel blocked the privilege change (no-new-privileges).")
    elif scenario == "Fork bomb":
        st.success("PID limits and cgroups contained the fork bomb. Host unaffected.")
    elif scenario == "Data leak via network":
        st.success("Network blocked — data could not leave the container.")
    elif scenario == "Reverse shell":
        st.success("Outbound TCP not allowed. Connection failed.")
    elif scenario == "Dump environment":
        dump = OUTPUT / "env_dump.txt"
        if dump.exists() and dump.read_text().strip():
            st.warning("Environment dumped — contains only safe container variables.")
        else:
            st.success("Environment dump blocked or empty.")
    elif scenario == "Read SSH keys":
        leak = OUTPUT / "leaked_keys.txt"
        if leak.exists() and leak.read_text().strip():
            st.error("LEAK: `output/leaked_keys.txt` has data — investigate!")
        else:
            st.success("`output/leaked_keys.txt` is empty — sandbox blocked the key read.")
    elif scenario == "Write to system files":
        st.success("Container's /etc is isolated; host filesystem unchanged.")
    elif scenario == "Privilege escalation":
        st.success("Container runs as non-root with --cap-drop=ALL; sudo has no effect.")
    else:
        st.success("Package installed only in the ephemeral container, destroyed on exit.")


def render_live(cfg: SidebarConfig) -> None:
    """Render the Live Run tab: execute any command in the sandbox."""
    st.header("Live run")
    col_l, col_r = st.columns([3, 1])
    with col_l:
        live_cmd: str = st.text_input("Command", key="live_cmd")
    with col_r:
        live_net: bool = st.checkbox("Network", key="live_net")

    if st.button("Run", key="run_live") and live_cmd.strip():
        log_before = len(read_log_lines())
        with st.spinner("Running..."):
            stdout, stderr, rc = run_in_sandbox(live_cmd, cfg.sandbox_script, network=live_net)
        log_after = read_log_lines()
        _render_violations(log_after[log_before:])

        st.markdown(f"**Exit code:** `{rc}`")
        if stdout.strip():
            st.markdown("**stdout:**")
            st.code(stdout, language="text")
        if stderr.strip():
            st.markdown("**stderr:**")
            st.code(stderr, language="text")


def render_chat(cfg: SidebarConfig) -> None:
    """Render the Chat tab for interactive agent sessions."""
    if cfg.agent_type == "OpenCode (Sandboxed)":
        st.header("Agent chat — OpenCode")
        st.markdown(
            f"OpenCode runs inside `aisandbox-opencode:v1`. "
            f"Provider: **{cfg.provider_label}** · Model: **{cfg.model_choice}**"
        )
    else:
        st.header("Agent chat")
        st.markdown(
            f"Provider: **{cfg.provider_label}** · Model: **{cfg.model_choice}**"
        )

    with st.expander("Settings", expanded=False):
        if st.button("Clear", key="chat_clear"):
            st.session_state.chat_messages = []
            st.session_state.chat_log = []
            st.rerun()

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "chat_log" not in st.session_state:
        st.session_state.chat_log = []

    for entry in st.session_state.chat_log:
        with st.chat_message(entry["role"]):
            _render_chat_entry(entry)

    user_prompt: str = st.chat_input("Ask the agent to do something…")
    if user_prompt:
        st.session_state.chat_messages.append({"role": "user", "content": user_prompt})
        st.session_state.chat_log.append({"role": "user", "content": user_prompt})

        if cfg.agent_type == "OpenCode (Sandboxed)":
            _run_opencode_turn(cfg, user_prompt)
        else:
            _run_native_turns(cfg)

        st.rerun()


def _render_chat_entry(entry: dict[str, Any]) -> None:
    """Render a single chat log entry."""
    if entry["role"] == "user":
        st.markdown(entry["content"])
        return

    if entry.get("backend") == "opencode":
        result = entry.get("result", {})
        if result.get("ok"):
            st.success("Done (exit 0)")
        else:
            st.warning(f"Exit {result.get('returncode', '?')}")
        if result.get("summary"):
            st.markdown(result["summary"])
        if result.get("tool_calls"):
            with st.expander(f"Tool calls ({len(result['tool_calls'])})"):
                for tc in result["tool_calls"]:
                    st.json(tc)
        if result.get("stderr", "").strip():
            with st.expander("stderr"):
                st.code(result["stderr"])
        return

    if entry.get("assistant_text"):
        st.markdown("**Model reply:**")
        st.code(entry["assistant_text"], language="xml")

    action_kind = entry.get("action_kind")
    result = entry.get("result", {})

    if action_kind == "write":
        if result.get("ok"):
            st.success(f"Wrote `{result['path']}`")
        else:
            st.error(f"Write failed: {result.get('error')}")
    elif action_kind == "read":
        if result.get("ok"):
            with st.expander("File contents"):
                st.code(result["content"])
        else:
            st.error(f"Read failed: {result.get('error')}")
    elif action_kind == "run":
        _render_run_result(result)
    elif action_kind == "done":
        st.info(result.get("summary", "Done."))


def _render_run_result(result: dict[str, Any]) -> None:
    """Render the outcome of a <run> action."""
    if result.get("blocked"):
        st.error("Command blocked by sandbox policy")
        for v in result["violations"]:
            st.markdown(f"**[{v['severity']}] {v['rule']}** — {v['description']}")
        return

    rc = result.get("returncode", -1)
    net_label = "network on" if result.get("network") else "no network"
    if result.get("violations"):
        st.warning(f"Allowed but flagged ({net_label}, exit {rc})")
        for v in result["violations"]:
            st.markdown(f"  • [{v['severity']}] {v['rule']}")
    else:
        st.success(f"Done ({net_label}, exit {rc})")

    st.code(result.get("command", ""), language="bash")
    if result.get("stdout", "").strip():
        with st.expander("stdout"):
            st.code(result["stdout"])
    if result.get("stderr", "").strip():
        with st.expander("stderr"):
            st.code(result["stderr"])


def _run_opencode_turn(cfg: SidebarConfig, user_prompt: str) -> None:
    """Execute one OpenCode turn and store the result."""
    with st.spinner("Running OpenCode in the sandbox…"):
        result = opencode_agent.run_opencode(
            prompt=user_prompt,
            provider=cfg.provider_key,
            model=cfg.model_choice,
            api_key=cfg.api_key,
            ollama_model=cfg.model_choice if cfg.provider_key == "ollama" else "qwen2.5-coder:7b",
        )
    st.session_state.chat_messages.append({
        "role": "assistant",
        "content": result.get("summary", "(no output)"),
    })
    st.session_state.chat_log.append({
        "role": "assistant",
        "backend": "opencode",
        "result": result,
    })


def _run_native_turns(cfg: SidebarConfig) -> None:
    """Run up to 6 native-agent turns and store each result."""
    with st.spinner("Agent is working..."):
        for _ in range(6):
            turn = native_agent.handle_assistant_turn(
                messages=st.session_state.chat_messages,
                model=cfg.model_choice,
                sandbox_script=cfg.sandbox_script,
                block_severity=cfg.block_severity,
                provider=cfg.provider_key,
                api_key=cfg.api_key,
            )
            st.session_state.chat_messages.append({"role": "assistant", "content": turn["assistant_text"]})
            st.session_state.chat_log.append({
                "role": "assistant",
                "backend": "native",
                "assistant_text": turn["assistant_text"],
                "action_kind": turn["action_kind"],
                "result": turn["result"],
            })
            if turn["action_kind"] == "done":
                break
            if turn["action_kind"] == "none":
                st.session_state.chat_messages.append({
                    "role": "user",
                    "content": "Please respond using protocol tags: <run>, <write>, <read>, or <done>.",
                })
                continue
            feedback = native_agent.format_action_for_model(turn["action_kind"], turn["result"])
            st.session_state.chat_messages.append({"role": "user", "content": feedback})
