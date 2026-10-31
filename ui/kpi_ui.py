"""Dashboard presentation; calculations come from the shared context."""
from html import escape
import pandas as pd
import streamlit as st
from core.analysis import context
from core.charts import build_figure, PALETTES
from core.insights import findings
from ui.ui_style import scope_strip

METRIC_LABELS = {
    "total_revenue": "Sales",
    "total_cost": "Cost of goods",
    "total_profit": "Gross profit",
    "profit_margin": "Gross margin",
    "total_orders": "Orders",
    "aov": "Average order value",
    "units_sold": "Units sold"
}


def metric_text(value, percent=False):
    if value is None or pd.isna(value):
        return "Unavailable"
    return f"{value:,.1f}%" if percent else f"{value:,.2f}"


def show_metrics(ctx):
    m = ctx["metrics"]
    keys = ["total_revenue", "total_profit", "profit_margin", "total_orders", "units_sold", "aov"]
    labels = {**METRIC_LABELS, "total_profit": m["profit_label"], "profit_margin": m["margin_label"]}
    columns = st.columns(6)
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

    # Compact Coverage & Profit Messaging Bar
    has_supplied_profit_without_cost = (
        m["profit_label"] == "Reported profit" and
        (m["total_cost"] is None or m["missing_cost_records"] > 0)
    )
    if has_supplied_profit_without_cost:
        profit_msg = "Reported profit supplied. Cost data unavailable; calculated gross profit cannot be verified."
    else:
        profit_msg = f"{m['profit_label']} verified against scoped records."

    meta_col1, meta_col2 = st.columns([5, 1])
    with meta_col1:
        st.caption(
            f"ℹ️ {profit_msg} · Coverage: {m['usable_records']:,} / {m['total_records']:,} rows · "
            f"Missing costs: {m['missing_cost_records']:,} · Returns/negatives: {m['return_records']:,} · "
            f"Currency: {m['currency']}"
        )
    with meta_col2:
        with st.popover("📐 How calculated"):
            st.markdown(f"**{m['profit_label']} & Revenue Accounting**")
            st.write(m["revenue_mode"])
            st.write(m["cost_mode"])
            st.write(m["profit_mode"])
            st.write(f"**Margin Formula:** {m['margin_label']} = {m['profit_label']} / positive sales × 100.")
            st.write("**Orders & AOV:** Orders = distinct nonblank order IDs. Average order value = revenue / orders (requires full matching coverage).")
            st.write(f"Total cost: {metric_text(m['total_cost'])}. AOV: {metric_text(m['aov'])}.")
            st.caption(m["currency_note"])
            for key in METRIC_LABELS:
                if m[key] is None:
                    st.info(f"{labels[key]}: {m['reasons'][key]}")
            st.caption("Figures use the analysis copy and current filters. Exact duplicates remain until you choose to remove them. Gross profit is not net profit.")
            if not ctx["growth"].empty:
                st.write("**Revenue Growth (Period over Period):**")
                st.dataframe(ctx["growth"], hide_index=True, width="stretch")
            else:
                st.info("Growth unavailable: mapped dates and comparable completed calendar months are required.")
    for notice in m["notices"]:
        st.warning(notice)


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

    # Interactive Chart Color Palette Chooser Toolbar
    t_left, t_right = st.columns([3, 1])
    with t_right:
        default_pal = dataset["settings"].get("palette", "Vibrant Rainbow")
        current_pal_idx = list(PALETTES.keys()).index(default_pal) if default_pal in PALETTES else 0
        active_palette = st.selectbox(
            "🎨 Chart Color Palette",
            list(PALETTES.keys()),
            index=current_pal_idx,
            key="ui_dashboard_palette_select"
        )
        dataset["settings"]["palette"] = active_palette

    PAGE_SIZE = 4
    if len(selected) > PAGE_SIZE:
        chart_page = st.session_state.get("dashboard_chart_page", 0)
        max_page = (len(selected) - 1) // PAGE_SIZE
        chart_page = min(max(chart_page, 0), max_page)
        st.session_state["dashboard_chart_page"] = chart_page

        p_col1, p_col2, p_col3 = st.columns([4, 1, 1])
        with p_col1:
            st.caption(f"Showing charts {chart_page*PAGE_SIZE + 1}–{min((chart_page+1)*PAGE_SIZE, len(selected))} of {len(selected)} (Page {chart_page + 1} of {max_page + 1})")
        with p_col2:
            if st.button("◀ Prev", key="btn_chart_prev", disabled=chart_page == 0):
                st.session_state["dashboard_chart_page"] = chart_page - 1
                st.rerun()
        with p_col3:
            if st.button("Next ▶", key="btn_chart_next", disabled=chart_page >= max_page):
                st.session_state["dashboard_chart_page"] = chart_page + 1
                st.rerun()
        visible_charts = selected[chart_page * PAGE_SIZE : (chart_page + 1) * PAGE_SIZE]
    else:
        visible_charts = selected

    for offset in range(0, len(visible_charts), width):
        columns = st.columns(width)
        for area, chart in zip(columns, visible_charts[offset:offset+width]):
            with area, st.container(border=True):
                try:
                    # Apply user's selected dashboard palette override if provided
                    chart_render = {**chart, "palette": active_palette} if active_palette else chart
                    fig, _, notes = build_figure(ctx["data"], chart_render, ctx["settings"]["mapping"], ctx["metrics"]["monetary_ok"], height=220)
                    st.plotly_chart(fig, width="stretch", key="plot_"+chart["id"])
                    
                    # Concise summary & accessible chart details
                    excluded_note = next((n for n in notes if n.startswith("Excluded ") and not n.startswith("Excluded 0 ")), None)
                    c_left, c_right = st.columns([3, 1])
                    with c_left:
                        if excluded_note:
                            st.caption(f"⚠️ {excluded_note}")
                        else:
                            st.caption(f"Method: {chart.get('aggregation', 'sum')} aggregation")
                    with c_right:
                        with st.popover("Chart details"):
                            for n in notes:
                                st.caption(f"• {n}")
                except ValueError as error:
                    st.info(f"{chart.get('title', 'Chart')}: {error}")
    if not selected:
        st.info("No selected charts. Add one or restore the automatic layout in Explore.")

    # Compact Finding & Action Highlight Strip
    f_list = findings(ctx)
    if f_list:
        with st.container(border=True):
            f_col1, f_col2 = st.columns([4, 1])
            with f_col1:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:2px;">'
                    f'<span style="background:#E0F2FE;color:#0369A1;font-size:10px;font-weight:700;padding:1px 6px;border-radius:4px;text-transform:uppercase;">Key Finding</span>'
                    f'<span style="font-weight:700;color:#0F172A;font-size:0.88rem;">{escape(f_list[0]["statement"])}</span>'
                    f'</div>'
                    f'<div style="font-size:0.80rem;color:#334155;">'
                    f'<strong style="color:#0F172A;">Action:</strong> {escape(f_list[0]["suggestion"])}'
                    f'</div>',
                    unsafe_allow_html=True
                )
                if len(f_list) > 1:
                    with st.popover(f"All findings ({len(f_list)})"):
                        for idx, f in enumerate(f_list, 1):
                            st.markdown(f"**{idx}. {f['statement']}**")
                            st.caption(f"Evidence: {f['evidence']}")
                            st.write(f"Suggested action: {f['suggestion']}")
                            st.caption(f"Limitation: {f['limitation']}")
                            if idx < len(f_list):
                                st.divider()
            with f_col2:
                st.button(
                    "Review findings in Reports",
                    key="btn_review_findings_reports",
                    type="primary",
                    width="stretch",
                    on_click=lambda: st.session_state.update(page="Reports")
                )
