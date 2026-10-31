"""Upload, automatic understanding, and optional mapping controls."""
from pathlib import Path
import pandas as pd
import streamlit as st
from app_state import clear_dataset, install_dataset, upload_changed, clear_controls
from core.automation import ALIASES, NUMERIC_ROLES, analyze_column_semantics, adapt_column_type, detect_roles
from core.data_cleaning import missing_mask
from core.charts import suggestions
from core.catalogue import FIELDS, RECOMMENDED, analysis_columns
from core.demo_data import extended_demo
from ui.template_ui import render_templates


def sample_preview(series, max_count=3, max_len=28):
    """Return a short readable comma-separated sample of first non-empty values."""
    missing = missing_mask(series)
    non_empty = series[~missing].astype(str).str.strip()
    non_empty = non_empty[non_empty != ""]
    samples = non_empty.head(max_count).tolist()
    if not samples:
        return "(empty)"
    preview = ", ".join(samples)
    return (preview[:max_len] + "...") if len(preview) > max_len else preview


def find_data_file(filename):
    """Locate sample files reliably whether running from root or subpackage."""
    candidates = [
        Path(__file__).resolve().parent.parent / "data" / filename,
        Path(__file__).resolve().parent.parent / filename,
        Path(__file__).with_name(filename),
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def render_data():
    with st.container(border=True):
        left, right = st.columns([2, 1])
        with left:
            key = f"upload_csv_{st.session_state.get('upload_epoch', 0)}"
            upload = st.file_uploader("Choose a CSV or Excel file", type=["csv", "xlsx"], max_upload_size=10, key=key,
                                      on_change=upload_changed, args=(key,),
                                      help="Comma-separated UTF-8 (.csv) or Excel workbook (.xlsx). Up to 10 MiB. Your upload remains in this session.")
            if upload is not None and install_dataset(upload.name, upload.getvalue()):
                st.rerun()
        with right:
            st.write("Try fictional sales data")
            if st.button("Use sample data", type="primary", key="use_sample"):
                path = find_data_file("sample_sales.csv")
                install_dataset(path.name, path.read_bytes(), force=True, currency="INR")
                st.session_state["upload_epoch"] = st.session_state.get("upload_epoch", 0) + 1
                st.rerun()
            if st.button("Use extended demo", key="use_demo"):
                install_dataset("fictional_extended_sales.csv", extended_demo(), force=True, currency="INR")
                st.session_state["upload_epoch"] = st.session_state.get("upload_epoch", 0) + 1
                st.rerun()
            st.caption("Small sample: 8 rows. Extended demo: 18 months and 30 customers for model demonstrations.")
            example = find_data_file("sample_sales_catalogue.csv")
            st.download_button("Download 20-field CSV example", example.read_bytes(), example.name, "text/csv")
    if st.session_state.get("upload_error"):
        st.error(st.session_state["upload_error"])
    ds = st.session_state.get("dataset")
    if ds is None:
        st.info("Upload a CSV or use fictional data. Analysis starts automatically; customization is optional.")
        return
    supported = analysis_columns(ds["working"], ds["settings"]["mapping"])
    extras = [c for c in ds["working"] if c not in supported]
    analysis = analyze_column_semantics(ds["working"], ds["settings"]["mapping"])

    st.success(f"Dataset loaded. {len(supported)} columns mapped to the 20-field catalogue · {len(extras)} auxiliary columns preserved.")
    t1, t2 = st.tabs([
        f"Active Business Fields ({len(analysis['active'])})",
        f"Preserved Auxiliary Attributes ({len(analysis['auxiliary']) + len(analysis['suggested'])})"
    ])
    with t1:
        st.caption("These fields are mapped to the 20-field business catalogue and drive your KPIs, dashboard charts, forecasts, and reports.")
        active_df = pd.DataFrame([{
            "Column Header": item["column"],
            "Business Role": item["role"].replace("_", " ").title(),
            "Data Type": item["type"],
            "Semantic Match": item["reason"]
        } for item in analysis["active"]])
        st.table(active_df)

    with t2:
        st.caption("These columns are preserved intact for preview, data cleaning, and CSV exports, but excluded from financial calculations so operational attributes (like phone numbers, addresses, and line numbers) do not distort accounting metrics.")
        if analysis["suggested"]:
            st.write("**Optional / Suggested Mappings:**")
            st.table(pd.DataFrame([{
                "Column Header": item["column"],
                "Suggested Role": item["suggested_role"].replace("_", " ").title(),
                "Data Type": item["type"],
                "Semantic Rationale": item["reason"]
            } for item in analysis["suggested"]]))
            st.write("##### Quick Promotion Actions:")
            q_cols = st.columns(min(len(analysis["suggested"]), 3))
            for i, item in enumerate(analysis["suggested"]):
                with q_cols[i % len(q_cols)]:
                    col_name = item["column"]
                    target_role = item["suggested_role"]
                    role_label = target_role.replace("_", " ").title()
                    if st.button(f"Promote '{col_name}' → {role_label}", key=f"quick_promote_{col_name}",
                                 help=f"Map '{col_name}' to '{role_label}' and adapt type if needed"):
                        converted, ok, reason = adapt_column_type(ds["working"][col_name], target_role)
                        if ok:
                            ds["working"][col_name] = converted
                            ds["settings"]["mapping"][target_role] = col_name
                            ds["settings"]["charts"] = suggestions(ds["working"], ds["settings"]["mapping"])
                            clear_controls()
                            st.rerun()
                        else:
                            st.error(f"Cannot promote '{col_name}': {reason}")
        if analysis["auxiliary"]:
            st.write("**Operational & Contact Metadata:**")
            st.table(pd.DataFrame([{
                "Column Header": item["column"],
                "Category": item["category"],
                "Data Type": item["type"],
                "Preservation Purpose": item["explanation"]
            } for item in analysis["auxiliary"]]))
            st.caption("Need to map an operational attribute to a business role? Use the Manual Column Mapping Studio below.")
    with st.expander("20 supported fields · dataset requirements"):
        st.write("Not all 20 are mandatory. Missing fields disable dependent features.")
        st.write("Recommended demo fields: " + ", ".join(RECOMMENDED))
        st.dataframe(pd.DataFrame([{"Field": role, "Type": details[0], "Meaning": details[1],
                                   "Mapped column": ds["settings"]["mapping"].get(role) or "Not mapped"}
                                  for role, details in FIELDS.items()]), hide_index=True, width="stretch")
        st.caption("One row must represent one sales line item. Discount is never deducted automatically. "
                   "Reported profit is not assumed to mean gross or net profit.")
    a,b,c = st.columns(3)
    a.metric("Records", len(ds["working"]))
    b.metric("Columns", len(ds["working"].columns))
    c.metric("Data version", ds["revision"])
    if st.button("Open automatic dashboard", type="primary"):
        st.session_state["page"] = "Dashboard"
        st.rerun()
    with st.expander("Detected fields and interpretation log"):
        st.dataframe(pd.DataFrame(ds["history"]), hide_index=True, width="stretch")
    with st.expander("Manual Column Mapping Studio & Currency", expanded=False):
        settings = ds["settings"]
        top_left, top_right = st.columns([3, 1])
        with top_left:
            st.markdown("#### Column Mapping Studio")
            st.caption("Review, customize, or override the assignment between your uploaded source columns and the 20-field canonical catalogue. Unmapped columns are safely preserved intact as auxiliary attributes.")
        with top_right:
            if st.button("Reset to Auto-Detection", key="reset_auto_mapping", help="Revert all mappings back to the automatic NLP detection"):
                auto_mapping, _ = detect_roles(ds["working"])
                settings["mapping"] = auto_mapping
                settings["charts"] = suggestions(ds["working"], auto_mapping)
                clear_controls()
                st.rerun()

        map_tab_source, map_tab_role = st.tabs([
            "Source-First Mapping (Column → Role)",
            "Catalogue-First Mapping (Role → Column)"
        ])
        
        col_to_role = {v: k for k, v in settings["mapping"].items() if v}
        columns = ds["working"].columns.tolist()

        with map_tab_source:
            with st.form("source_first_mapping_form"):
                st.write("##### Assign Source Columns to Business Roles")
                st.caption("Select the appropriate catalogue role for each column in your dataset. Selecting '[Preserved as Auxiliary]' keeps the column in data preview and exports without calculating financial KPIs on it.")
                
                h1, h2, h3, h4 = st.columns([3, 3, 2, 4])
                h1.markdown("**Column Header**")
                h2.markdown("**Sample Preview**")
                h3.markdown("**Data Type**")
                h4.markdown("**Target Catalogue Role**")

                role_options = [None] + list(FIELDS.keys())
                selected_source_mappings = {}

                for col in columns:
                    c1, c2, c3, c4 = st.columns([3, 3, 2, 4])
                    c1.markdown(f"**`{col}`**")
                    c2.caption(sample_preview(ds["working"][col]))
                    c3.caption(f"`{ds['working'][col].dtype}`")
                    
                    current_role = col_to_role.get(col)
                    current_index = role_options.index(current_role) if current_role in role_options else 0
                    
                    selected_source_mappings[col] = c4.selectbox(
                        f"Target role for {col}",
                        options=role_options,
                        index=current_index,
                        format_func=lambda r: "[Preserved as Auxiliary]" if r is None else f"{r.replace('_', ' ').title()} ({FIELDS[r][0]})",
                        label_visibility="collapsed",
                        key=f"src_map_{col}"
                    )

                st.divider()
                currency_source = st.text_input(
                    "Currency label (blank = unspecified)",
                    value="" if settings["currency"] == "Unspecified" else settings["currency"],
                    max_chars=32,
                    key="currency_source_input",
                    help="Labels do not convert exchange rates. A dataset currency column takes priority."
                )

                if st.form_submit_button("Apply Mappings & Adapt Types", type="primary"):
                    mapped_roles = [r for r in selected_source_mappings.values() if r is not None]
                    if len(mapped_roles) != len(set(mapped_roles)):
                        seen = set()
                        duplicates = {r for r in mapped_roles if r in seen or seen.add(r)}
                        dup_names = [r.replace("_", " ").title() for r in duplicates]
                        st.error(f"Duplicate assignment error: The role(s) {', '.join(dup_names)} were assigned to multiple columns. Each business role must be assigned to at most one column.")
                    else:
                        adapt_errors = []
                        adapted_cols = {}
                        for col, target_role in selected_source_mappings.items():
                            if target_role is not None:
                                converted, ok, reason = adapt_column_type(ds["working"][col], target_role)
                                if not ok:
                                    adapt_errors.append(f"Column '{col}' mapped to {target_role.replace('_', ' ').title()}: {reason}")
                                else:
                                    adapted_cols[col] = converted
                        if adapt_errors:
                            for err in adapt_errors:
                                st.error(err)
                        else:
                            for col, series in adapted_cols.items():
                                ds["working"][col] = series
                            new_mapping = {r: None for r in ALIASES}
                            for col, target_role in selected_source_mappings.items():
                                if target_role is not None:
                                    new_mapping[target_role] = col
                            settings["mapping"] = new_mapping
                            settings["currency"] = currency_source.strip() or "Unspecified"
                            settings["filters"] = {}
                            settings["charts"] = suggestions(ds["working"], new_mapping)
                            clear_controls()
                            st.rerun()

        with map_tab_role:
            with st.form("catalogue_first_mapping_form"):
                st.write("##### Assign Catalogue Roles to Source Columns")
                st.caption("Inspect and configure each of the 20 catalogue roles individually.")
                mappings_by_role = {}
                col_options = [None] + columns
                for role in ALIASES:
                    current_col = settings["mapping"].get(role)
                    current_idx = col_options.index(current_col) if current_col in col_options else 0
                    mappings_by_role[role] = st.selectbox(
                        role.replace("_", " ").title(),
                        col_options,
                        index=current_idx,
                        format_func=lambda x: "Not mapped" if x is None else f"{x} ({ds['working'][x].dtype})",
                        key=f"role_map_{role}"
                    )
                currency_role = st.text_input(
                    "Currency label (blank = unspecified)",
                    value="" if settings["currency"] == "Unspecified" else settings["currency"],
                    max_chars=32,
                    key="currency_role_input"
                )
                if st.form_submit_button("Apply Catalogue Mappings"):
                    selected = [v for v in mappings_by_role.values() if v]
                    if len(selected) != len(set(selected)):
                        st.error("Map each column to one business role only.")
                    else:
                        adapt_errors = []
                        adapted_cols = {}
                        for role, col in mappings_by_role.items():
                            if col is not None:
                                converted, ok, reason = adapt_column_type(ds["working"][col], role)
                                if not ok:
                                    adapt_errors.append(f"Column '{col}' mapped to {role.replace('_', ' ').title()}: {reason}")
                                else:
                                    adapted_cols[col] = converted
                        if adapt_errors:
                            for err in adapt_errors:
                                st.error(err)
                        else:
                            for col, series in adapted_cols.items():
                                ds["working"][col] = series
                            settings["mapping"] = mappings_by_role
                            settings["filters"] = {}
                            settings["currency"] = currency_role.strip() or "Unspecified"
                            settings["charts"] = suggestions(ds["working"], mappings_by_role)
                            clear_controls()
                            st.rerun()
    st.subheader("Data preview")
    st.dataframe(ds["working"].head(20), hide_index=True, width="stretch")
    with st.expander("Original data (unchanged)"):
        st.dataframe(ds["original"].head(20), hide_index=True, width="stretch")
    render_templates(ds)
    if st.button("Remove active dataset", key="remove_data"):
        clear_dataset()
        st.session_state["upload_epoch"] = st.session_state.get("upload_epoch", 0) + 1
        st.rerun()
