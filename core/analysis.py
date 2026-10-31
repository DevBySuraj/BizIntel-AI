"""One analysis scope shared by cards, charts, findings, and reports."""
from copy import deepcopy
import pandas as pd
from core.dashboard import filter_data
from core.kpi import analyze_kpis, compute_sales_growth
from core.automation import fingerprint
from core.catalogue import analysis_table
from core.data_cleaning import quality_summary


def apply_filters(data, filters):
    result = data.copy(deep=True)
    for column, rule in filters.items():
        kind = rule["kind"]
        common = {"include_missing": rule.get("include_missing", False)}
        if kind == "category":
            result = filter_data(result, category=column, selected_values=rule["values"], **common)
        elif kind == "number":
            result = filter_data(result, numeric=column, number_range=rule["range"], **common)
        elif kind == "date":
            bounds = rule["range"]
            if rule.get("mode") == "last_days":
                end = data[column].max()
                bounds = [end - pd.Timedelta(days=rule.get("days", 30) - 1), end]
            result = filter_data(result, date=column, date_range=bounds, **common)
        else:
            raise ValueError("Unknown filter kind.")
    return result


def context(dataset):
    settings = dataset["settings"]
    supported = analysis_table(dataset["working"], settings["mapping"])
    filters = {c: r for c, r in settings["filters"].items() if c in supported}
    data = apply_filters(supported, filters)
    source_data = dataset["working"].loc[data.index].copy()
    metrics = analyze_kpis(data, settings["mapping"], settings["currency"])
    growth = pd.DataFrame()
    date = settings["mapping"].get("order_date")
    if date in data and pd.api.types.is_datetime64_any_dtype(data[date]):
        growth = compute_sales_growth(data, date, metrics["revenue_series"], metrics["usable_mask"])
    return {"data": data, "source_data": source_data, "metrics": metrics, "growth": growth,
            "quality": quality_summary(source_data), "settings": deepcopy(settings),
            "scope": {"dataset": dataset["name"], "version": dataset["revision"],
                      "rows": len(data), "total_rows": len(dataset["working"]),
                      "filters": deepcopy(filters), "currency": metrics["currency"],
                      "preparation": deepcopy(dataset["history"]),
                      "id": fingerprint(dataset["source_id"], dataset["revision"], settings)}}
