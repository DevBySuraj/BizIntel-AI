"""BizIntel AI: a small, navigable analytics workspace."""

import streamlit as st

from app_state import preserve_controls
from ui.cleaning_ui import render_cleaning
from ui.dashboard_ui import render_dashboard
from ui.data_ui import render_data
from ui.forecasting_ui import render_forecasting
from ui.kpi_ui import render_kpis
from ui.reports_ui import render_reports
from ui.ui_controls import render_filters
from core.analysis import context
from ui.ui_style import apply_style, page_header, sidebar

st.set_page_config(page_title="BizIntel AI", page_icon="📊", layout="wide")
preserve_controls()
apply_style()
page = sidebar(dashboard_ready=True, intelligence_ready=True)
page_header(page)
dataset = st.session_state.get("dataset")

if page == "Data":
    render_data()
elif dataset is None:
    st.info("Choose a dataset in Data to use this module.")
elif page == "Prepare":
    render_cleaning(dataset["original"], dataset["source_id"])
else:
    if render_filters(dataset):
        try:
            ctx = context(dataset)
        except (ValueError, TypeError) as error:
            st.error(f"This scope cannot be analyzed: {error}")
        else:
            if page == "Explore":
                render_dashboard(dataset, ctx)
            elif page == "Dashboard":
                render_kpis(dataset, ctx)
            elif page == "Intelligence":
                render_forecasting(dataset, ctx)
            elif page == "Reports":
                render_reports(dataset, ctx)
