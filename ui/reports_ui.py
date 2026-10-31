"""Review findings and proposed actions before exporting a scoped snapshot."""
from hashlib import sha256
import json
import streamlit as st
from core.insights import findings
from core.intelligence import forecast, segmentation, anomalies
from core.reports import assemble_report, report_sections, csv_bytes, html_bytes, pdf_bytes
from ui.ui_style import scope_strip
from app_state import clear_controls
from core.catalogue import check_measure


def method_notes(ctx, selected):
    notes = []
    models = ctx["settings"]["models"]
    for name in selected:
        try:
            if name == "Forecasting":
                result = forecast(ctx, models["frequency"], models["horizon"], models.get("target"))
                notes.append("Forecasting: " + result["notes"])
                notes.append(result["comparison"].to_string(index=False))
                notes.append(f"Frequency: {models['frequency']}; future horizon: {models['horizon']}; target: {models.get('target') or 'Mapped revenue'}.")
            elif name == "Customer segmentation":
                result = segmentation(ctx, models["clusters"])
                notes.append("Customer segmentation: " + result["notes"])
                notes.append(result["reason"] or result["profiles"].to_string(index=False))
                notes.append(f"Silhouette separation diagnostic: {result['silhouette']}")
            else:
                column = models.get("anomaly_column")
                check_measure(column, ctx["settings"]["mapping"], ctx["metrics"]["monetary_ok"])
                result = anomalies(ctx["data"], column, models["iqr_multiplier"])
                notes.append(f"Anomalies: {column}; {len(result['flagged'])} flags; bounds {result['lower']} to {result['upper']}. " + result["notes"])
        except ValueError as error:
            notes.append(f"{name} unavailable: {error}")
    return notes


def render_reports(dataset, ctx):
    scope_strip(ctx)
    if len(ctx["data"].columns) == 0:
        st.info("No supported fields are mapped. Review the catalogue in Data before building a business report.")
        return
    scope_id = ctx["scope"]["id"]
    draft = st.session_state.setdefault("report_draft", {"scope": scope_id})
    if draft["scope"] != scope_id:
        st.warning("The dataset or analysis settings changed. Your previous report is an outdated draft; review the new scope before exporting.")
        with st.expander("Previous interpretation (outdated)"):
            st.text(draft.get("interpretation", "No interpretation entered."))
        if st.button("Start fresh report for current scope", type="primary"):
            st.session_state["report_draft"] = {"scope": scope_id}
            st.session_state.pop("report_files", None)
            clear_controls(("ui_report_",))
            st.rerun()
        return
    if ctx["data"].empty:
        st.info("No records in this scope. Adjust filters before building a report.")
        return
    preferences = dataset["settings"]["report"]
    title = st.text_input("Report title", preferences.get("title", "Business performance review"), max_chars=150, key="ui_report_title")
    available = findings(ctx)
    selected, actions = [], {}
    st.subheader("Findings and business actions")
    for finding in available:
        with st.container(border=True):
            include = st.checkbox(finding["statement"], finding["kind"] in preferences.get("finding_kinds", [f["kind"] for f in available]), key="ui_report_find_"+finding["id"])
            st.caption("Calculated evidence: " + finding["evidence"])
            st.caption(finding["limitation"])
            status = st.selectbox("Action review", ["Suggested", "Accepted", "Edited", "Rejected"], key="ui_report_status_"+finding["id"])
            action = st.text_area("Suggested action / your revised action", finding["suggestion"], max_chars=2000, key="ui_report_action_"+finding["id"])
            if action != finding["suggestion"] and status == "Suggested":
                status = "Edited"
            actions[finding["id"]] = {"status": status, "text": action}
            if include:
                selected.append(finding["id"])
    chart_names = {c["id"]: c["title"] for c in ctx["settings"]["charts"]}
    default_charts = preferences.get("chart_ids", [c["id"] for c in ctx["settings"]["charts"] if c.get("enabled", True)])
    chart_ids = st.multiselect("Supporting charts", list(chart_names), default=[c for c in default_charts if c in chart_names],
                               format_func=lambda x: chart_names[x], key="ui_report_charts")
    methods = st.multiselect("Include current method results", ["Forecasting", "Customer segmentation", "Anomalies"], default=preferences.get("methods", []), key="ui_report_methods")
    dataset["settings"]["report"] = {"title": title, "chart_ids": chart_ids, "methods": methods,
                                     "finding_kinds": [f["kind"] for f in available if f["id"] in selected]}
    interpretation = st.text_area("Your final interpretation", max_chars=5000, key="ui_report_interpretation",
                                  help="Keep your judgment separate from calculated findings and suggestions.")
    draft["interpretation"] = interpretation
    report = assemble_report(ctx, title, selected, chart_ids, actions, interpretation, method_notes(ctx, methods))
    with st.expander("Preview report", expanded=False):
        st.subheader(report["title"])
        for heading, paragraphs in report_sections(report):
            st.write(heading)
            for paragraph in paragraphs:
                st.text(paragraph)
        for index, chart in enumerate(report["charts"]):
            st.plotly_chart(chart["figure"], width="stretch", key=f"report_chart_{index}")
            st.caption(chart["notes"])
    safe = st.checkbox("Protect spreadsheet downloads from text formulas", True, key="ui_report_safe")
    st.caption("Prefixes risky text with an apostrophe in the download only. Numeric negatives remain numbers. CSV contains the prepared, filtered records in this report scope.")
    st.download_button("Download scoped cleaned CSV", csv_bytes(ctx["source_data"], safe), "bizintel_cleaned.csv", "text/csv")
    signature = sha256(json.dumps([scope_id, title, selected, chart_ids, actions, interpretation, methods], sort_keys=True).encode()).hexdigest()
    if st.button("Prepare HTML and PDF downloads", type="primary"):
        files = {"signature": signature, "html": html_bytes(report)}
        with st.spinner("Rendering report charts and PDF…"):
            try:
                files["pdf"] = pdf_bytes(report)
            except Exception as error:
                # Export boundary: HTML/CSV remain usable if the renderer fails.
                files["error"] = f"PDF export failed: {error}. HTML and CSV are available. PDF charts need Chrome or Chromium."
        st.session_state["report_files"] = files
    files = st.session_state.get("report_files", {})
    if files.get("signature") == signature:
        if files.get("error"):
            st.error(files["error"])
        st.download_button("Download HTML report", files["html"], "bizintel_report.html", "text/html")
        if files.get("pdf"):
            st.download_button("Download PDF report", files["pdf"], "bizintel_report.pdf", "application/pdf")
    elif files:
        st.info("Report choices changed. Prepare fresh downloads to match this preview.")
