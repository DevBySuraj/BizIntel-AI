"""Template management, with explicit update/delete confirmation."""
import streamlit as st
from core.automation import interpret, default_settings
from core.charts import suggestions
from app_state import mark_data_changed
from core.templates import list_templates, save_template, delete_template, compatible_settings


def render_templates(dataset):
    with st.expander("Reusable templates"):
        st.caption("Saved locally across restarts. Stores settings and approved cleaning rules, never uploaded rows or old results.")
        try:
            templates, errors = list_templates()
            for error in errors:
                st.warning(error)
            names = {t["id"]: t["name"] for t in templates}
            chosen = st.selectbox("Saved template", [None] + list(names), format_func=lambda x: names.get(x, "Choose a template"), key="ui_template")
            if chosen:
                document = next(t for t in templates if t["id"] == chosen)
                st.caption(document.get("description", ""))
                if st.button("Load template on this dataset"):
                    working, mapping, log = interpret(dataset["original"])
                    defaults = default_settings(working, mapping, dataset["settings"]["currency"])
                    updated, settings, warnings = compatible_settings(working, defaults, document)
                    dataset["working"] = updated
                    dataset["history"] = log + [{"Action": f"Template: {document['name']}; approved rules replayed", "Before": len(working), "After": len(updated)}]
                    for rule in settings["cleaning_rules"]:
                        dataset["history"].append({"Action": rule["action"], "Columns": ", ".join(rule.get("columns", []))})
                    dataset["settings"] = settings
                    if not settings["charts"]:
                        settings["charts"] = suggestions(updated, settings["mapping"])
                    # A template's valid filters replace the previous scope.
                    filters = settings["filters"]
                    mark_data_changed(dataset)
                    settings["filters"] = filters
                    st.session_state["template_notice"] = warnings or ["Template loaded. All outputs recomputed for current data."]
                    st.rerun()
                confirm = st.checkbox("Confirm updating or deleting this saved template", key="ui_template_confirm")
                if st.button("Update selected with current settings", disabled=not confirm):
                    save_template(document["name"], document.get("description", ""), dataset["settings"], chosen)
                    st.success("Template updated.")
                rename = st.text_input("New name for selected template", key="ui_template_rename", max_chars=100)
                if st.button("Rename selected", disabled=not rename.strip()):
                    save_template(rename, document.get("description", ""), document["settings"], chosen)
                    st.rerun()
                if st.button("Delete selected", disabled=not confirm):
                    delete_template(chosen)
                    del st.session_state["ui_template"]
                    st.rerun()
            name = st.text_input("Name for a new template", key="ui_template_name", max_chars=100)
            description = st.text_input("Template description", key="ui_template_description", max_chars=1000)
            if st.button("Save as new template", type="primary", disabled=not name.strip()):
                save_template(name, description, dataset["settings"])
                st.success("Template saved locally. It will be available after restarting.")
        except (OSError, ValueError, TypeError) as error:
            st.error(f"Template could not be processed: {error}")
        for message in st.session_state.pop("template_notice", []):
            st.info(message)
