"""AI Coding Agent Sandbox — dashboard entry point.

Run with: streamlit run demo_app.py
"""
import datetime

import streamlit as st

from src.ui import sidebar as sidebar_module
from src.ui import styles
from src.ui import tabs

st.set_page_config(
    page_title="AI Sandbox",
    layout="wide",
    initial_sidebar_state="expanded",
)

styles.apply()
cfg = sidebar_module.render()

_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
st.markdown(f"""
<div class="page-header">
    <h1>AI Coding Agent Sandbox</h1>
    <p>Docker-based safe execution with violation detection</p>
    <div class="meta-row">
        <span class="meta-item"><span class="meta-label">Runtime</span> {cfg.runtime_label}</span>
        <span class="meta-item"><span class="meta-label">Agent</span> {cfg.agent_type}</span>
        <span class="meta-item"><span class="meta-label">Model</span> {cfg.provider_label} / {cfg.model_choice}</span>
        <span class="meta-item"><span class="meta-label">Session</span> {_now}</span>
    </div>
</div>
""", unsafe_allow_html=True)

tab_overview, tab_safe, tab_attacks, tab_live, tab_chat = st.tabs(
    ["Overview", "Safe Task", "Attacks", "Live Run", "Chat"]
)

with tab_overview:
    tabs.render_overview(cfg)
with tab_safe:
    tabs.render_safe(cfg)
with tab_attacks:
    tabs.render_attacks(cfg)
with tab_live:
    tabs.render_live(cfg)
with tab_chat:
    tabs.render_chat(cfg)
