"""Run with: python -m unittest discover -s tests -v."""

from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from core.csv_loader import MAX_UPLOAD_BYTES, load_csv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CsvLoaderTests(unittest.TestCase):
    def test_fictional_sample(self):
        data = load_csv("sample_sales.csv", (PROJECT_ROOT / "data" / "sample_sales.csv").read_bytes())
        self.assertEqual(data.shape, (8, 9))
        self.assertEqual(data.columns.tolist(), [
            "date", "order_id", "customer_id", "product", "category",
            "quantity", "unit_price", "unit_cost", "region",
        ])
        self.assertEqual(data.iloc[0]["order_id"], "ORD001")

    def test_preserves_values_and_duplicate_rows(self):
        source = b"id,note,amount\n001,NA,\n001,NA,\n"
        original = source[:]
        data = load_csv("records.csv", source)
        self.assertEqual(data.values.tolist(), [["001", "NA", ""], ["001", "NA", ""]])
        self.assertEqual(source, original)

    def test_bom_unicode_quotes_and_multiline_fields(self):
        source = '\ufeffname,note\r\nCafé,"North, East"\r\nTea,"two\nlines"\r\n'
        data = load_csv("EXPORT.CSV", source.encode("utf-8"))
        self.assertEqual(data.columns.tolist(), ["name", "note"])
        self.assertEqual(data.values.tolist(), [["Café", "North, East"], ["Tea", "two\nlines"]])

    def test_single_column_and_blank_lines(self):
        data = load_csv("names.csv", b"\nname\nAlice\n\nBob\n")
        self.assertEqual(data.shape, (2, 1))

    def test_blank_cells_are_not_an_empty_file(self):
        data = load_csv("blanks.csv", b"a,b\n,\n")
        self.assertEqual(data.values.tolist(), [["", ""]])

    def test_invalid_uploads(self):
        cases = [
            ("wrong.txt", b"a\n1", ".csv extension"),
            ("large.csv", b"x" * (MAX_UPLOAD_BYTES + 1), "too large"),
            ("empty.csv", b"", "empty"),
            ("blank.csv", b" \r\n\t", "empty"),
            ("headers.csv", b"a,b\n", "no data rows"),
            ("encoding.csv", b"name\n\xff", "UTF-8"),
            ("binary.csv", b"a\n\x00", "null bytes"),
            ("duplicate.csv", b"a,a\n1,2", "unique"),
            ("unnamed.csv", b"a, \n1,2", "nonempty"),
            ("extra.csv", b"a,b\n1,2,3", "3 fields"),
            ("short.csv", b"a,b\n1", "1 fields"),
            ("quotes.csv", b'a,b\n1,"unfinished', "quotation marks"),
        ]
        for filename, contents, message in cases:
            with self.subTest(filename=filename):
                with self.assertRaisesRegex(ValueError, message):
                    load_csv(filename, contents)

    def test_excel_upload_and_preservation(self):
        import openpyxl
        import datetime
        buf = BytesIO()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["order_id", "date", "quantity", "price"])
        ws.append(["001", datetime.date(2026, 10, 28), 10, 25.5])
        ws.append(["002", datetime.datetime(2026, 10, 29, 0, 0), 5, None])
        wb.save(buf)

        data = load_csv("sales.xlsx", buf.getvalue())
        self.assertEqual(data.shape, (2, 4))
        self.assertEqual(data.columns.tolist(), ["order_id", "date", "quantity", "price"])
        self.assertEqual(data.iloc[0]["order_id"], "001")
        self.assertEqual(data.iloc[0]["date"], "2026-10-28")
        self.assertEqual(data.iloc[1]["price"], "")

    def test_excel_invalid_uploads(self):
        import openpyxl
        buf_empty = BytesIO()
        openpyxl.Workbook().save(buf_empty)

        buf_dup = BytesIO()
        wb_dup = openpyxl.Workbook()
        wb_dup.active.append(["col", "col"])
        wb_dup.active.append(["1", "2"])
        wb_dup.save(buf_dup)

        cases = [
            ("empty.xlsx", buf_empty.getvalue(), "empty|no data rows"),
            ("dup.xlsx", buf_dup.getvalue(), "unique"),
            ("corrupt.xlsx", b"not an excel file", "Excel file could not be read"),
        ]
        for filename, contents, message in cases:
            with self.subTest(filename=filename):
                with self.assertRaisesRegex(ValueError, message):
                    load_csv(filename, contents)


class UploadInterfaceTests(unittest.TestCase):
    """Inject uploads at the widget boundary; native file selection is a manual check."""

    def setUp(self):
        self.app = AppTest.from_file(str(PROJECT_ROOT / "app.py"))

    def run_with_upload(self, contents=None):
        upload = None
        if contents is not None:
            upload = BytesIO(contents)
            upload.name = "test.csv"
        with patch("streamlit.file_uploader", return_value=upload):
            self.app.run(timeout=15)
        self.assertFalse(self.app.exception)

    def test_real_widget_renders_without_upload(self):
        self.app.run(timeout=15)
        self.assertFalse(self.app.exception)
        self.assertEqual(len(self.app.get("file_uploader")), 1)
        self.assertEqual(len(self.app.info), 1)
        self.assertEqual(len(self.app.dataframe), 0)

    def test_sample_metrics_and_preview(self):
        self.run_with_upload((PROJECT_ROOT / "data" / "sample_sales.csv").read_bytes())
        self.assertEqual([metric.value for metric in self.app.metric], ["8", "9", "1"])
        self.assertEqual(len(self.app.success), 1)
        self.assertEqual(len(self.app.dataframe[0].value), 20)
        self.assertIn("Interpretation", self.app.dataframe[1].value.columns)
        self.assertEqual(self.app.dataframe[2].value.shape, (8, 9))

    def test_preview_is_limited_but_count_is_full(self):
        self.run_with_upload(("id\n" + "\n".join(str(i) for i in range(15))).encode())
        self.assertEqual(self.app.metric[0].value, "15")
        self.assertEqual(len(self.app.dataframe[2].value), 15)  # Preview limit is now 20.

    def test_replacing_valid_upload_with_invalid_clears_results(self):
        self.run_with_upload(b"a,b\n1,2")
        self.run_with_upload(b"a,b\n1,2,3")
        self.assertEqual(len(self.app.error), 1)
        self.assertEqual(len(self.app.metric), 0)
        self.assertEqual(len(self.app.dataframe), 0)

    def test_removing_upload_clears_results(self):
        self.run_with_upload(b"a,b\n1,2")
        self.app.button(key="remove_data").click()
        self.run_with_upload()
        self.assertEqual(len(self.app.info), 1)
        self.assertEqual(len(self.app.metric), 0)
        self.assertEqual(len(self.app.dataframe), 0)


if __name__ == "__main__":
    unittest.main()
