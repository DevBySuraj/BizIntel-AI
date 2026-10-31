"""Tests for Step 6: Sales Forecasting, time-series split, and metric accuracy."""

from datetime import datetime, timedelta
import unittest

import numpy as np
import pandas as pd

from core.forecasting import (
    chronological_split,
    evaluate_forecast,
    forecast_linear_trend,
    forecast_moving_average,
    forecast_naive,
    prepare_time_series,
    run_forecasting_pipeline,
)


class ForecastingMathTests(unittest.TestCase):
    def setUp(self):
        # 5 chronological days
        dates = [datetime(2026, 10, 1) + timedelta(days=i) for i in range(5)]
        self.df = pd.DataFrame({
            "date": dates,
            "sales": [10.0, 20.0, 30.0, 40.0, 50.0],
        })

    def test_prepare_time_series_daily_sum(self):
        ts = prepare_time_series(self.df, "date", "sales", frequency="D", aggregation="sum")
        self.assertEqual(len(ts), 5)
        self.assertEqual(ts["Actual"].tolist(), [10.0, 20.0, 30.0, 40.0, 50.0])

    def test_prepare_time_series_unconverted_type_rejected(self):
        df_text = pd.DataFrame({"date": ["2026-10-01"], "sales": ["10"]})
        with self.assertRaises(ValueError):
            prepare_time_series(df_text, "date", "sales")

    def test_chronological_split_preserves_order(self):
        ts = prepare_time_series(self.df, "date", "sales")
        train, test = chronological_split(ts, test_size=2)
        self.assertEqual(len(train), 3)
        self.assertEqual(len(test), 2)
        # Train: 10, 20, 30. Test: 40, 50
        self.assertEqual(train["Actual"].tolist(), [10.0, 20.0, 30.0])
        self.assertEqual(test["Actual"].tolist(), [40.0, 50.0])
        # Verify chronological order
        self.assertTrue(train["Period"].max() < test["Period"].min())

    def test_chronological_split_insufficient_points(self):
        short = self.df.iloc[:2].copy()
        ts = prepare_time_series(short, "date", "sales")
        with self.assertRaises(ValueError):
            chronological_split(ts, test_size=1)

    def test_naive_forecast(self):
        train = pd.DataFrame({"Actual": [10.0, 20.0, 35.0]})
        preds = forecast_naive(train, horizon=3)
        self.assertEqual(preds.tolist(), [35.0, 35.0, 35.0])

    def test_moving_average_forecast(self):
        train = pd.DataFrame({"Actual": [10.0, 20.0, 30.0, 40.0]})
        # window 2: mean of (30, 40) = 35.0
        preds = forecast_moving_average(train, horizon=2, window=2)
        self.assertEqual(preds.tolist(), [35.0, 35.0])

    def test_linear_trend_forecast(self):
        # y = 10*t + 10 for t = 0, 1, 2 (y = 10, 20, 30)
        train = pd.DataFrame({"Actual": [10.0, 20.0, 30.0]})
        preds, slope, intercept = forecast_linear_trend(train, horizon=2)
        self.assertAlmostEqual(slope, 10.0)
        self.assertAlmostEqual(intercept, 10.0)
        # t = 3 -> 40, t = 4 -> 50
        self.assertAlmostEqual(preds[0], 40.0)
        self.assertAlmostEqual(preds[1], 50.0)

    def test_evaluation_metrics(self):
        actuals = np.array([100.0, 200.0])
        predictions = np.array([110.0, 180.0])
        # Errors: -10, +20
        # MAE: (10 + 20) / 2 = 15.0
        # RMSE: sqrt((100 + 400) / 2) = sqrt(250) = 15.811388
        # MAPE: ((10/100 + 20/200) / 2) * 100 = ((0.10 + 0.10) / 2) * 100 = 10.0%
        metrics = evaluate_forecast(actuals, predictions)
        self.assertAlmostEqual(metrics["mae"], 15.0)
        self.assertAlmostEqual(metrics["rmse"], 15.811388, places=4)
        self.assertAlmostEqual(metrics["mape"], 10.0)

    def test_full_pipeline_execution(self):
        ts = prepare_time_series(self.df, "date", "sales")
        result = run_forecasting_pipeline(ts, "Linear Trend", test_size=1, horizon=2)
        self.assertIn("train", result)
        self.assertIn("test", result)
        self.assertIn("future", result)
        self.assertEqual(len(result["future"]), 2)
        self.assertIn("mae", result["metrics"])


# Automatic workflow UI regressions are maintained in test_workflows.py.
# The former manual-conversion/planned-page expectations were superseded by the PRD.


if __name__ == "__main__":
    unittest.main()

