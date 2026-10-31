"""Step 3 regression tests: preservation, chosen actions, and session behavior."""

import unittest

import pandas as pd
from pandas.testing import assert_frame_equal

from core.csv_loader import load_csv
from core.data_cleaning import apply_cleaning, conversion_preview, profile_data, quality_summary

DIRTY_CSV = (
    b"customer_id,quantity,date,region\n"
    b"001,2,2026-10-01,North\n"
    b"001,2,2026-10-01,North\n"
    b"002, ,2026-10-02,South\n"
    b"003,oops,invalid,\n"
)


class CleaningTests(unittest.TestCase):
    def setUp(self):
        self.data = load_csv("dirty.csv", DIRTY_CSV)
        self.original = self.data.copy(deep=True)

    def tearDown(self):
        assert_frame_equal(self.data, self.original)

    def test_profile_counts_and_identifier_hint(self):
        summary = quality_summary(self.data)
        self.assertEqual(summary["Missing cells"], 2)
        self.assertEqual(summary["Duplicate rows beyond first"], 1)
        profile = profile_data(self.data).set_index("Column")
        self.assertEqual(profile.loc["quantity", "Missing %"], 25.0)
        self.assertEqual(profile.loc["quantity", "Number-compatible text"], 2)
        self.assertIn("Mixed", profile.loc["quantity", "Type guidance"])
        self.assertIn("identifier", profile.loc["customer_id", "Type guidance"])

    def test_missing_definition_excludes_literal_na(self):
        data = pd.DataFrame({"a": ["", " \t", None, "NA", "null", "0"]})
        self.assertEqual(quality_summary(data)["Missing cells"], 3)

    def test_duplicates_keep_first_and_other_values(self):
        cleaned = apply_cleaning(self.data, "Remove duplicate rows")
        self.assertEqual(cleaned["customer_id"].tolist(), ["001", "002", "003"])
        self.assertEqual(cleaned.iloc[1]["quantity"], " ")
        self.assertEqual(cleaned.index.tolist(), [0, 2, 3])  # Original record references survive.

    def test_drop_checks_only_selected_columns(self):
        cleaned = apply_cleaning(self.data, "Drop rows with missing values", ["quantity"])
        self.assertEqual(len(cleaned), 3)
        self.assertEqual(cleaned.iloc[-1]["region"], "")
        both = apply_cleaning(self.data, "Drop rows with missing values", ["quantity", "region"])
        self.assertEqual(len(both), 2)

    def test_fill_changes_only_missing_cells_in_selected_column(self):
        cleaned = apply_cleaning(self.data, "Fill missing values", ["quantity"], "0")
        self.assertEqual(cleaned["quantity"].tolist(), ["2", "2", "0", "oops"])
        self.assertEqual(cleaned.iloc[-1]["region"], "")

    def test_failed_conversion_preserves_input(self):
        _, invalid = conversion_preview(self.data["quantity"], "number")
        self.assertEqual(invalid.tolist(), [False, False, False, True])
        with self.assertRaisesRegex(ValueError, "1 nonmissing"):
            apply_cleaning(self.data, "Convert to number", ["quantity"])

    def test_numeric_conversion_keeps_blanks_missing_and_ids_untouched(self):
        source = pd.DataFrame({"id": ["001", "002", "003"], "n": ["2", "", "3.5"]})
        cleaned = apply_cleaning(source, "Convert to number", ["n"])
        self.assertTrue(pd.api.types.is_numeric_dtype(cleaned["n"]))
        self.assertTrue(pd.isna(cleaned.loc[1, "n"]))
        self.assertEqual(cleaned["id"].tolist(), ["001", "002", "003"])
        self.assertEqual(source.loc[1, "n"], "")

    def test_nonfinite_numbers_block_conversion(self):
        for value in ("inf", "-inf", "NaN", "1e999"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                apply_cleaning(pd.DataFrame({"a": [value]}), "Convert to number", ["a"])

    def test_explicit_date_formats_and_invalid_calendar_date(self):
        source = pd.DataFrame({"d": ["03/04/2026", ""]})
        day_first = apply_cleaning(source, "Convert to date", ["d"], date_format="%d/%m/%Y")
        month_first = apply_cleaning(source, "Convert to date", ["d"], date_format="%m/%d/%Y")
        self.assertEqual(day_first.loc[0, "d"].month, 4)
        self.assertEqual(month_first.loc[0, "d"].month, 3)
        self.assertTrue(pd.isna(day_first.loc[1, "d"]))
        with self.assertRaises(ValueError):
            apply_cleaning(pd.DataFrame({"d": ["2026-02-30"]}), "Convert to date", ["d"])

    def test_typed_fill_validates_replacement(self):
        source = pd.DataFrame({"n": pd.Series([2, None], dtype="Int64")})
        cleaned = apply_cleaning(source, "Fill missing values", ["n"], "1.5")
        self.assertEqual(cleaned["n"].tolist(), [2.0, 1.5])
        with self.assertRaises(ValueError):
            apply_cleaning(source, "Fill missing values", ["n"], "unknown")
        dates = pd.DataFrame({"d": pd.to_datetime(["2026-01-01", None])})
        filled = apply_cleaning(dates, "Fill missing values", ["d"], "2026-02-01")
        self.assertEqual(filled.loc[1, "d"].month, 2)

    def test_empty_result_profiles_and_all_missing_conversion(self):
        source = pd.DataFrame({"a": ["", " "]})
        with self.assertRaisesRegex(ValueError, "no nonmissing"):
            apply_cleaning(source, "Convert to number", ["a"])
        empty = apply_cleaning(source, "Drop rows with missing values", ["a"])
        self.assertEqual(quality_summary(empty)["Rows"], 0)
        self.assertEqual(profile_data(empty).iloc[0]["Missing %"], 0.0)

    def test_invalid_options_are_rejected(self):
        for action, columns, value in [
            ("unknown", [], ""),
            ("Fill missing values", [], "x"),
            ("Fill missing values", ["absent"], "x"),
            ("Fill missing values", ["quantity"], " "),
            ("Convert to number", ["quantity", "region"], ""),
        ]:
            with self.subTest(action=action, columns=columns), self.assertRaises(ValueError):
                apply_cleaning(self.data, action, columns, value)


# Automatic workflow UI regressions are maintained in test_workflows.py.
# The former manual-conversion/planned-page expectations were superseded by the PRD.


if __name__ == "__main__":
    unittest.main()
