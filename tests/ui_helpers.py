"""Test uploads at the UI boundary, then open the requested workspace page."""

from io import BytesIO
from unittest.mock import patch


def run_upload(app, contents, page):
    upload = None
    if contents is not None:
        upload = BytesIO(contents)
        upload.name = "test.csv"
    with patch("streamlit.file_uploader", return_value=upload):
        if getattr(app, "fixture_contents", object()) != contents:
            app.session_state["page"] = "Data"
            app.run(timeout=20)
            if contents is None and "dataset" in app.session_state:
                app.button(key="remove_data").click().run(timeout=20)
            app.fixture_contents = contents
        app.session_state["page"] = page
        app.run(timeout=20)
