"""Optional shared filters; settings survive page changes."""
import pandas as pd
import streamlit as st
from app_state import clear_controls
from core.catalogue import analysis_table
from core.dashboard import column_groups, finite_mask
from core.data_cleaning import missing_mask


def render_filters(dataset):
    data, settings = dataset["working"], dataset["settings"]
    data = analysis_table(data, settings["mapping"])
    groups = column_groups(data)
    with st.expander("Shared filters", expanded=bool(settings["filters"])):
        st.caption("Cards, charts, findings, Intelligence and reports use these filters together (AND). Range endpoints are included.")
        options = list(data.columns)
        default_cols = [c for c in settings["filters"] if c in data]
        filter_kwargs = {"default": default_cols} if "ui_filter_columns" not in st.session_state else {}
        selected = st.multiselect("Filter columns", options, key="ui_filter_columns", **filter_kwargs)
        rules = {}
        for column in selected:
            previous = settings["filters"].get(column, {})
            missing = st.checkbox(f"Include missing: {column}", value=previous.get("include_missing", False), key=f"ui_missing_{column}")
            if column in groups["text"]:
                values = data.loc[~missing_mask(data[column]), column].unique().tolist()
                picked = st.multiselect(f"Values: {column}", values, default=previous.get("values", values), key=f"ui_values_{column}")
                rules[column] = dict(kind="category", values=picked, include_missing=missing)
            elif column in groups["number"]:
                values = data.loc[finite_mask(data[column]), column]
                if values.empty:
                    st.info(f"{column}: no finite numeric values to filter.")
                    continue
                bounds = previous.get("range", [float(values.min()), float(values.max())])
                left, right = st.columns(2)
                low = left.number_input(f"Minimum: {column}", value=float(bounds[0]), key=f"ui_min_{column}")
                high = right.number_input(f"Maximum: {column}", value=float(bounds[1]), key=f"ui_max_{column}")
                rules[column] = dict(kind="number", range=[low, high], include_missing=missing)
            else:
                values = data[column].dropna()
                if values.empty:
                    st.info(f"{column}: no dates to filter.")
                    continue
                modes = ["Fixed dates", "Last N days of dataset"]
                mode = st.selectbox(f"Date rule: {column}", modes, index=1 if previous.get("mode") == "last_days" else 0, key=f"ui_date_mode_{column}")
                if mode == modes[1]:
                    days = st.number_input(f"Days: {column}", 1, 3660, int(previous.get("days", 30)), key=f"ui_days_{column}")
                    rules[column] = dict(kind="date", mode="last_days", days=days, range=[], include_missing=missing)
                else:
                    bounds = previous.get("range") or [values.min().date(), values.max().date()]
                    dates = st.date_input(f"Date range: {column}", value=tuple(pd.Timestamp(x).date() for x in bounds), key=f"ui_dates_{column}")
                    if len(dates) != 2:
                        st.info("Choose both date endpoints.")
                        return False
                    rules[column] = dict(kind="date", mode="fixed", range=[str(x) for x in dates], include_missing=missing)
        if any(r["kind"] == "number" and r["range"][0] > r["range"][1] for r in rules.values()):
            st.error("The minimum must not exceed the maximum. Fix the range to show analysis.")
            return False
        settings["filters"] = rules
        if st.button("Clear filters"):
            settings["filters"] = {}
            clear_controls(("ui_filter", "ui_missing", "ui_values", "ui_min", "ui_max", "ui_date", "ui_days"))
            st.rerun()
    return True
