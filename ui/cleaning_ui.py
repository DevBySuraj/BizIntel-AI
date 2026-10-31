"""Preview each preparation operation before applying it to a copy."""
import pandas as pd
import streamlit as st
from app_state import mark_data_changed
from core.automation import interpret, detect_roles
from core.charts import suggestions
from core.data_cleaning import ACTIONS, DATE_FORMATS, apply_cleaning, profile_data, quality_summary


def render_cleaning(original, source_id):
    ds = st.session_state["dataset"]
    data = ds["working"]
    st.caption("Automatic interpretation changes types only. Cleaning requires your choice. Literal NA/null codes are retained.")
    st.dataframe(pd.DataFrame({"Original": quality_summary(ds["original"]), "Working": quality_summary(data)}), width="stretch")
    st.dataframe(profile_data(data), hide_index=True, width="stretch")
    with st.container(border=True):
        st.subheader("Preview a preparation action")
        action = st.selectbox("Action", ACTIONS, key="ui_clean_action")
        columns = []
        value, fmt = "", "%Y-%m-%d"
        if action == "Drop rows with missing values":
            columns = st.multiselect("Check these columns", list(data.columns), key="ui_clean_columns")
        elif action != "Remove duplicate rows":
            column = st.selectbox("Column", list(data.columns), key="ui_clean_column")
            columns = [column]
        if action == "Fill missing values":
            value = st.text_input("Replacement value", key="ui_clean_fill")
        if action in ("Convert to date", "Fill missing values"):
            fmt = DATE_FORMATS[st.selectbox("Date format", list(DATE_FORMATS), key="ui_clean_date")]
        rule = dict(action=action, columns=columns, fill_value=value, date_format=fmt)
        try:
            preview = apply_cleaning(data, **rule)
        except ValueError as error:
            st.info(str(error))
        else:
            removed = data.index.difference(preview.index)
            common = data.index.intersection(preview.index)
            changed = pd.Series(False, index=data.index)
            changed.loc[removed] = True
            cells_changed = 0
            for name in columns:
                before_values, after_values = data.loc[common, name], preview.loc[common, name]
                equal = (before_values.eq(after_values) | (before_values.isna() & after_values.isna())).fillna(False)
                cells_changed += int((~equal).sum())
                changed.loc[common] |= ~equal
            sample_rows = changed[changed].index[:10] if changed.any() else data.index[:10]
            st.caption(f"Before: {len(data)} records. After: {len(preview)}. Removed records: {len(removed)}. Changed cells in retained rows: {cells_changed}. Original data remains intact.")
            left, right = st.columns(2)
            left.write("Before · affected records first")
            left.dataframe(data.loc[sample_rows, columns or list(data.columns)], width="stretch")
            right.write("After · retained records from this preview")
            right.dataframe(preview.loc[sample_rows.intersection(preview.index), columns or list(preview.columns)], width="stretch")
            st.write("New types: " + ", ".join(f"{c}: {preview[c].dtype}" for c in columns))
            if st.button("Apply previewed action", type="primary", key="clean_apply"):
                ds["working"] = preview
                ds["settings"]["cleaning_rules"].append(rule)
                ds["history"].append({"Action": action, "Columns": ", ".join(columns), "Before": len(data), "After": len(preview)})
                detected, _ = detect_roles(preview)
                for role, column in detected.items():
                    if not ds["settings"]["mapping"].get(role) and column:
                        ds["settings"]["mapping"][role] = column
                mark_data_changed(ds)
                st.rerun()
    left, right = st.columns(2)
    if left.button("Reset to original", key="reset_data"):
        ds["working"] = ds["original"].copy(deep=True)
        ds["history"] = [{"Action": "Reset to original text values"}]
        ds["settings"]["cleaning_rules"] = []
        ds["settings"]["mapping"], _ = detect_roles(ds["working"])
        ds["settings"]["charts"] = suggestions(ds["working"], ds["settings"]["mapping"])
        mark_data_changed(ds)
        st.rerun()
    if right.button("Re-run safe interpretation"):
        ds["working"], ds["settings"]["mapping"], ds["history"] = interpret(ds["original"])
        ds["settings"]["cleaning_rules"] = []
        ds["settings"]["charts"] = suggestions(ds["working"], ds["settings"]["mapping"])
        mark_data_changed(ds)
        st.rerun()
    with st.expander("Preparation history and original values"):
        st.dataframe(pd.DataFrame(ds["history"]), width="stretch")
        st.dataframe(ds["original"].head(20), width="stretch")
