"""Small shared visual shell, using native Streamlit controls."""
from html import escape
import streamlit as st
from app_state import navigate

# Canonical Design System Constants
COLOR_BG = "#F4F7FB"
COLOR_CARD = "#FFFFFF"
COLOR_SIDEBAR = "#102A43"
COLOR_MAIN_TEXT = "#0F172A"
COLOR_BODY_TEXT = "#1E293B"
COLOR_SUPPORTING_TEXT = "#334155"
COLOR_PRIMARY = "#087F8C"
COLOR_PRIMARY_HOVER = "#066672"
COLOR_SECONDARY = "#2563EB"
COLOR_BORDER = "#CBD5E1"

PAGES = {
    "Data": ("database", "Your data, understood", "Upload once. Get useful analysis automatically."),
    "Prepare": ("tune", "Prepare with confidence", "Inspect quality, preview changes, keep the original."),
    "Explore": ("bar_chart", "Make the dashboard yours", "Choose the question. Customize the view. Save it for next time."),
    "Dashboard": ("dashboard", "Business dashboard", "Understand performance. Decide what to investigate next."),
    "Intelligence": ("lightbulb", "Look beyond the dashboard", "Understand predictions, customer groups, and unusual records."),
    "Reports": ("description", "From insight to action", "Review the evidence. Add your interpretation. Share a report."),
}


