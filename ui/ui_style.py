"""Small shared visual shell, using native Streamlit controls."""
from html import escape
import streamlit as st
from app_state import navigate

PAGES = {
    "Data": ("database", "Your data, understood", "Upload once. Get useful analysis automatically."),
    "Prepare": ("tune", "Prepare with confidence", "Inspect quality, preview changes, keep the original."),
    "Explore": ("bar_chart", "Make the dashboard yours", "Choose the question. Customize the view. Save it for next time."),
    "Dashboard": ("dashboard", "Business dashboard", "Understand performance. Decide what to investigate next."),
    "Intelligence": ("lightbulb", "Look beyond the dashboard", "Understand predictions, customer groups, and unusual records."),
    "Reports": ("description", "From insight to action", "Review the evidence. Add your interpretation. Share a report."),
}


def apply_style():
    st.markdown("""<style>
    .stApp {background:#F5F7FB}
    .block-container {max-width:1440px;padding-top:4rem;padding-bottom:3rem}
    h1,h2,h3 {color:#10243A;letter-spacing:-.025em}
    [data-testid="stSidebar"] {background:#10243A}
    [data-testid="stSidebar"] h2,[data-testid="stSidebar"] p {color:#E8EFF6}
    [data-testid="stSidebar"] [data-testid="stButton"] button {width:100%;justify-content:flex-start;min-height:46px}
    [data-testid="stSidebar"] button[kind="secondary"] {background:transparent;color:#D4DFEB;border-color:transparent}
    [data-testid="stSidebar"] button[kind="primary"] {background:#174D60;color:#8BF0E6;border-color:#2FC5C5}
    [data-testid="stMetric"] {background:white;border:1px solid #DFE6EE;border-radius:9px;padding:18px}
    [data-testid="stMetricValue"] {font-size:1.8rem;color:#10243A}
    [data-testid="stVerticalBlockBorderWrapper"] {background:white;border-radius:9px}
    button[kind="primary"] {background:#087F8C;border-color:#087F8C;color:white}
    .brand {font-size:27px;font-weight:750;color:white;margin-bottom:4px}
    .brand span {color:#34D4C6}
    .scope {background:#E7F3F4;border:1px solid #C6E1E4;padding:10px 16px;border-radius:6px;color:#245967}
    .eyebrow {font-size:13px;color:#597087;margin-bottom:14px}
    @media(max-width:700px) {
      .block-container {padding:4rem 1rem 1.3rem}
      [data-testid="stHorizontalBlock"] {flex-wrap:wrap}
      [data-testid="stColumn"] {min-width:240px;flex:1 1 100%}
    }
    </style>""", unsafe_allow_html=True)


def sidebar(**kwargs):
    page = st.session_state.get("page", "Data")
    with st.sidebar:
        st.markdown('<div class="brand"><span>▥</span> BizIntel AI</div>', unsafe_allow_html=True)
        st.caption("BUSINESS ANALYTICS WORKSPACE")
        st.divider()
        for name, (icon, _, _) in PAGES.items():
            st.button(name, key=f"nav_{name}", icon=f":material/{icon}:",
                      type="primary" if page == name else "secondary",
                      on_click=navigate, args=(name,), width="stretch")
        st.divider()
        dataset = st.session_state.get("dataset")
        if dataset:
            st.write(dataset["name"])
            st.caption(f"Analysis copy · v{dataset['revision']}\n\n{len(dataset['working']):,} records · {len(dataset['working'].columns)} columns")
            st.button("Change dataset", on_click=navigate, args=("Data",), width="stretch")
        else:
            st.caption("No dataset selected")
        st.caption("Local workspace · no paid AI service\n\nSuggestions only. You make the decisions.")
    return page


def page_header(page):
    _, title, subtitle = PAGES[page]
    st.markdown(f'<div class="eyebrow">WORKSPACE &nbsp; / &nbsp; {escape(page.upper())}</div>', unsafe_allow_html=True)
    st.title(title)
    st.write(subtitle)


def scope_strip(ctx):
    s = ctx["scope"]
    st.markdown(f'<div class="scope">{escape(s["dataset"])} · v{s["version"]} · '
                f'{s["rows"]:,} of {s["total_rows"]:,} records · {escape(s["currency"])} · shared dashboard scope</div>',
                unsafe_allow_html=True)
    if s["filters"]:
        with st.expander("Active filter details"):
            st.json(s["filters"])
