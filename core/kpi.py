"""Business calculations on one scoped table, with coverage and reasons."""
import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype, is_datetime64_any_dtype
from core.automation import detect_roles, currency_status
from core.catalogue import canonical_mapping
from core.data_cleaning import missing_mask


def number(data, column):
    if column not in data or not is_numeric_dtype(data[column]):
        return pd.Series(np.nan, index=data.index, dtype=float)
    values = data[column].astype(float)
    return values.where(np.isfinite(values))


def safe_sum(values):
    if not values.notna().any():
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        total = float(values.sum(min_count=1))
    return total if np.isfinite(total) else None


def monetary_series(data, mapping):
    mapping = canonical_mapping(mapping)
    quantity = number(data, mapping.get("quantity"))
    with np.errstate(over="ignore", invalid="ignore"):
        revenue = (number(data, mapping["sales"]) if mapping.get("sales") else
                   quantity * number(data, mapping.get("unit_price")))
        cost = (number(data, mapping["total_cost"]) if mapping.get("total_cost") else
                quantity * number(data, mapping.get("unit_cost")))
    return revenue.where(np.isfinite(revenue)), cost.where(np.isfinite(cost))


def analyze_kpis(data, mapping, currency="Unspecified"):
    mapping = canonical_mapping(mapping)
    revenue, cost = monetary_series(data, mapping)
    label, monetary_ok, currency_note = currency_status(data, mapping, currency)
    reported = number(data, mapping.get("profit"))
    if not monetary_ok:
        revenue[:] = np.nan
        cost[:] = np.nan
        reported[:] = np.nan
    valid = revenue.notna()
    total = safe_sum(revenue)
    complete = bool(valid.any() and cost[valid].notna().all())
    total_cost = safe_sum(cost[valid]) if complete else None
    gross = revenue - cost
    gross = gross.where(np.isfinite(gross))
    supplied = bool(mapping.get("profit"))
    row_profit = reported.where(valid) if supplied else gross
    profit_complete = bool(valid.any() and row_profit[valid].notna().all())
    profit = safe_sum(row_profit[valid]) if profit_complete else None
    margin = profit / total * 100 if profit is not None and total is not None and total > 0 else None
    if margin is not None and not np.isfinite(margin):
        margin = None
    order_column = mapping.get("order_id")
    orders, missing_orders = None, len(data)
    if order_column in data:
        missing_orders = int(missing_mask(data[order_column]).sum())
        orders = int(data.loc[~missing_mask(data[order_column]), order_column].nunique())
    quantity = number(data, mapping.get("quantity"))
    units = safe_sum(quantity) if quantity.notna().all() else None
    aov = total / orders if (total is not None and orders and not missing_orders and valid.all()) else None
    revenue_mode = (f"Sum of row sales: {mapping['sales']}" if mapping.get("sales") else
                    f"Sum of quantity × unit price: {mapping.get('quantity')} × {mapping.get('unit_price')}. "
                    "Assumes unit price is the realized selling price; discount is not applied.")
    cost_mode = (f"Sum of row cost of goods: {mapping['total_cost']}" if mapping.get("total_cost") else
                 f"Sum of quantity × unit cost: {mapping.get('quantity')} × {mapping.get('unit_cost')}")
    profit_label = "Reported profit" if supplied else "Gross profit"
    margin_label = "Reported profit margin" if supplied else "Gross margin"
    profit_mode = (f"Sum of supplied row profit: {mapping['profit']}; source definition, not assumed gross or net."
                   if supplied else "Gross profit = sales - corresponding cost of goods; excludes operating expenses.")
    notices = []
    def disagreement(left, right, explanation):
        comparable = left.notna() & right.notna()
        count = int((comparable & ~np.isclose(left, right, rtol=1e-6, atol=0.01)).sum())
        if count:
            notices.append(f"{count} comparable rows differ: {explanation}")
        return count
    with np.errstate(over="ignore", invalid="ignore"):
        derived_sales = quantity * number(data, mapping.get("unit_price"))
    derived_sales = derived_sales.where(np.isfinite(derived_sales))
    sales_conflicts = disagreement(revenue, derived_sales,
        "supplied sales versus quantity × unit price. Supplied sales takes priority; discounts/rounding may explain this.") if mapping.get("sales") and monetary_ok else 0
    profit_conflicts = disagreement(reported, gross,
        "reported profit versus sales minus cost of goods. Reported profit takes priority; the source may use a different profit definition.") if supplied and monetary_ok else 0
    if mapping.get("discount"):
        notices.append("Discount is informational and never deducted again. Confirm whether the source uses a fraction, percentage or monetary amount.")
    if int((~valid & reported.notna()).sum()):
        notices.append("Reported profit on rows without valid sales is excluded so profit and margin use the same sales cohort.")
    reasons = {
        "total_revenue": currency_note if not monetary_ok else "Map row sales or numeric quantity and realized unit price; at least one finite result is needed.",
        "total_cost": "Costs must cover every record with valid sales. Map total cost or quantity and unit cost.",
        "total_profit": currency_note if not monetary_ok else (profit_mode + " Profit must cover every record with valid sales."),
        "profit_margin": f"{profit_label} / positive sales × 100; requires matching complete profit coverage.",
        "total_orders": "Map order IDs. Records are not necessarily orders.",
        "units_sold": "Sum of quantity across all scoped records; requires complete quantity coverage. Returns reduce the total.",
        "aov": "Sales / distinct orders needs sales and nonblank order IDs for every scoped record.",
    }
    return dict(total_revenue=total, total_cost=total_cost, total_profit=profit,
                profit_margin=margin, total_orders=orders, units_sold=units, aov=aov, total_records=len(data),
                usable_records=int(valid.sum()), excluded_records=int((~valid).sum()),
                missing_cost_records=int((valid & cost.isna()).sum()), missing_order_records=missing_orders,
                missing_profit_records=int((valid & row_profit.isna()).sum()),
                return_records=int((revenue < 0).sum()), revenue_series=revenue, cost_series=cost,
                profit_series=row_profit, profit_basis="reported" if supplied else "calculated_gross",
                profit_label=profit_label, margin_label=margin_label, profit_mode=profit_mode,
                notices=notices, sales_conflicts=sales_conflicts, profit_conflicts=profit_conflicts,
                usable_mask=valid, revenue_mode=revenue_mode, cost_mode=cost_mode,
                currency=label, currency_note=currency_note, monetary_ok=monetary_ok, reasons=reasons)