def apply_style():
    st.markdown(f"""<style>
    /* Global Base */
    .stApp {{
        background: {COLOR_BG};
        color: {COLOR_MAIN_TEXT};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    .block-container {{
        max-width: 1440px;
        padding-top: 0.75rem;
        padding-bottom: 1rem;
        padding-left: 1.25rem;
        padding-right: 1.25rem;
    }}

    /* Typography Hierarchy - Deep, Sharp, 100% Readable */
    h1, h2, h3, h4, h5, h6 {{
        color: {COLOR_MAIN_TEXT} !important;
        letter-spacing: -0.02em;
        font-weight: 700 !important;
    }}
    h1 {{ font-size: 1.35rem; line-height: 1.2; margin-bottom: 0.2rem; }}
    h2 {{ font-size: 1.15rem; line-height: 1.25; margin-top: 0.4rem; margin-bottom: 0.2rem; }}
    h3 {{ font-size: 1.0rem; line-height: 1.3; margin-top: 0.3rem; margin-bottom: 0.15rem; }}
    
    .block-container p, 
    .block-container span, 
    .block-container label,
    .block-container li {{
        color: {COLOR_BODY_TEXT} !important;
        font-size: 0.92rem;
    }}
    
    /* Captions & Supporting Text - High Contrast Slate, Never Faint */
    .caption, 
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p,
    .stCaption {{
        color: {COLOR_SUPPORTING_TEXT} !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
    }}

    /* Deep Navy Sidebar with Crystal-Clear Light Navigation Text */
    [data-testid="stSidebar"] {{
        background: {COLOR_SIDEBAR} !important;
    }}
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] strong {{
        color: #FFFFFF !important;
    }}
    [data-testid="stSidebar"] [data-testid="stMarkdown"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] caption {{
        color: #E2E8F0 !important;
    }}
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
    [data-testid="stSidebar"] small {{
        color: #CBD5E1 !important;
    }}

    /* Sidebar Navigation Buttons - Explicit High-Contrast Text Fix */
    [data-testid="stSidebar"] [data-testid="stButton"] button {{
        width: 100%;
        justify-content: flex-start;
        min-height: 40px;
        border-radius: 6px;
        font-size: 0.92rem !important;
        transition: all 0.15s ease;
    }}
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"],
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"] p,
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"] span,
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"] div,
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"] i {{
        background: transparent !important;
        color: #F1F5F9 !important; /* Crisp pure light slate text */
        font-weight: 600 !important;
        border-color: transparent !important;
    }}
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"]:hover,
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"]:hover p,
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"]:hover span,
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"]:hover div {{
        background: #1E3A5F !important;
        color: #FFFFFF !important;
    }}
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"],
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] p,
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] span,
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] div {{
        background: {COLOR_PRIMARY} !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border: 1px solid {COLOR_PRIMARY} !important;
        box-shadow: 0 1px 4px rgba(8, 127, 140, 0.4) !important;
    }}

    /* Metric Cards - Non-Truncating, High Contrast & Compact */
    [data-testid="stMetric"] {{
        background: {COLOR_CARD} !important;
        border: 1px solid {COLOR_BORDER} !important;
        border-radius: 6px !important;
        padding: 6px 10px !important;
        min-height: 56px !important;
        box-shadow: 0 1px 2px rgba(16, 42, 67, 0.04) !important;
    }}
    [data-testid="stMetric"]:hover {{
        border-color: #94A3B8 !important;
    }}
    [data-testid="stMetricLabel"],
    [data-testid="stMetricLabel"] p,
    [data-testid="stMetricLabel"] span,
    [data-testid="stMetricLabel"] div {{
        font-size: 0.72rem !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        color: {COLOR_SUPPORTING_TEXT} !important;
        white-space: normal !important;
        word-break: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        line-height: 1.2 !important;
        min-height: 1.7rem !important;
        display: flex !important;
        align-items: flex-end !important;
    }}
    [data-testid="stMetricValue"],
    [data-testid="stMetricValue"] div {{
        font-size: 1.35rem !important;
        font-weight: 800 !important;
        color: {COLOR_MAIN_TEXT} !important;
        line-height: 1.15 !important;
    }}

    /* Content Containers & Cards */
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background: {COLOR_CARD} !important;
        border: 1px solid {COLOR_BORDER} !important;
        border-radius: 6px !important;
        box-shadow: 0 1px 2px rgba(16, 42, 67, 0.03) !important;
    }}

    /* Buttons with Solid High Contrast */
    button[kind="primary"],
    button[kind="primary"] p,
    button[kind="primary"] span,
    button[kind="primary"] div {{
        background: {COLOR_PRIMARY} !important;
        border-color: {COLOR_PRIMARY} !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
    }}
    button[kind="primary"]:hover {{
        background: {COLOR_PRIMARY_HOVER} !important;
        border-color: {COLOR_PRIMARY_HOVER} !important;
    }}
    button[kind="secondary"],
    button[kind="secondary"] p,
    button[kind="secondary"] span,
    button[kind="secondary"] div {{
        background: {COLOR_CARD} !important;
        border: 1px solid {COLOR_BORDER} !important;
        color: {COLOR_MAIN_TEXT} !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
    }}
    button[kind="secondary"]:hover {{
        background: #F1F5F9 !important;
        border-color: #94A3B8 !important;
        color: {COLOR_MAIN_TEXT} !important;
    }}

    /* Data Tables & Dataframes */
    [data-testid="stDataFrame"], [data-testid="stTable"] {{
        color: {COLOR_MAIN_TEXT} !important;
    }}
    [data-testid="stTable"] th {{
        background-color: #F1F5F9 !important;
        color: {COLOR_MAIN_TEXT} !important;
        font-weight: 700 !important;
    }}
    [data-testid="stTable"] td {{
        color: {COLOR_BODY_TEXT} !important;
        font-weight: 500 !important;
    }}

    /* Form & Input Labels */
    [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] label,
    [data-testid="stWidgetLabel"] span {{
        color: {COLOR_MAIN_TEXT} !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
    }}

    /* Tabs Styling */
    [data-testid="stTabs"] button,
    [data-testid="stTabs"] button p,
    [data-testid="stTabs"] button span {{
        font-size: 0.88rem !important;
        font-weight: 600 !important;
        color: {COLOR_SUPPORTING_TEXT} !important;
    }}
    [data-testid="stTabs"] button[aria-selected="true"],
    [data-testid="stTabs"] button[aria-selected="true"] p,
    [data-testid="stTabs"] button[aria-selected="true"] span {{
        color: {COLOR_PRIMARY} !important;
        border-bottom-color: {COLOR_PRIMARY} !important;
        font-weight: 700 !important;
    }}

    /* Alerts */
    [data-testid="stAlert"] p,
    [data-testid="stAlert"] div {{
        color: {COLOR_MAIN_TEXT} !important;
        font-weight: 500 !important;
    }}

    /* Brand & Compact Shell */
    .brand {{
        font-size: 20px;
        font-weight: 750;
        color: #FFFFFF;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 2px;
    }}
    .brand span {{
        color: #38BDF8;
        font-size: 22px;
    }}
    .page-header-container {{
        height: 28px;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
    }}
    .eyebrow {{
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: {COLOR_PRIMARY};
    }}
    .header-title-row {{
        display: flex;
        align-items: baseline;
        gap: 10px;
        flex-wrap: wrap;
    }}
    .header-title {{
        font-size: 1.3rem !important;
        font-weight: 700 !important;
        color: {COLOR_MAIN_TEXT} !important;
        margin: 0 !important;
        line-height: 1.2 !important;
    }}
    .header-subtitle {{
        font-size: 0.82rem;
        color: {COLOR_SUPPORTING_TEXT};
        margin: 0;
    }}
    .scope-bar {{
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 8px;
        background: {COLOR_CARD};
        border: 1px solid {COLOR_BORDER};
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 11px;
        color: {COLOR_SUPPORTING_TEXT};
        margin-bottom: 6px;
        box-shadow: 0 1px 2px rgba(16, 42, 67, 0.02);
    }}
    .scope-pill {{
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }}
    .scope-pill-strong {{
        font-weight: 700;
        color: {COLOR_MAIN_TEXT};
    }}
    .scope-sep {{
        color: {COLOR_BORDER};
    }}
    .scope-tag {{
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 700;
    }}

    /* Responsive adjustments */
    @media (max-width: 768px) {{
        .block-container {{
            padding: 0.75rem 0.5rem 1rem;
        }}
        [data-testid="stHorizontalBlock"] {{
            flex-wrap: wrap !important;
        }}
        [data-testid="stColumn"] {{
            min-width: 140px;
            flex: 1 1 100% !important;
            margin-bottom: 6px;
        }}
    }}
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
            st.write(f"**{dataset['name']}**")
            st.caption(f"Analysis copy · v{dataset['revision']}\n\n{len(dataset['working']):,} records · {len(dataset['working'].columns)} columns")
            st.button("Change dataset", on_click=navigate, args=("Data",), width="stretch")
        else:
            st.caption("No dataset selected")
        st.caption("Local workspace · no paid AI service\n\nSuggestions only. You make the decisions.")
    return page


def page_header(page):
    _, title, subtitle = PAGES[page]
    st.markdown(
        f'<div class="page-header-container">'
        f'<div class="header-title-row">'
        f'<span class="eyebrow">BIZINTEL AI &nbsp;·&nbsp; {escape(page.upper())}</span>'
        f'<h1 class="header-title">{escape(title)}</h1>'
        f'<span class="header-subtitle">{escape(subtitle)}</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True
    )


def scope_strip(ctx):
    s = ctx["scope"]
    filters_count = len(s["filters"])
    filter_html = (
        f'<span class="scope-tag" style="background:#E0F2FE;color:#0369A1;">⚡ {filters_count} Active Filter{"s" if filters_count > 1 else ""}</span>'
        if filters_count else
        '<span class="scope-tag" style="background:#F1F5F9;color:#334155;">No Filters Active</span>'
    )
    st.markdown(
        f'<div class="scope-bar">'
        f'<span class="scope-pill"><span class="scope-pill-strong">Dataset:</span> {escape(s["dataset"])}</span>'
        f'<span class="scope-sep">•</span>'
        f'<span class="scope-pill"><span class="scope-pill-strong">Version:</span> v{s["version"]}</span>'
        f'<span class="scope-sep">•</span>'
        f'<span class="scope-pill"><span class="scope-pill-strong">Scope:</span> {s["rows"]:,} of {s["total_rows"]:,} rows</span>'
        f'<span class="scope-sep">•</span>'
        f'<span class="scope-pill"><span class="scope-pill-strong">Currency:</span> {escape(s["currency"])}</span>'
        f'<span class="scope-sep">•</span>'
        f'{filter_html}'
        f'</div>',
        unsafe_allow_html=True
    )
    if s["filters"]:
        with st.expander("View active filter parameters", expanded=False):
            st.json(s["filters"])
