"""Dashboard presentation; calculations come from the shared context."""
import pandas as pd
import streamlit as st
from core.analysis import context
from core.charts import build_figure
from core.insights import findings
from ui.ui_style import scope_strip

METRIC_LABELS = {"total_revenue": "Sales", "total_cost": "Cost of goods", "total_profit": "Gross profit",
                 "profit_margin": "Gross margin", "total_orders": "Orders", "aov": "Average order value", "units_sold": "Units sold"}


def metric_text(value, percent=False):
    if value is None or pd.isna(value):
        return "Unavailable"
    return f"{value:,.1f}%" if percent else f"{value:,.2f}"


def show_metrics(ctx):
    m = ctx["metrics"]
    keys = ["total_revenue", "total_profit", "profit_margin", "total_orders", "units_sold", "aov"]
    labels = {**METRIC_LABELS, "total_profit": m["profit_label"], "profit_margin": m["margin_label"]}
    columns = st.columns(3)
    columns += st.columns(3)
    for area, key in zip(columns, keys):
        label = labels[key]
        value = m[key]
        if key == "total_orders" and value is None:
            label, text = "Records", str(m["total_records"])
        elif key == "total_orders":
            text = f"{value:,}"
        else:
            text = metric_text(value, key == "profit_margin")
        area.metric(label, text, help=m["reasons"][key])
    st.caption(f"{m['currency']} · Sales coverage: {m['usable_records']} / {m['total_records']} records. "
               f"Missing corresponding costs: {m['missing_cost_records']}. Returns/negative sales: {m['return_records']}.")
    for notice in m["notices"]:
        st.warning(notice)
    with st.expander("How calculated · formulas and limitations"):
        st.write(m["revenue_mode"])
        st.write(m["cost_mode"])
        st.write(m["profit_mode"])
        st.write(f"{m['margin_label']} = {m['profit_label']} / positive sales × 100.")
        st.write("Orders = distinct nonblank order IDs. Average order value = revenue / orders, only with full matching coverage.")
        st.write(f"Cost of goods: {metric_text(m['total_cost'])}. Average order value: {metric_text(m['aov'])}.")
        st.caption(m["currency_note"])
        for key in METRIC_LABELS:
            if m[key] is None:
                st.info(f"{labels[key]}: {m['reasons'][key]}")
        st.caption("Figures use the analysis copy and current filters. Exact duplicates remain until you choose to remove them. Gross profit is not net profit.")
        if not ctx["growth"].empty:
            st.write("Revenue growth = (current - previous) / previous × 100.")
            st.dataframe(ctx["growth"], hide_index=True, width="stretch")
        else:
            st.info("Growth unavailable: mapped dates and comparable completed calendar months are required.")


def render_kpis(dataset, ctx=None):
    ctx = ctx or context(dataset)
    scope_strip(ctx)
    if len(ctx["data"].columns) == 0:
        st.info("No supported fields are mapped. Review the 20-field catalogue in Data and correct types in Prepare.")
        return
    if ctx["data"].empty:
        st.info("No records match these filters. Clear or widen the scope.")
        return
    show_metrics(ctx)
    selected = [c for c in dataset["settings"]["charts"] if c.get("enabled", True)]
    width = dataset["settings"].get("layout", 2)
    for offset in range(0, len(selected), width):
        columns = st.columns(width)
        for area, chart in zip(columns, selected[offset:offset+width]):
            with area, st.container(border=True):
                try:
                    fig, _, notes = build_figure(ctx["data"], chart, ctx["settings"]["mapping"], ctx["metrics"]["monetary_ok"])
                    st.plotly_chart(fig, width="stretch", key="plot_"+chart["id"])
                    st.caption(" · ".join(notes))
                except ValueError as error:
                    st.info(f"{chart.get('title', 'Chart')}: {error}")
    if not selected:
        st.info("No selected charts. Add one or restore the automatic layout in Explore.")
    st.subheader("From insight to action")
    for finding in findings(ctx):
        with st.container(border=True):
            st.write(finding["statement"])
            st.caption(finding["evidence"])
            st.write("Suggested action: " + finding["suggestion"])
            st.caption(finding["limitation"])
    st.button("Review findings in Reports", type="primary", on_click=lambda: st.session_state.update(page="Reports"))
