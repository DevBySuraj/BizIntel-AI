"""Chart customization and ordering; templates save specifications."""
from copy import deepcopy
import streamlit as st
from core.analysis import context
from core.catalogue import analysis_table
from core.charts import KINDS, PALETTES, spec, suggestions, build_figure
from core.dashboard import column_groups
from ui.template_ui import render_templates
from ui.ui_style import scope_strip
from app_state import clear_controls


def render_dashboard(dataset, ctx=None):
    ctx = ctx or context(dataset)
    scope_strip(ctx)
    settings = dataset["settings"]
    st.caption("All previews use the shared dashboard filters. A saved chart stores its settings, not old plotted values.")
    layout_kwargs = {"index": settings["layout"] - 1} if "ui_layout" not in st.session_state else {}
    settings["layout"] = st.radio("Dashboard columns", [1, 2], horizontal=True, key="ui_layout", **layout_kwargs)
    if st.button("Restore automatic layout"):
        settings["charts"] = suggestions(dataset["working"], settings["mapping"], ctx["metrics"]["monetary_ok"])
        clear_controls()
        st.rerun()
    charts = settings["charts"]
    names = {c["id"]: c.get("title") or c["kind"] for c in charts}
    chosen = st.selectbox("Edit chart", [None] + list(names), format_func=lambda x: names.get(x, "Create a new chart"), key="ui_edit_chart")
    original = next((c for c in charts if c["id"] == chosen), None)
    supported = analysis_table(dataset["working"], settings["mapping"])
    columns = list(supported.columns)
    if not columns:
        st.info("No supported fields are mapped. Review the catalogue in Data and prepare compatible types.")
        return
    groups = column_groups(supported)
    numeric = groups["number"] + (["@revenue"] if ctx["metrics"]["total_revenue"] is not None else [])
    initial = original or spec("Bar", columns[0], title="My chart", aggregation="count")
    # The chart ID namespaces editor widgets so switching charts loads its own settings.
    suffix = chosen or "new"
    def select(label, options, value, name):
        return st.selectbox(label, options, index=options.index(value) if value in options else 0, key=f"ui_chart_{suffix}_{name}")
    with st.container(border=True):
        kind = select("Chart type", KINDS, initial["kind"], "kind")
        st.caption({"Bar":"Compare categories using counts, sums, or means.",
                    "Line":"Show ordered changes; missing intervals are not zero.",
                    "Histogram":"Inspect the distribution of a numeric measure.",
                    "Scatter":"Compare paired numeric values; association is not causation.",
                    "Box":"Compare medians and spread; extreme values are not automatically errors."}[kind])
        x_options = groups["number"] if kind in ("Histogram", "Scatter") else columns
        if not x_options:
            st.info("This chart needs a numeric column. Choose another chart type or prepare your data.")
            return
        x = select("Horizontal axis", x_options, initial["x"], "x")
        aggregation = select("Aggregation", ["sum","mean","count"], initial["aggregation"], "agg") if kind in ("Bar", "Line") else "count"
        needs_y = kind in ("Scatter", "Box") or (kind in ("Bar", "Line") and aggregation != "count")
        y = select("Vertical measure", [None]+numeric, initial.get("y"), "y") if needs_y else None
        group = select("Group / color", [None]+groups["text"], initial.get("group"), "group")
        title = st.text_input("Chart title", value=initial["title"], key=f"ui_chart_{suffix}_title", max_chars=150)
        a,b = st.columns(2)
        x_label = a.text_input("Horizontal label", value=initial.get("x_label",""), key=f"ui_chart_{suffix}_xl")
        y_label = b.text_input("Vertical label", value=initial.get("y_label",""), key=f"ui_chart_{suffix}_yl")
        palette = select("Palette", list(PALETTES), initial["palette"], "palette")
        sort, top_n, labels = initial["sort"], initial["top_n"], False
        if kind == "Bar":
            sort = select("Bar sort order", ["Descending","Ascending","Alphabetical"], initial["sort"], "sort")
            top_n = st.number_input("Maximum bar categories", 1, 50, int(initial["top_n"]), key=f"ui_chart_{suffix}_top")
            labels = st.checkbox("Show bar values", initial["labels"], key=f"ui_chart_{suffix}_labels")
        edited = {**initial, "kind":kind, "x":x, "y":y, "aggregation":aggregation, "group":group,
                  "title":title, "x_label":x_label, "y_label":y_label, "palette":palette, "sort":sort,
                  "top_n":top_n, "labels":labels}
        try:
            figure, table, notes = build_figure(ctx["data"], edited, settings["mapping"], ctx["metrics"]["monetary_ok"])
        except (ValueError, TypeError) as error:
            st.info(str(error))
        else:
            st.plotly_chart(figure, width="stretch", key="editor_preview")
            st.caption(" · ".join(notes))
            with st.expander("Chart data"):
                st.dataframe(table, hide_index=True, width="stretch")
            if st.button("Save chart to dashboard", type="primary"):
                if chosen:
                    charts[charts.index(original)] = deepcopy(edited)
                else:
                    charts.append(deepcopy(edited))
                clear_controls(("ui_chart_", "ui_edit_chart"))
                st.rerun()
    st.subheader("Dashboard chart selection and order")
    for index, chart in enumerate(charts):
        a,b,c,d = st.columns([7,1,1,1])
        chart["enabled"] = a.checkbox(chart["title"] or chart["kind"], chart.get("enabled",True), key="ui_include_"+chart["id"])
        if b.button("↑", key="up_"+chart["id"], disabled=index==0, help="Move chart up"):
            charts[index-1], charts[index] = charts[index], charts[index-1]
            st.rerun()
        if c.button("↓", key="down_"+chart["id"], disabled=index==len(charts)-1, help="Move chart down"):
            charts[index+1], charts[index] = charts[index], charts[index+1]
            st.rerun()
        if d.button("Remove", key="remove_"+chart["id"]):
            charts.pop(index)
            clear_controls(("ui_edit_chart",))
            st.rerun()
    render_templates(dataset)
