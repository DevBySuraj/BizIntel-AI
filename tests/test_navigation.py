"""Real sidebar buttons and session persistence across views."""

from pathlib import Path
import unittest

from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=20)
        self.app.button(key="use_sample").click().run(timeout=20)
        self.assertFalse(self.app.exception)

    def go(self, page):
        self.app.button(key=f"nav_{page}").click().run(timeout=20)
        self.assertFalse(self.app.exception)

    def test_navigation_preserves_working_data_and_filters(self):
        self.go("Prepare")
        original = self.app.session_state["dataset"]["working"].copy(deep=True)
        version = self.app.session_state["dataset"]["revision"]
        self.go("Explore")
        self.app.multiselect(key="ui_filter_columns").set_value(["region"]).run()
        self.app.multiselect(key="ui_values_region").set_value(["North"]).run()
        self.go("Data")
        self.go("Explore")
        self.assertEqual(self.app.multiselect(key="ui_values_region").value, ["North"])
        assert_frame_equal(self.app.session_state["dataset"]["working"], original)
        self.assertEqual(self.app.session_state["dataset"]["revision"], version)

    def test_reports_are_now_functional(self):
        for page in ("Reports",):
            self.go(page)
            self.assertEqual(len(self.app.get("plotly_chart")), 3)
            self.assertTrue(self.app.get("download_button"))

    def test_clear_dataset_and_empty_module(self):
        self.app.button(key="remove_data").click().run()
        self.go("Explore")
        self.assertNotIn("dataset", self.app.session_state)
        self.assertTrue(any("Choose a dataset" in message.value for message in self.app.info))


if __name__ == "__main__":
    unittest.main()
