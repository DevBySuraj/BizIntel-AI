"""Suitability gates and explainable analyses, independent of Streamlit."""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from core.forecasting import prepare_time_series, run_forecasting_pipeline
from core.data_cleaning import missing_mask
from core.catalogue import check_measure


def forecast(context, frequency="M", horizon=3, target=None):
    data, mapping, metrics = context["data"], context["settings"]["mapping"], context["metrics"]
    if target is not None and target not in data:
        raise ValueError("The selected forecast target is outside the mapped catalogue or unavailable.")
    check_measure(target or "@revenue", mapping, metrics["monetary_ok"])
    date = mapping.get("order_date")
    if date not in data or not pd.api.types.is_datetime64_any_dtype(data[date]):
        raise ValueError("Forecasting needs a mapped date and numeric target.")
    values = data[target] if target and target in data else metrics["revenue_series"]
    if not pd.api.types.is_numeric_dtype(values) or values.isna().any() or data[date].isna().any() or not np.isfinite(values.astype(float)).all():
        raise ValueError("Forecasting needs complete dates and finite target values in this scope.")
    if frequency not in ("D", "W", "M") or not 1 <= horizon <= 12:
        raise ValueError("Choose a daily/weekly/monthly frequency and horizon of 1-12.")
    source = pd.DataFrame({"date": data[date], "target": values})
    ts = prepare_time_series(source, "date", "target", frequency)
    if len(ts) < 12:
        raise ValueError(f"Only {len(ts)} observed periods; at least 12 are needed (6+ train, 3+ test).")
    periods = pd.PeriodIndex(ts["Period"], freq=frequency)
    if len(pd.period_range(periods.min(), periods.max(), freq=frequency)) != len(periods):
        raise ValueError("Missing periods are unknown, not zero. Try a coarser interval or prepare a justified complete series.")
    start, end = source["date"].min().normalize(), source["date"].max().normalize()
    if frequency in ("W", "M") and (start > periods.min().start_time.normalize() or end < periods.max().end_time.normalize()):
        raise ValueError("First/last period is partial. Filter to completed periods or choose a suitable interval.")
    if end >= pd.Timestamp.now().normalize():
        raise ValueError("The latest period is current/future; filter to completed historical periods.")
    if not np.isfinite(ts["Actual"]).all():
        raise ValueError("Aggregated values exceeded the numeric range.")
    test_size = max(3, int(np.ceil(len(ts) * .2)))
    models = {}
    for name in ("Naive (Last Value)", "Moving Average", "Linear Trend"):
        result = run_forecasting_pipeline(ts, name, test_size, horizon, frequency)
        if not np.isfinite(result["future"]["Forecast"]).all():
            raise ValueError("Forecast exceeded the numeric range.")
        models[name] = result
    comparison = pd.DataFrame([{"Model": name, "MAE": r["metrics"]["mae"], "RMSE": r["metrics"]["rmse"]}
                               for name, r in models.items()])
    return {"models": models, "comparison": comparison, "series": ts,
            "recommended": comparison.sort_values("MAE").iloc[0]["Model"],
            "notes": "Last 20% (minimum 3 periods) held out chronologically. Recommendation uses this same holdout, not an independent final test. Future forecasts refit all history. No causal guarantee or confidence interval. Source completeness cannot be proven from dates alone."}


