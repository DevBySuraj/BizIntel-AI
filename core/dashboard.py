"""Read-only filtering and chart preparation for the working dataset."""

import math

import pandas as pd
import plotly.express as px
from pandas.api.types import is_bool_dtype, is_datetime64_any_dtype, is_numeric_dtype

from core.data_cleaning import missing_mask

CHART_GUIDE = {
    "Category counts": "One text column: compare how many records belong to each category.",
    "Numeric distribution": "One numeric column: a histogram shows how values are distributed.",
    "Category comparison": "Text plus numbers: compare an explicit mean or sum across categories.",
    "Trend over time": "Dates plus numbers: compare an explicit daily mean or sum in date order.",
    "Numeric relationship": "Two different numeric columns: inspect paired values; association is not causation.",
}


def column_groups(data):
    groups = {"text": [], "number": [], "date": []}
    for column in data.columns:
        dtype = data[column].dtype
        if is_datetime64_any_dtype(dtype):
            groups["date"].append(column)
        elif is_numeric_dtype(dtype) and not is_bool_dtype(dtype):
            groups["number"].append(column)
        else:
            groups["text"].append(column)
    # Offer simpler category columns first; IDs remain selectable if meaningful.
    groups["text"].sort(key=lambda column: data[column].nunique())
    return groups


def chart_options(data):
    groups = column_groups(data)
    available = []
    if groups["text"]:
        available.append("Category counts")
    if groups["number"]:
        available.append("Numeric distribution")
    if groups["text"] and groups["number"]:
        available.append("Category comparison")
    if groups["date"] and groups["number"]:
        available.append("Trend over time")
    if len(groups["number"]) >= 2:
        available.append("Numeric relationship")
    return available


def finite_mask(values):
    return values.map(lambda value: pd.notna(value) and math.isfinite(value)).astype(bool)


def filter_data(data, category=None, selected_values=None, numeric=None,
                number_range=None, date=None, date_range=None, include_missing=False):
    """Combine active filters with AND and return a copy, without changing data."""
    groups = column_groups(data)
    keep = pd.Series(True, index=data.index)
    for column, expected in ((category, "text"), (numeric, "number"), (date, "date")):
        if column is not None and column not in groups[expected]:
            raise ValueError(f"Choose a valid {expected} column for the filter.")
    if category is not None:
        match = data[category].isin(selected_values or [])
        if include_missing:
            match |= missing_mask(data[category])
        keep &= match.fillna(False)
    if numeric is not None:
        if number_range is None or len(number_range) != 2:
            raise ValueError("Choose both numeric range bounds.")
        low, high = number_range
        if not math.isfinite(low) or not math.isfinite(high) or low > high:
            raise ValueError("The numeric minimum must not exceed the maximum; both must be finite.")
        match = data[numeric].between(low, high) & finite_mask(data[numeric])
        if include_missing:
            match |= missing_mask(data[numeric])
        keep &= match.fillna(False)
    if date is not None:
        if date_range is None or len(date_range) != 2:
            raise ValueError("Choose both a start and an end date.")
        start, end = (pd.Timestamp(value) for value in date_range)
        if pd.isna(start) or pd.isna(end) or start > end:
            raise ValueError("The start date must not be after the end date.")
        # Include the entire selected end day rather than only midnight.
        match = data[date].dt.normalize().between(start.normalize(), end.normalize())
        if include_missing:
            match |= missing_mask(data[date])
        keep &= match.fillna(False)
    return data.loc[keep].copy(deep=True)


def build_chart(data, kind, x, y=None, aggregation="Mean"):
    """Return a Plotly figure, its prepared data, and explicit exclusion notes."""
    if kind not in chart_options(data):
        raise ValueError("This chart needs different column types. Convert suitable columns in cleaning first.")
    groups = column_groups(data)
    x_type = {
        "Category counts": "text", "Numeric distribution": "number",
        "Category comparison": "text", "Trend over time": "date",
        "Numeric relationship": "number",
    }[kind]
    if x not in groups[x_type]:
        raise ValueError(f"Choose a {x_type} column for the horizontal axis.")
    needs_y = kind in ("Category comparison", "Trend over time", "Numeric relationship")
    if needs_y and y not in groups["number"]:
        raise ValueError("Choose a numeric column for the vertical axis.")
    if kind == "Numeric relationship" and x == y:
        raise ValueError("Choose two different numeric columns.")
    if aggregation not in ("Mean", "Sum"):
        raise ValueError("Choose Mean or Sum aggregation.")

    keep = ~missing_mask(data[x])
    if x_type == "number":
        keep &= finite_mask(data[x])
    if needs_y:
        keep &= ~missing_mask(data[y]) & finite_mask(data[y])
    valid = data.loc[keep].copy(deep=True)
    notes = [f"Excluded {len(data) - len(valid)} filtered rows with missing or nonfinite chart values."]
    if valid.empty:
        raise ValueError("No usable values remain for these chart columns. Choose other columns or filters.")

    # Internal names avoid collisions with arbitrary user-provided column names.
    table = pd.DataFrame({"x": valid[x].to_numpy()})
    if needs_y:
        table["y"] = valid[y].to_numpy()
    y_label = y
    if kind == "Category counts":
        table = table.groupby("x", sort=False).size().reset_index(name="y")
        table = table.sort_values("y", ascending=False, kind="stable")
        y_label = "Record count"
    elif kind in ("Category comparison", "Trend over time"):
        if kind == "Trend over time":
            table["x"] = pd.to_datetime(table["x"]).dt.normalize()
        table = table.groupby("x", sort=True)["y"].agg(aggregation.lower()).reset_index()
        y_label = f"{aggregation} of {y}"
        notes.append(f"Each point/bar uses the {aggregation.lower()} of nonmissing {y} values in its group.")
        if not finite_mask(table["y"]).all():
            raise ValueError("The aggregation exceeded the numeric range. Try Mean or narrower filters.")
        if kind == "Category comparison":
            table = table.sort_values("y", ascending=False, kind="stable")
        else:
            if len(table) < 2:
                raise ValueError("A time trend needs at least two distinct dates after filtering.")
            notes.append("Daily values are sorted by date. Days without records are not filled with zero; lines connect observed dates.")

    if kind in ("Category counts", "Category comparison"):
        if len(table) > 20:
            notes.append(f"Showing the top 20 of {len(table)} categories by the plotted value; others are omitted.")
            table = table.head(20)
        figure = px.bar(table, x="x", y="y", labels={"x": x, "y": y_label})
        figure.update_xaxes(type="category")
    elif kind == "Numeric distribution":
        figure = px.histogram(table, x="x", nbins=20, labels={"x": x}, title=f"Distribution of {x}")
        figure.update_yaxes(title_text="Record count")
        notes.append("Histogram bins are chosen by Plotly (target: 20); the table lists the input observations.")
    elif kind == "Trend over time":
        figure = px.line(table, x="x", y="y", markers=True, labels={"x": x, "y": y_label})
    else:
        if len(table) > 5000:
            notes.append(f"Showing a reproducible sample of 5,000 of {len(table)} valid paired observations.")
            table = table.sample(5000, random_state=42)
        figure = px.scatter(table, x="x", y="y", labels={"x": x, "y": y_label})
        notes.append("Each point is one record. A visible relationship does not establish cause and effect.")
    figure.update_layout(title=figure.layout.title.text or kind)
    return figure, table.rename(columns={"x": f"X: {x}", "y": f"Y: {y_label}"}), notes
