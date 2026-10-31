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
    st.caption("Automatic interpretation safely infers data types upon upload. Data cleaning operations are completely user-controlled and applied to an analysis copy—your original data is always preserved intact.")

    with st.container(border=True):
        st.markdown("#### Data Health & Profiling Overview")
        q_col1, q_col2 = st.columns([1, 2])
        with q_col1:
            st.markdown("##### Quality Metrics")
            st.dataframe(pd.DataFrame({"Original": quality_summary(ds["original"]), "Working Copy": quality_summary(data)}), width="stretch")
        with q_col2:
            st.markdown("##### Column Profile & Missing Value Counts")
            st.dataframe(profile_data(data), hide_index=True, width="stretch")

    with st.container(border=True):
        st.markdown("#### Preparation Studio: Preview & Apply Action")
        st.caption("Select a cleaning operation, inspect the before/after record impact, and apply it with confidence.")

        c_act, c_col = st.columns(2)
        with c_act:
            action = st.selectbox("1. Choose cleaning action", ACTIONS, key="ui_clean_action")
        columns = []
        value, fmt = "", "%Y-%m-%d"
        with c_col:
            if action == "Drop rows with missing values":
                columns = st.multiselect("2. Check these target columns", list(data.columns), key="ui_clean_columns")
            elif action != "Remove duplicate rows":
                column = st.selectbox("2. Target column", list(data.columns), key="ui_clean_column")
                columns = [column]

        if action == "Fill missing values":
            c_fill1, c_fill2 = st.columns(2)
            with c_fill1:
                value = st.text_input("Replacement value", key="ui_clean_fill", help="Enter text or number to replace empty cells")
            with c_fill2:
                fmt = DATE_FORMATS[st.selectbox("Date format (if date column)", list(DATE_FORMATS), key="ui_clean_date")]
        elif action == "Convert to date":
            fmt = DATE_FORMATS[st.selectbox("Date format parser", list(DATE_FORMATS), key="ui_clean_date")]

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

            st.markdown(
                f'<div style="background:#F1F5F9;border:1px solid #E2E8F0;padding:8px 14px;border-radius:6px;font-size:12px;margin:10px 0;">'
                f'<strong>Impact Summary:</strong> Before: <strong>{len(data):,}</strong> records &nbsp;·&nbsp; '
                f'After: <strong>{len(preview):,}</strong> records &nbsp;·&nbsp; '
                f'Removed rows: <strong style="color:{"#DC2626" if len(removed) else "#334155"}">{len(removed):,}</strong> &nbsp;·&nbsp; '
                f'Changed cells: <strong style="color:{"#088395" if cells_changed else "#334155"}">{cells_changed:,}</strong>'
                f'</div>',
                unsafe_allow_html=True
            )

            st.markdown("##### 3. Side-by-Side Verification Diff")
            left, right = st.columns(2)
            with left:
                st.caption("Before · affected records first")
                st.dataframe(data.loc[sample_rows, columns or list(data.columns)], width="stretch")
            with right:
                st.caption("After · retained records from this preview")
                st.dataframe(preview.loc[sample_rows.intersection(preview.index), columns or list(preview.columns)], width="stretch")

            if columns:
                st.caption("Resulting types: " + ", ".join(f"{c}: {preview[c].dtype}" for c in columns))

            st.markdown("##### 4. Confirm & Apply")
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

    c_rst1, c_rst2 = st.columns(2)
    with c_rst1:
        if st.button("Reset to original", key="reset_data", help="Revert all cleaning rules and restore raw uploaded text values"):
            ds["working"] = ds["original"].copy(deep=True)
            ds["history"] = [{"Action": "Reset to original text values"}]
            ds["settings"]["cleaning_rules"] = []
            ds["settings"]["mapping"], _ = detect_roles(ds["working"])
            ds["settings"]["charts"] = suggestions(ds["working"], ds["settings"]["mapping"])
            mark_data_changed(ds)
            st.rerun()
    with c_rst2:
        if st.button("Re-run safe interpretation", help="Re-infer dates and numeric types from original data without manual cleaning"):
            ds["working"], ds["settings"]["mapping"], ds["history"] = interpret(ds["original"])
            ds["settings"]["cleaning_rules"] = []
            ds["settings"]["charts"] = suggestions(ds["working"], ds["settings"]["mapping"])
            mark_data_changed(ds)
            st.rerun()

    with st.expander("Preparation history and original values", expanded=False):
        st.markdown("##### Transformation Audit Trail")
        st.dataframe(pd.DataFrame(ds["history"]), width="stretch")
        st.markdown("##### Original Untouched Data Sample")
        st.dataframe(ds["original"].head(20), width="stretch")