def detect_kpi_columns(df):
    roles, _ = detect_roles(df)
    return {**roles, "price": roles["unit_price"], "cost": roles["unit_cost"]}


def compute_kpis(df, qty_col=None, price_col=None, cost_col=None, revenue_col=None, order_col=None, total_cost_col=None):
    """Compatibility entry point; cost_col always means unit cost."""
    if df.empty:
        raise ValueError("Cannot calculate KPIs on an empty dataset.")
    for column in (qty_col, price_col, cost_col, revenue_col, total_cost_col):
        if column and (column not in df or not is_numeric_dtype(df[column])):
            raise ValueError(f"Column '{column}' must be converted to numbers first.")
    if not revenue_col and not (qty_col and price_col):
        raise ValueError("Provide Revenue or Quantity and Unit Price columns.")
    return analyze_kpis(df, {"quantity": qty_col, "unit_price": price_col, "unit_cost": cost_col,
                           "total_cost": total_cost_col, "revenue": revenue_col, "order_id": order_col})


def compute_sales_growth(df, date_col, revenue_series, usable_mask, today=None):
    """Growth requires consecutive calendar months bounded by observations."""
    if date_col not in df or not is_datetime64_any_dtype(df[date_col]):
        raise ValueError("Choose a converted date column.")
    columns = ["Period", "Revenue", "Growth %", "Reason"]
    valid = usable_mask & df[date_col].notna()
    if not valid.any():
        return pd.DataFrame(columns=columns)
    dates = df.loc[valid, date_col]
    table = pd.DataFrame({"Period": dates.dt.to_period("M"), "Revenue": revenue_series.reindex(df.index)[valid]})
    summed = table.groupby("Period")["Revenue"].sum(min_count=1)
    summed = summed.reindex(pd.period_range(summed.index.min(), summed.index.max(), freq="M"))
    now = pd.Timestamp(today or pd.Timestamp.now()).normalize()
    first, last = dates.min().normalize(), dates.max().normalize()
    rows, previous_ok, previous = [], False, None
    for period, value in summed.items():
        start, end = period.start_time.normalize(), period.end_time.normalize()
        complete = first <= start and last >= end and end < now and pd.notna(value) and np.isfinite(value)
        complete = complete and bool(usable_mask.all() and df[date_col].notna().all())
        growth = None
        reason = "Incomplete coverage, missing period, or current/future month."
        if complete and previous_ok and previous is not None and previous > 0:
            candidate = (value - previous) / previous * 100
            growth = float(candidate) if np.isfinite(candidate) else None
            reason = "Consecutive completed months; source completeness is not guaranteed."
        elif complete:
            reason = "A consecutive completed month with a positive baseline is needed."
        rows.append({"Period": start, "Revenue": value, "Growth %": growth, "Reason": reason})
        previous_ok, previous = complete, value
    return pd.DataFrame(rows, columns=columns)


def compute_dimension_breakdown(df, dimension_col, revenue_series, usable_mask, top_n=10):
    if dimension_col not in df:
        raise ValueError("Dimension column not found.")
    labels = df[dimension_col].astype("string").mask(missing_mask(df[dimension_col]), "(Missing)")
    table = pd.DataFrame({dimension_col: labels[usable_mask], "Revenue": revenue_series.reindex(df.index)[usable_mask]})
    result = table.groupby(dimension_col, as_index=False)["Revenue"].sum(min_count=1)
    denominator = safe_sum(revenue_series.reindex(df.index)[usable_mask])
    result["Share %"] = result["Revenue"] / denominator * 100 if denominator is not None and denominator > 0 else np.nan
    return result.sort_values("Revenue", ascending=False, kind="stable").head(top_n)
