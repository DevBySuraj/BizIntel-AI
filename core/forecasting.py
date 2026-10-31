"""Sales forecasting engine: pure time-series modeling without UI dependencies.

Implements:
1. Chronological aggregation (Daily, Weekly, Monthly)
2. Strict chronological train/test split (no future data leakage)
3. Three interpretable forecasting models:
   - Naive Baseline: y_hat_{t+h} = y_t
   - Moving Average: rolling mean of last k periods
   - Linear Trend: Ordinary Least Squares (OLS) over time index t
4. Performance evaluation metrics:
   - Mean Absolute Error (MAE)
   - Root Mean Squared Error (RMSE)
   - Mean Absolute Percentage Error (MAPE)
5. Out-of-sample future horizon forecasting
"""

from typing import Dict, List, Tuple
import numpy as np
import pandas as pd


def prepare_time_series(
    df: pd.DataFrame,
    date_col: str,
    target_col: str,
    frequency: str = "D",
    aggregation: str = "sum",
) -> pd.DataFrame:
    """Validate, clean, and aggregate a time series chronologically.
    
    Args:
        df: Input DataFrame
        date_col: Name of datetime column
        target_col: Name of numeric target column
        frequency: 'D' (daily), 'W' (weekly), or 'M' (monthly)
        aggregation: 'sum' or 'mean'
    """
    if date_col not in df.columns:
        raise ValueError(f"Date column '{date_col}' not found in dataset.")
    if target_col not in df.columns:
        raise ValueError(f"Target column '{target_col}' not found in dataset.")
    if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
        raise ValueError(f"Date column '{date_col}' must be converted to datetime in Prepare.")
    if not pd.api.types.is_numeric_dtype(df[target_col]):
        raise ValueError(f"Target column '{target_col}' must be converted to numbers in Prepare.")

    valid_mask = df[date_col].notna() & df[target_col].notna() & np.isfinite(df[target_col])
    if not valid_mask.any():
        raise ValueError("No valid rows found with both non-empty dates and finite numbers.")

    sub = df.loc[valid_mask, [date_col, target_col]].copy()
    sub[target_col] = sub[target_col].astype(float)

    # Floor to frequency
    if frequency == "D":
        sub["Period"] = sub[date_col].dt.floor("D")
    elif frequency == "W":
        sub["Period"] = sub[date_col].dt.to_period("W").dt.start_time
    elif frequency == "M":
        sub["Period"] = sub[date_col].dt.to_period("M").dt.start_time
    else:
        raise ValueError(f"Unsupported frequency '{frequency}'. Choose 'D', 'W', or 'M'.")

    # Aggregate
    if aggregation == "sum":
        ts = sub.groupby("Period", as_index=False)[target_col].sum()
    elif aggregation == "mean":
        ts = sub.groupby("Period", as_index=False)[target_col].mean()
    else:
        raise ValueError(f"Unsupported aggregation '{aggregation}'. Choose 'sum' or 'mean'.")

    ts = ts.sort_values("Period").reset_index(drop=True)
    ts = ts.rename(columns={target_col: "Actual"})
    return ts


