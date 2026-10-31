"""Approved 20-field contract and sales/profit accounting regressions."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from streamlit.testing.v1 import AppTest
from test_product import dataset
from core.analysis import context
from core.catalogue import FIELDS, canonical_mapping
from core.charts import build_figure, spec
from core.intelligence import forecast
from core.reports import assemble_report, html_bytes
from core.templates import save_template, compatible_settings, validate

ROOT = Path(__file__).resolve().parents[1]


class CatalogueTests(unittest.TestCase):
    def test_exact_catalogue_and_full_example(self):
        expected = "order_date order_id customer_id segment product_id product_name category sub_category sales quantity discount profit unit_price unit_cost total_cost country state city region currency".split()
        self.assertEqual(list(FIELDS), expected)
        ds = dataset((ROOT / "data" / "sample_sales_catalogue.csv").read_bytes())
        self.assertEqual(ds["settings"]["mapping"], {key: key for key in expected})
        m = context(ds)["metrics"]
        self.assertEqual((m["total_revenue"], m["total_profit"], m["units_sold"], m["aov"]), (5180, 1920, 17, 647.5))
        self.assertEqual(m["profit_label"], "Reported profit")
        self.assertEqual((m["sales_conflicts"], m["profit_conflicts"]), (0, 0))

    def test_superstore_headers_and_identifier_preservation(self):
        ds = dataset(b"Order Date,Order ID,Customer ID,Product ID,Product Name,Sub-Category,Sales,Profit,Discount\n2025-01-01,123,456,789,Desk,Tables,100,15,0.2\n")
        mapping = ds["settings"]["mapping"]
        self.assertEqual(mapping["sales"], "Sales")
        self.assertEqual(mapping["sub_category"], "Sub-Category")
        self.assertEqual(ds["working"].iloc[0]["Customer ID"], "456")
        self.assertEqual(context(ds)["metrics"]["total_profit"], 15)

    def test_kaggle_auto_sales_column_mapping_and_timestamp_conversion(self):
        csv_bytes = (
            b"ORDERNUMBER,QUANTITYORDERED,PRICEEACH,ORDERLINENUMBER,SALES,ORDERDATE,STATUS,PRODUCTLINE,PRODUCTCODE,CUSTOMERNAME,CITY,STATE,COUNTRY,TERRITORY,DEALSIZE\n"
            b"10107,30,95.70,2,2871.00,2/24/2003 0:00,Shipped,Motorcycles,S10_1678,Land of Toys Inc.,NYC,NY,USA,NA,Small\n"
        )
        ds = dataset(csv_bytes)
        mapping = ds["settings"]["mapping"]
        self.assertEqual(mapping["order_id"], "ORDERNUMBER")
        self.assertEqual(mapping["quantity"], "QUANTITYORDERED")
        self.assertEqual(mapping["unit_price"], "PRICEEACH")
        self.assertEqual(mapping["product_id"], "PRODUCTCODE")
        self.assertEqual(mapping["category"], "PRODUCTLINE")
        self.assertEqual(mapping["customer_id"], "CUSTOMERNAME")
        self.assertEqual(mapping["segment"], "DEALSIZE")
        self.assertEqual(mapping["sales"], "SALES")
        self.assertEqual(mapping["country"], "COUNTRY")
        self.assertEqual(mapping["region"], "TERRITORY")
        self.assertEqual(str(ds["working"].iloc[0]["ORDERNUMBER"]), "10107")
        self.assertEqual(str(ds["working"].iloc[0]["PRODUCTCODE"]), "S10_1678")

    def test_total_sale_units_sold_sales_channel_mapping(self):
        csv_bytes = (
            b"Order ID,Units Sold,Total Sale,Sales Channel,Order Date\n"
            b"ORD-001,15,450.50,Online,2025-05-10\n"
        )
        ds = dataset(csv_bytes)
        mapping = ds["settings"]["mapping"]
        self.assertEqual(mapping["order_id"], "Order ID")
        self.assertEqual(mapping["quantity"], "Units Sold")
        self.assertEqual(mapping["sales"], "Total Sale")
        self.assertEqual(mapping["segment"], "Sales Channel")
        self.assertEqual(mapping["order_date"], "Order Date")
        m = context(ds)["metrics"]
        self.assertEqual(m["total_revenue"], 450.50)
        self.assertEqual(m["units_sold"], 15)

    def test_supplied_sales_profit_priority_and_disclosure(self):
        ds = dataset(b"sales,profit,quantity,unit_price,unit_cost,total_cost,discount\n80,12,2,50,20,45,0.2\n")
        m = context(ds)["metrics"]
        self.assertEqual(m["total_revenue"], 80)  # Never subtract 20% again.
        self.assertEqual(m["total_cost"], 45)  # Never multiply a row total again.
        self.assertEqual(m["total_profit"], 12)  # Source takes priority over 80-45.
        self.assertEqual(m["profit_margin"], 15)
        self.assertEqual((m["sales_conflicts"], m["profit_conflicts"]), (1, 1))
        self.assertTrue(any("Discount" in n for n in m["notices"]))

    def test_missing_profit_is_not_filled_using_costs(self):
        m = context(dataset(b"sales,profit,total_cost\n100,20,70\n50,,30\n"))["metrics"]
        self.assertEqual(m["profit_basis"], "reported")
        self.assertIsNone(m["total_profit"])
        self.assertIsNone(m["profit_margin"])
        self.assertEqual(m["missing_profit_records"], 1)

    def test_profit_without_costs_and_negative_profit(self):
        m = context(dataset(b"sales,profit\n100,-25\n50,5\n"))["metrics"]
        self.assertIsNone(m["total_cost"])
        self.assertEqual(m["total_profit"], -20)
        self.assertAlmostEqual(m["profit_margin"], -20 / 150 * 100)
        zero = context(dataset(b"sales,profit\n0,-5\n"))["metrics"]
        self.assertEqual(zero["total_profit"], -5)
        self.assertIsNone(zero["profit_margin"])

    def test_missing_sales_not_backfilled_from_quantity(self):
        m = context(dataset(b"sales,profit,quantity,unit_price\n100,20,1,100\n,50,2,100\n"))["metrics"]
        self.assertEqual(m["total_revenue"], 100)
        self.assertEqual(m["total_profit"], 20)
        self.assertEqual(m["excluded_records"], 1)
        self.assertTrue(any("without valid sales" in n for n in m["notices"]))

    def test_extra_columns_preserved_but_unavailable_for_analysis(self):
        ds = dataset(b"sales,category,secret_score,note\n100,A,8,first\n100,A,9,second\n")
        ctx = context(ds)
        self.assertIn("secret_score", ds["original"])
        self.assertIn("secret_score", ctx["source_data"])
        self.assertNotIn("secret_score", ctx["data"])
        self.assertEqual(ctx["quality"]["Duplicate rows beyond first"], 0)
        with self.assertRaises(ValueError):
            build_figure(ds["working"], spec("Histogram", "secret_score"), ds["settings"]["mapping"])
        with self.assertRaisesRegex(ValueError, "outside"):
            forecast(ctx, target="secret_score")

    def test_ambiguous_sales_aliases_require_mapping(self):
        ds = dataset(b"Sales,Revenue,Profit\n100,200,20\n")
        self.assertIsNone(ds["settings"]["mapping"]["sales"])
        self.assertIsNone(context(ds)["metrics"]["total_revenue"])

    def test_legacy_mapping_and_template_reuse(self):
        ds = dataset()
        with tempfile.TemporaryDirectory() as directory:
            doc = save_template("Legacy layout", "", ds["settings"], directory=directory)
            old = {"order_date": "date", "sales": "revenue", "product_name": "product"}
            doc["settings"]["mapping"] = {old.get(k, k): v for k, v in doc["settings"]["mapping"].items()}
            self.assertIn("order_date", validate(doc)["settings"]["mapping"])
            _, restored, warnings = compatible_settings(ds["working"], ds["settings"], doc)
            self.assertFalse(warnings)
            self.assertEqual(restored["mapping"]["product_name"], "product")
        with self.assertRaises(ValueError):
            canonical_mapping({"sales": "Sales", "revenue": "Revenue"})

    def test_template_cannot_restore_unmapped_chart_filter_or_model(self):
        ds = dataset(b"sales,extra\n100,1\n200,2\n")
        with tempfile.TemporaryDirectory() as directory:
            saved = deepcopy(ds["settings"])
            saved["charts"] = [spec("Histogram", "extra")]
            saved["filters"] = {"extra": {"kind": "number", "range": [1, 2]}}
            saved["models"]["target"] = "extra"
            doc = save_template("Old arbitrary columns", "", saved, directory=directory)
            _, restored, warnings = compatible_settings(ds["working"], ds["settings"], doc)
            self.assertFalse(restored["charts"])
            self.assertFalse(restored["filters"])
            self.assertIsNone(restored["models"].get("target"))
            self.assertEqual(len(warnings), 3)

    def test_mixed_currency_blocks_raw_monetary_charts_and_models(self):
        ds = dataset(b"order_date,sales,profit,currency\n2025-01-01,100,20,INR\n2025-02-01,200,50,USD\n")
        ctx = context(ds)
        self.assertIsNone(ctx["metrics"]["total_profit"])
        with self.assertRaisesRegex(ValueError, "currency"):
            build_figure(ctx["data"], spec("Histogram", "sales"), ctx["settings"]["mapping"], False)
        with self.assertRaisesRegex(ValueError, "currency"):
            forecast(ctx, target="profit")

    def test_report_uses_reported_profit_label_and_formula(self):
        ctx = context(dataset(b"sales,profit\n100,12\n"))
        report = assemble_report(ctx, "Test", [], [])
        metrics = {row["Metric"]: row for row in report["metrics"]}
        self.assertEqual(metrics["Reported profit"]["Value"], "12.00")
        self.assertIn("supplied row profit", metrics["Reported profit"]["Explanation"])
        self.assertNotIn("Gross profit", metrics)
        self.assertIn(b"Reported profit margin", html_bytes(report))

    def test_unknown_only_dataset_has_no_business_results(self):
        ctx = context(dataset(b"notes,score\nhello,15\nworld,20\n"))
        self.assertEqual(len(ctx["data"].columns), 0)
        self.assertEqual(ctx["scope"]["rows"], 2)
        self.assertIsNone(ctx["metrics"]["total_revenue"])

    def test_full_example_ui_and_supported_filters(self):
        app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
        app.session_state["dataset"] = dataset((ROOT / "data" / "sample_sales_catalogue.csv").read_bytes())
        app.session_state["page"] = "Dashboard"
        app.run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual([m.label for m in app.metric], ["Sales", "Reported profit", "Reported profit margin", "Orders", "Units sold", "Average order value"])
        self.assertEqual([m.value for m in app.metric], ["5,180.00", "1,920.00", "37.1%", "8", "17.00", "647.50"])
        app.button(key="nav_Reports").click().run(timeout=30)
        self.assertFalse(app.exception)
        app.button(key="nav_Data").click().run(timeout=30)
        self.assertEqual(len(app.dataframe[0].value), 20)

    def test_unknown_fields_show_mapping_guidance(self):
        app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
        app.session_state["dataset"] = dataset(b"notes,score\nhello,15\nworld,20\n")
        for page in ("Dashboard", "Explore", "Reports"):
            app.session_state["page"] = page
            app.run(timeout=30)
            self.assertFalse(app.exception)
            self.assertTrue(any("No supported fields" in item.value for item in app.info))

    def test_adapt_column_type_currency_dates_and_text(self):
        from core.automation import adapt_column_type
        import pandas as pd

        # Currency string to numeric
        curr_series = pd.Series(["$1,200.50", " ₹ 450.00 ", "-$50.25", None])
        converted, ok, reason = adapt_column_type(curr_series, "sales")
        self.assertTrue(ok)
        self.assertEqual(converted.dropna().tolist(), [1200.50, 450.00, -50.25])

        # Invalid string mapped to numeric fails gracefully
        bad_series = pd.Series(["$100.00", "not_a_number"])
        converted, ok, reason = adapt_column_type(bad_series, "sales")
        self.assertFalse(ok)
        self.assertIn("Cannot convert", reason)

        # Slash dates to datetime
        date_series = pd.Series(["10/28/2026", "10/29/2026", ""])
        converted, ok, reason = adapt_column_type(date_series, "order_date")
        self.assertTrue(ok)
        self.assertEqual(str(converted.iloc[0].date()), "2026-10-28")

        # Integer code to text
        id_series = pd.Series([101, 102])
        converted, ok, reason = adapt_column_type(id_series, "order_id")
        self.assertTrue(ok)
        self.assertEqual(converted.tolist(), ["101", "102"])

    def test_manual_mapping_and_reset_to_auto(self):
        from core.automation import detect_roles
        csv_bytes = b"my_custom_code,custom_units,custom_price\nORD-1,10,25.5\nORD-2,5,30.0\n"
        ds = dataset(csv_bytes)
        # Initially unmapped
        self.assertIsNone(ds["settings"]["mapping"].get("order_id"))

        # Apply manual mapping
        ds["settings"]["mapping"]["order_id"] = "my_custom_code"
        ds["settings"]["mapping"]["quantity"] = "custom_units"
        ds["settings"]["mapping"]["unit_price"] = "custom_price"
        ctx = context(ds)
        self.assertEqual(ctx["metrics"]["units_sold"], 15)

        # Reset to auto-detection
        auto_map, _ = detect_roles(ds["working"])
        ds["settings"]["mapping"] = auto_map
        self.assertIsNone(ds["settings"]["mapping"].get("order_id"))


if __name__ == "__main__":
    unittest.main()
