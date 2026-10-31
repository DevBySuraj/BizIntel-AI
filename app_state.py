"""Session data, durable settings, and explicit invalidation."""
from hashlib import sha256
import streamlit as st
from core.csv_loader import load_csv
from core.automation import interpret, default_settings
from core.charts import suggestions

CONTROL_PREFIXES = ("ui_", "clean_", "dash_", "kpi_", "map_", "fc_")


def clear_controls(prefixes=CONTROL_PREFIXES):
    for key in list(st.session_state):
        if key.startswith(prefixes):
            del st.session_state[key]


def preserve_controls():
    # Only ordinary widgets use ui_. Buttons deliberately use other prefixes.
    for key in list(st.session_state):
        if key.startswith("ui_"):
            st.session_state[key] = st.session_state[key]


def next_version():
    version = st.session_state.get("version_counter", 0) + 1
    st.session_state["version_counter"] = version
    return version


def clear_dataset():
    st.session_state.pop("dataset", None)
    st.session_state.pop("upload_error", None)
    st.session_state.pop("report_draft", None)
    st.session_state.pop("report_files", None)
    clear_controls()


def install_dataset(name, contents, force=False, currency="Unspecified"):
    source_id = sha256(name.encode("utf-8") + b"\0" + contents).hexdigest()
    if not force and st.session_state.get("dataset", {}).get("source_id") == source_id:
        return False
    try:
        original = load_csv(name, contents)
        working, mapping, log = interpret(original)
    except ValueError as error:
        clear_dataset()
        st.session_state["upload_error"] = str(error)
        return False
    clear_dataset()
    settings = default_settings(working, mapping, currency)
    settings["charts"] = suggestions(working, mapping)
    st.session_state["dataset"] = {
        "name": name, "source_id": source_id, "revision": next_version(),
        "original": original.copy(deep=True), "original_bytes": contents,
        "working": working, "history": log, "settings": settings,
    }
    return True


def upload_changed(key):
    upload = st.session_state.get(key)
    if upload is None:
        clear_dataset()
    else:
        install_dataset(upload.name, upload.getvalue(), force=True)


def mark_data_changed(dataset):
    dataset["revision"] = next_version()
    dataset["settings"]["filters"] = {}
    st.session_state.pop("report_files", None)
    clear_controls()


def navigate(page):
    st.session_state["page"] = page