def chronological_split(
    ts: pd.DataFrame,
    test_size: int = 1,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split time series strictly in chronological order without shuffling.
    
    Prevents lookahead bias / data leakage.
    """
    n = len(ts)
    if n < 3:
        raise ValueError(f"Time series has only {n} points. At least 3 points are required to split.")
    if test_size < 1 or test_size >= n:
        raise ValueError(f"Test size ({test_size}) must be between 1 and {n - 1}.")

    train = ts.iloc[:-test_size].copy().reset_index(drop=True)
    test = ts.iloc[-test_size:].copy().reset_index(drop=True)
    return train, test


def evaluate_forecast(actuals: np.ndarray, predictions: np.ndarray) -> Dict[str, float]:
    """Compute standard error metrics (MAE, RMSE, MAPE)."""
    actuals = np.asarray(actuals, dtype=float)
    predictions = np.asarray(predictions, dtype=float)

    if len(actuals) == 0 or actuals.shape != predictions.shape or not np.isfinite(actuals).all() or not np.isfinite(predictions).all():
        raise ValueError("Evaluation needs nonempty matching finite actuals and predictions.")

    errors = actuals - predictions
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors ** 2)))

    # MAPE: only compute where actual != 0 to prevent division by zero
    nonzero = actuals != 0
    if np.any(nonzero):
        mape = float(np.mean(np.abs(errors[nonzero] / actuals[nonzero])) * 100.0)
    else:
        mape = None

    return {"mae": mae, "rmse": rmse, "mape": mape, "mape_records": int(nonzero.sum())}


def forecast_naive(train: pd.DataFrame, horizon: int) -> np.ndarray:
    """Naive model: future values equal the last observed train value."""
    if train.empty:
        raise ValueError("Training data is empty.")
    last_value = float(train["Actual"].iloc[-1])
    return np.full(horizon, last_value)


def forecast_moving_average(train: pd.DataFrame, horizon: int, window: int = 3) -> np.ndarray:
    """Moving average model: forecasts the mean of the last `window` observations."""
    if train.empty:
        raise ValueError("Training data is empty.")
    w = min(window, len(train))
    mean_value = float(train["Actual"].iloc[-w:].mean())
    return np.full(horizon, mean_value)


def forecast_linear_trend(train: pd.DataFrame, horizon: int) -> Tuple[np.ndarray, float, float]:
    """Linear trend model using Ordinary Least Squares: y = slope * t + intercept."""
    if len(train) < 2:
        # Fall back to naive if only 1 point
        return forecast_naive(train, horizon), 0.0, float(train["Actual"].iloc[-1])

    t_train = np.arange(len(train), dtype=float)
    y_train = train["Actual"].values.astype(float)

    # OLS fit: y = m*t + c
    slope, intercept = np.polyfit(t_train, y_train, deg=1)

    t_future = np.arange(len(train), len(train) + horizon, dtype=float)
    preds = slope * t_future + intercept
    return preds, float(slope), float(intercept)


def generate_future_dates(last_date: pd.Timestamp, horizon: int, frequency: str = "D") -> List[pd.Timestamp]:
    """Generate future period timestamps."""
    if frequency == "D":
        return [last_date + pd.Timedelta(days=i) for i in range(1, horizon + 1)]
    elif frequency == "W":
        return [last_date + pd.Timedelta(weeks=i) for i in range(1, horizon + 1)]
    elif frequency == "M":
        # Month offsets
        return [last_date + pd.DateOffset(months=i) for i in range(1, horizon + 1)]
    return [last_date + pd.Timedelta(days=i) for i in range(1, horizon + 1)]


def run_forecasting_pipeline(
    ts: pd.DataFrame,
    model_name: str,
    test_size: int = 1,
    horizon: int = 3,
    frequency: str = "D",
    ma_window: int = 3,
) -> Dict[str, any]:
    """Execute complete chronological train/test split, evaluation, and future projection.
    
    Returns train, test with predictions, future forecast, and error metrics.
    """
    if len(ts) < 3:
        raise ValueError(
            f"Dataset has only {len(ts)} historical periods. At least 3 periods are required "
            "for a chronological train/test evaluation."
        )

    # 1. Chronological Split
    train, test = chronological_split(ts, test_size=test_size)

    # 2. Fit on Train, Predict on Test
    slope = None
    intercept = None
    if model_name == "Naive (Last Value)":
        test_preds = forecast_naive(train, horizon=len(test))
    elif model_name == "Moving Average":
        test_preds = forecast_moving_average(train, horizon=len(test), window=ma_window)
    elif model_name == "Linear Trend":
        test_preds, slope, intercept = forecast_linear_trend(train, horizon=len(test))
    else:
        raise ValueError(f"Unknown model '{model_name}'.")

    test_evaluated = test.copy()
    test_evaluated["Predicted"] = test_preds
    metrics = evaluate_forecast(test_evaluated["Actual"].values, test_evaluated["Predicted"].values)

    # 3. Refit on FULL dataset to project into the true future
    if model_name == "Naive (Last Value)":
        future_preds = forecast_naive(ts, horizon=horizon)
    elif model_name == "Moving Average":
        future_preds = forecast_moving_average(ts, horizon=horizon, window=ma_window)
    elif model_name == "Linear Trend":
        future_preds, full_slope, full_intercept = forecast_linear_trend(ts, horizon=horizon)
        slope = full_slope
        intercept = full_intercept

    last_period = ts["Period"].max()
    future_dates = generate_future_dates(last_period, horizon=horizon, frequency=frequency)

    future_df = pd.DataFrame({
        "Period": future_dates,
        "Forecast": future_preds,
    })

    return {
        "train": train,
        "test": test_evaluated,
        "metrics": metrics,
        "future": future_df,
        "model_name": model_name,
        "slope": slope,
        "intercept": intercept,
    }

