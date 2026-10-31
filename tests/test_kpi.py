"""Tests for Step 5: Business KPIs, formula accuracy, and UI integration."""

import unittest

import numpy as np
import pandas as pd

from core.kpi import (
    compute_dimension_breakdown,
    compute_kpis,
    compute_sales_growth,
    detect_kpi_columns,
)


class KpiComputationTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "order_id": ["O1", "O1", "O2", "O3"],
            "qty": [2.0, 3.0, 1.0, 4.0],
            "price": [100.0, 150.0, 200.0, 50.0],
            "cost": [60.0, 90.0, 120.0, 30.0],
            "date": pd.to_datetime(["2026-10-01", "2026-10-01", "2026-10-02", "2026-10-03"]),
            "region": ["North", "North", "South", "East"],
        })

    def test_revenue_and_profit_calculation(self):
        # Rev = (2*100) + (3*150) + (1*200) + (4*50) = 200 + 450 + 200 + 200 = 1050
        # Cost = (2*60) + (3*90) + (1*120) + (4*30) = 120 + 270 + 120 + 120 = 630
        # Profit = 1050 - 630 = 420
        # Margin = (420 / 1050) * 100 = 40.0%
        # Orders = 3 (O1, O2, O3)
        # AOV = 1050 / 3 = 350.0
        kpis = compute_kpis(
            self.df,
            qty_col="qty",
            price_col="price",
            cost_col="cost",
            order_col="order_id",
        )
        self.assertAlmostEqual(kpis["total_revenue"], 1050.0)
        self.assertAlmostEqual(kpis["total_cost"], 630.0)
        self.assertAlmostEqual(kpis["total_profit"], 420.0)
        self.assertAlmostEqual(kpis["profit_margin"], 40.0)
        self.assertEqual(kpis["total_orders"], 3)
        self.assertAlmostEqual(kpis["aov"], 350.0)
        self.assertEqual(kpis["usable_records"], 4)
        self.assertEqual(kpis["excluded_records"], 0)

    def test_precalculated_revenue_mode(self):
        df_rev = self.df.copy()
        df_rev["revenue"] = [200.0, 450.0, 200.0, 200.0]
        kpis = compute_kpis(df_rev, revenue_col="revenue", order_col="order_id")
        self.assertAlmostEqual(kpis["total_revenue"], 1050.0)
        self.assertIsNone(kpis["total_profit"])
        self.assertIsNone(kpis["profit_margin"])

    def test_missing_and_invalid_data_exclusion(self):
        dirty = self.df.copy()
        dirty.loc[1, "qty"] = np.nan
        dirty.loc[2, "price"] = np.nan
        kpis = compute_kpis(dirty, qty_col="qty", price_col="price")
        # Included: row 0 (2*100=200) and row 3 (4*50=200) -> 400
        self.assertAlmostEqual(kpis["total_revenue"], 400.0)
        self.assertEqual(kpis["usable_records"], 2)
        self.assertEqual(kpis["excluded_records"], 2)

    def test_sales_growth(self):
        kpis = compute_kpis(self.df, qty_col="qty", price_col="price")
        growth = compute_sales_growth(self.df, "date", kpis["revenue_series"], kpis["usable_mask"])
        self.assertEqual(len(growth), 1)  # One incomplete calendar month.
        self.assertTrue(pd.isna(growth.loc[0, "Growth %"]))

    def test_dimension_breakdown(self):
        kpis = compute_kpis(self.df, qty_col="qty", price_col="price")
        breakdown = compute_dimension_breakdown(
            self.df, "region", kpis["revenue_series"], kpis["usable_mask"]
        )
        # North: 650 (61.9%), South: 200 (19.0%), East: 200 (19.0%)
        self.assertEqual(breakdown.iloc[0]["region"], "North")
        self.assertAlmostEqual(breakdown.iloc[0]["Revenue"], 650.0)
        self.assertAlmostEqual(breakdown["Share %"].sum(), 100.0)

    def test_detect_kpi_columns(self):
        cols = detect_kpi_columns(self.df)
        self.assertEqual(cols["quantity"], "qty")
        self.assertIsNone(cols["price"])  # Ambiguous unit-versus-total name.
        self.assertIsNone(cols["cost"])
        self.assertEqual(cols["order_date"], "date")
        self.assertEqual(cols["order_id"], "order_id")


# Automatic workflow UI regressions are maintained in test_workflows.py.
# The former manual-conversion/planned-page expectations were superseded by the PRD.


if __name__ == "__main__":
    unittest.main()
