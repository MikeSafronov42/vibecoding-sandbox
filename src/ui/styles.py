"""Streamlit CSS injection for the dashboard.

All colors use `inherit` + `opacity` or semi-transparent `rgba()` so the
stylesheet works correctly in both Streamlit's light and dark themes.
"""
import streamlit as st

_CSS = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* ── Page header ───────────────────────────────────────── */
    .page-header {
        border-bottom: 1px solid rgba(128, 128, 128, 0.2);
        padding-bottom: 1.1rem;
        margin-bottom: 1.5rem;
    }
    .page-header h1 {
        font-size: 1.5rem;
        font-weight: 700;
        color: inherit;
        margin: 0 0 0.25rem 0;
        letter-spacing: -0.3px;
    }
    .page-header p {
        color: inherit;
        opacity: 0.55;
        margin: 0;
        font-size: 0.875rem;
    }
    .meta-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem 2rem;
        margin-top: 0.8rem;
        font-size: 0.78rem;
        color: inherit;
    }
    .meta-item {
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }
    .meta-label {
        opacity: 0.4;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.07em;
    }

    /* ── Tabs ──────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        border-bottom: 1px solid rgba(128, 128, 128, 0.2);
        background: transparent;
        padding: 0;
        border-radius: 0;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border-radius: 0;
        padding: 0.55rem 1.1rem;
        color: inherit;
        opacity: 0.5;
        font-weight: 500;
        font-size: 0.875rem;
        border-bottom: 2px solid transparent;
        margin-bottom: -1px;
        transition: opacity 0.15s ease;
    }
    .stTabs [data-baseweb="tab"]:hover {
        opacity: 0.8;
        background: transparent;
    }
    .stTabs [aria-selected="true"] {
        background: transparent !important;
        color: inherit !important;
        opacity: 1 !important;
        border-bottom: 2px solid #4299E1 !important;
    }

    /* ── Buttons ───────────────────────────────────────────── */
    .stButton > button {
        border-radius: 4px;
        font-weight: 500;
        font-size: 0.875rem;
        padding: 0.4rem 1rem;
        border: 1px solid rgba(128, 128, 128, 0.3);
        background: transparent;
        color: inherit;
        transition: background 0.12s ease, border-color 0.12s ease;
    }
    .stButton > button:hover {
        background: rgba(128, 128, 128, 0.1) !important;
        border-color: rgba(128, 128, 128, 0.5) !important;
        color: inherit !important;
    }

    /* ── Code ──────────────────────────────────────────────── */
    pre, code {
        font-family: "SF Mono", "Fira Code", Consolas, monospace !important;
        font-size: 0.82rem !important;
    }

    /* ── Alerts ────────────────────────────────────────────── */
    .stAlert { border-radius: 4px; }

    /* ── Sidebar ───────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        border-right: 1px solid rgba(128, 128, 128, 0.15);
    }
    [data-testid="stSidebar"] h3 {
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.09em;
        color: inherit;
        opacity: 0.4;
        margin-bottom: 0.5rem;
    }

    /* ── Misc ──────────────────────────────────────────────── */
    [data-testid="stDataFrame"] { border-radius: 4px; }
    hr { border: none; border-top: 1px solid rgba(128, 128, 128, 0.18); margin: 1.5rem 0; }
</style>
"""


def apply() -> None:
    """Inject the dashboard CSS into the Streamlit page."""
    st.markdown(_CSS, unsafe_allow_html=True)
