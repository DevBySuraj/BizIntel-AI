"""Verify chart values, filter boundaries, and integration with working data."""

from datetime import date
import unittest

import pandas as pd
from pandas.testing import assert_frame_equal

from core.dashboard import build_chart, chart_options, column_groups, filter_data


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.data = pd.DataFrame({
            "region": ["North", "North", "South", "", "South"],
            "quantity": pd.Series([2, 4, 3, 8, None], dtype="Float64"),
            "price": [10.0, 20.0, 30.0, 40.0, 50.0],
            "date": pd.to_datetime(["2026-10-02", "2026-10-01", "2026-10-02", "2026-10-03", None]),
        })
        self.original = self.data.copy(deep=True)

    def tearDown(self):
        assert_frame_equal(self.data, self.original)

    def test_types_are_not_inferred_from_text(self):
        text = pd.DataFrame({"id": ["001"], "n": ["2"], "d": ["2026-10-01"]})
        self.assertEqual(chart_options(text), ["Category counts"])
        self.assertEqual(len(chart_options(self.data)), 5)
        self.assertEqual(column_groups(self.data)["date"], ["date"])

    def test_filters_combine_with_and_and_include_endpoints(self):
        filtered = filter_data(self.data, "region", ["North"], "quantity", (2, 4),
                               "date", (date(2026, 10, 1), date(2026, 10, 2)))
        self.assertEqual(filtered.index.tolist(), [0, 1])
        filtered.iloc[0, 0] = "Changed"

    def test_missing_filters_are_explicit(self):
        filtered = filter_data(self.data, category="region", selected_values=[], include_missing=True)
        self.assertEqual(filtered.index.tolist(), [3])
        self.assertTrue(filter_data(self.data, category="region", selected_values=[]).empty)
        numeric = filter_data(self.data, numeric="quantity", number_range=(2, 3), include_missing=True)
        self.assertEqual(numeric.index.tolist(), [0, 2, 4])

    def test_date_filter_includes_whole_end_day(self):
        frame = pd.DataFrame({"d": pd.to_datetime(["2026-10-02 23:59", "2026-10-03 00:00"])})
        result = filter_data(frame, date="d", date_range=(date(2026, 10, 2), date(2026, 10, 2)))
        self.assertEqual(len(result), 1)

    def test_invalid_filters(self):
        for options in (
            {"numeric": "region", "number_range": (0, 1)},
            {"numeric": "quantity", "number_range": (5, 1)},
            {"date": "date", "date_range": (date(2026, 10, 3),)},
            {"date": "date", "date_range": (date(2026, 10, 3), date(2026, 10, 1))},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                filter_data(self.data, **options)

    def test_category_counts_exclude_missing_and_count_records(self):
        figure, table, notes = build_chart(self.data, "Category counts", "region")
        self.assertEqual(figure.data[0].type, "bar")
        self.assertEqual(dict(table.values.tolist()), {"North": 2, "South": 2})
        self.assertIn("Excluded 1", notes[0])

    def test_mean_and_sum_are_explicit(self):
        _, mean, _ = build_chart(self.data, "Category comparison", "region", "quantity", "Mean")
        _, total, _ = build_chart(self.data, "Category comparison", "region", "quantity", "Sum")
        self.assertEqual(dict(mean.values.tolist()), {"North": 3.0, "South": 3.0})
        self.assertEqual(dict(total.values.tolist()), {"North": 6.0, "South": 3.0})

    def test_time_trend_groups_and_sorts_dates(self):
        figure, table, _ = build_chart(self.data, "Trend over time", "date", "quantity", "Sum")
        self.assertEqual(figure.data[0].mode, "lines+markers")
        self.assertEqual(table.iloc[:, 0].dt.day.tolist(), [1, 2, 3])
        self.assertEqual(table.iloc[:, 1].tolist(), [4.0, 5.0, 8.0])
        with self.assertRaisesRegex(ValueError, "two distinct dates"):
            build_chart(self.data.iloc[[0]], "Trend over time", "date", "quantity")

    def test_histogram_and_scatter_use_only_valid_observations(self):
        histogram, table, notes = build_chart(self.data, "Numeric distribution", "quantity")
        self.assertEqual(histogram.data[0].type, "histogram")
        self.assertEqual(len(table), 4)
        self.assertIn("Excluded 1", notes[0])
        scatter, table, _ = build_chart(self.data, "Numeric relationship", "quantity", "price")
        self.assertEqual(scatter.data[0].mode, "markers")
        self.assertEqual(len(table), 4)

    def test_chart_prerequisites_and_empty_values(self):
        for kind, x, y in (
            ("Numeric distribution", "region", None),
            ("Numeric relationship", "quantity", "quantity"),
            ("Category comparison", "region", "date"),
        ):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                build_chart(self.data, kind, x, y)
        with self.assertRaisesRegex(ValueError, "No usable values"):
            build_chart(self.data.iloc[[4]], "Numeric distribution", "quantity")

    def test_top_categories_and_scatter_sampling_are_disclosed(self):
        frame = pd.DataFrame({"group": [str(i) for i in range(30)]})
        _, table, notes = build_chart(frame, "Category counts", "group")
        self.assertEqual(len(table), 20)
        self.assertTrue(any("top 20 of 30" in note for note in notes))
        frame = pd.DataFrame({"a": range(5001), "b": range(5001)})
        _, first, notes = build_chart(frame, "Numeric relationship", "a", "b")
        _, second, _ = build_chart(frame, "Numeric relationship", "a", "b")
        self.assertEqual(len(first), 5000)
        assert_frame_equal(first, second)
        self.assertTrue(any("sample" in note for note in notes))

    def test_arbitrary_column_names_and_nonfinite_values(self):
        frame = pd.DataFrame({"x": [1.0, float("inf")], "y": [2.0, 3.0]})
        _, table, notes = build_chart(frame, "Numeric relationship", "x", "y")
        self.assertEqual(table.values.tolist(), [[1.0, 2.0]])
        self.assertIn("Excluded 1", notes[0])


# Automatic workflow UI regressions are maintained in test_workflows.py.
# The former manual-conversion/planned-page expectations were superseded by the PRD.


if __name__ == "__main__":
    unittest.main()