def segmentation(context, clusters=3):
    data, mapping, metrics = context["data"], context["settings"]["mapping"], context["metrics"]
    customer, order, date = [mapping.get(role) for role in ("customer_id", "order_id", "order_date")]
    if any(c not in data for c in (customer, order, date)) or not pd.api.types.is_datetime64_any_dtype(data[date]):
        raise ValueError("Customer analysis needs customer IDs, order IDs, dates and revenue.")
    valid = ~missing_mask(data[customer]) & ~missing_mask(data[order]) & data[date].notna() & metrics["usable_mask"]
    bad_customers = data.loc[~valid & ~missing_mask(data[customer]), customer]
    valid &= ~data[customer].isin(bad_customers)
    conflicts = data.groupby(order)[customer].nunique()
    conflicted_customers = data.loc[data[order].isin(conflicts[conflicts > 1].index), customer]
    valid &= ~data[customer].isin(conflicted_customers)
    table = pd.DataFrame({"customer": data.loc[valid, customer], "order": data.loc[valid, order],
                          "date": data.loc[valid, date], "revenue": metrics["revenue_series"][valid]})
    if table.empty:
        raise ValueError("No complete customer transactions are available.")
    reference = table["date"].max().normalize() + pd.Timedelta(days=1)
    summary = table.groupby("customer").agg(last_date=("date", "max"), frequency=("order", "nunique"), monetary=("revenue", "sum"))
    summary["recency"] = (reference - summary["last_date"]).dt.days
    summary = summary[["recency", "frequency", "monetary"]]
    finite = np.isfinite(summary).all(axis=1)
    summary = summary.loc[finite]
    notes = f"Reference date: {reference:%Y-%m-%d}. Excluded {len(data) - int(valid.sum())} incomplete/ambiguous transaction rows; {int((~finite).sum())} nonfinite customer profiles. Monetary values include returns."
    result = {"customers": summary.reset_index(), "profiles": pd.DataFrame(), "silhouette": None,
              "notes": notes, "reason": None}
    features = [c for c in summary if summary[c].nunique() > 1]
    if len(summary) < 20 or not features or not 2 <= clusters <= 6 or len(summary.drop_duplicates()) < clusters:
        result["reason"] = f"{len(summary)} eligible customers. Clustering needs at least 20, varying features and enough distinct profiles for 2-6 clusters."
        return result
    scaled = StandardScaler().fit_transform(summary[features])
    labels = KMeans(n_clusters=clusters, random_state=42, n_init=10).fit_predict(scaled)
    summary["Group"] = [f"Group {i + 1}" for i in labels]
    result["customers"] = summary.reset_index()
    result["profiles"] = summary.groupby("Group").agg(Customers=("recency", "size"), Recency=("recency", "mean"),
                                                      Frequency=("frequency", "mean"), Monetary=("monetary", "mean")).reset_index()
    if 1 < len(set(labels)) < len(labels):
        result["silhouette"] = float(silhouette_score(scaled, labels, sample_size=min(len(labels), 5000), random_state=42))
    result["notes"] += " K-means on standardized varying RFM features; no log transform; fixed seed 42. Groups describe behavior, not personal worth. Silhouette is separation, not accuracy."
    return result


def anomalies(data, column, multiplier=1.5):
    if column not in data or not pd.api.types.is_numeric_dtype(data[column]):
        raise ValueError("Choose a numeric measure for anomaly investigation.")
    if not .5 <= multiplier <= 5:
        raise ValueError("Choose an IQR multiplier between 0.5 and 5.")
    values = data[column].astype(float)
    values = values[np.isfinite(values)]
    if len(values) < 20 or values.nunique() < 2:
        raise ValueError("IQR needs at least 20 finite observations and a nonconstant measure.")
    q1, q3 = values.quantile([.25, .75])
    iqr = q3 - q1
    if iqr <= 0 or not np.isfinite(iqr):
        raise ValueError("The interquartile range is zero/undefined; use another measure.")
    lower, upper = q1 - multiplier * iqr, q3 + multiplier * iqr
    if not np.isfinite([lower, upper]).all():
        raise ValueError("IQR bounds exceed the numeric range; choose a smaller-scale measure.")
    flagged = values[(values < lower) | (values > upper)]
    table = pd.DataFrame({"Original record": flagged.index + 1, "Value": flagged.values,
                          "Lower bound": lower, "Upper bound": upper,
                          "Reason": ["Below lower IQR fence" if v < lower else "Above upper IQR fence" for v in flagged]})
    return {"flagged": table, "lower": float(lower), "upper": float(upper), "excluded": len(data) - len(values),
            "notes": "Q1/Q3 +/- multiplier × IQR. Original record is the parsed data-row position, not a physical CSV line. Flags invite investigation; they do not prove error or fraud. No rows removed."}
