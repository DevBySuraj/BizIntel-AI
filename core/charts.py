"""Serializable chart settings. Figures are always rebuilt from current data."""
from uuid import uuid4
import numpy as np
import pandas as pd
import plotly.express as px
from core.dashboard import column_groups
from core.data_cleaning import missing_mask
from core.kpi import monetary_series
from core.catalogue import analysis_table, check_measure

PALETTES = {"Teal": ["#087F8C", "#173451", "#59A7A6", "#B68132", "#7378A7"],
            "Navy": ["#173451", "#387EA0", "#087F8C", "#B68132"],
            "Accessible": ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00"]}
KINDS = ["Bar", "Line", "Histogram", "Scatter", "Box"]


def spec(kind, x, y=None, title="", aggregation="sum", **kwargs):
    return {"id": uuid4().hex, "kind": kind, "x": x, "y": y,
            "title": title, "aggregation": aggregation, "group": None,
            "palette": "Teal", "top_n": 12, "sort": "Descending", "labels": False,
            "x_label": "", "y_label": "", "enabled": True, **kwargs}


def suggestions(data, mapping, money_ok=True):
    data = analysis_table(data, mapping)
    groups = column_groups(data)
    revenue, _ = monetary_series(data, mapping)
    result = []
    if money_ok and revenue.notna().any():
        date = mapping.get("order_date")
        if date in groups["date"]:
            result.append(spec("Line", date, "@revenue", "Sales over time"))
        for role in ("category", "region", "product_name"):
            column = mapping.get(role)
            if column:
                result.append(spec("Bar", column, "@revenue", f"Sales by {column}"))
                if len(result) >= 3:
                    break
    if not result:
        if groups["text"]:
            category = next((c for c in groups["text"] if not c.lower().endswith("id")), groups["text"][0])
            result.append(spec("Bar", category, title=f"Records by {category}", aggregation="count"))
        if groups["number"]:
            result.append(spec("Histogram", groups["number"][0], title=f"Distribution of {groups['number'][0]}"))
        if len(groups["number"]) >= 2:
            result.append(spec("Scatter", *groups["number"][:2], title="Numeric relationship"))
    return result


def build_figure(data, setting, mapping, money_ok=True):
    data = analysis_table(data, mapping)
    kind, x, y = setting["kind"], setting["x"], setting.get("y")
    for column in (x, y, setting.get("group")):
        check_measure(column, mapping, money_ok)
    if kind not in KINDS or x not in data:
        raise ValueError("This chart's type or horizontal column is unavailable.")
    if y == "@revenue":
        if not money_ok:
            raise ValueError("Monetary charts require a single known currency per scope.")
        values, _ = monetary_series(data, mapping)
    elif y in data:
        values = data[y]
    else:
        values = None
    agg = setting.get("aggregation", "sum")
    if agg not in ("sum", "mean", "count"):
        raise ValueError("Choose sum, mean, or count.")
    table = pd.DataFrame({"x": data[x]})
    need_y = kind in ("Scatter", "Box") or (kind in ("Bar", "Line") and agg != "count")
    if need_y:
        if values is None or not pd.api.types.is_numeric_dtype(values):
            raise ValueError("This chart requires a numeric vertical measure.")
        table["y"] = values
    if kind in ("Scatter", "Histogram") and not pd.api.types.is_numeric_dtype(table["x"]):
        raise ValueError("This chart needs a numeric horizontal axis.")
    if kind == "Scatter" and x == y:
        raise ValueError("Choose different numeric axes.")
    group = setting.get("group")
    if group:
        if group not in data:
            raise ValueError("The grouping column is unavailable.")
        table["group"] = data[group]
        if table["group"].nunique() > 20:
            raise ValueError("Choose a grouping column with at most 20 distinct values.")
    valid = pd.Series(True, index=table.index)
    for column in table:
        valid &= ~missing_mask(table[column])
        if pd.api.types.is_numeric_dtype(table[column]):
            valid &= np.isfinite(table[column].astype(float))
    notes = [f"Excluded {int((~valid).sum())} scoped rows with missing/nonfinite axes or grouping values."]
    table = table.loc[valid].copy()
    if table.empty:
        raise ValueError("No usable chart values remain in this scope.")
    if kind in ("Bar", "Line"):
        keys = ["x"] + (["group"] if group else [])
        table = (table.groupby(keys, as_index=False).size().rename(columns={"size": "y"}) if agg == "count"
                 else table.groupby(keys, as_index=False)["y"].agg(agg))
        if not np.isfinite(table["y"]).all():
            raise ValueError("Chart aggregation exceeds the numeric range.")
        notes.append(f"Aggregation: {agg}. Missing periods are not filled with zero.")
        if kind == "Bar":
            categories = table.groupby("x")["y"].sum().sort_values(ascending=setting.get("sort") == "Ascending")
            if setting.get("sort") == "Alphabetical":
                categories = categories.sort_index()
            selected = categories.head(int(setting.get("top_n", 12))).index
            notes.append(f"Showing {len(selected)} of {len(categories)} categories; totals still use the full scope.")
            table = table[table["x"].isin(selected)]
            rank = {v: i for i, v in enumerate(selected)}
            table = table.sort_values("x", key=lambda s: s.map(rank))
        else:
            table = table.sort_values("x")
    elif len(table) > 5000:
        notes.append(f"Deterministic sample of 5,000 of {len(table)} usable records.")
        table = table.sample(5000, random_state=42)
    options = {"data_frame": table, "x": "x", "color": "group" if group else None,
               "color_discrete_sequence": PALETTES.get(setting.get("palette"), PALETTES["Teal"]),
               "labels": {"x": setting.get("x_label") or x,
                          "y": setting.get("y_label") or ("Records" if agg == "count" else "Sales" if y == "@revenue" else str(y)),
                          "group": group or ""}, "title": setting.get("title") or kind}
    if kind == "Histogram":
        figure = px.histogram(**options, nbins=20)
        figure.update_yaxes(title_text=setting.get("y_label") or "Record count")
    else:
        options["y"] = "y"
        figure = {"Bar": px.bar, "Line": px.line, "Scatter": px.scatter, "Box": px.box}[kind](**options)
    if setting.get("labels") and kind == "Bar":
        figure.update_traces(texttemplate="%{y:,.2f}", textposition="auto")
    if kind == "Line":
        figure.update_traces(mode="lines+markers")
    figure.update_layout(template="plotly_white", height=360, margin=dict(l=20, r=20, t=55, b=35),
                         font=dict(family="Arial", color="#173451", size=12), paper_bgcolor="white",
                         legend=dict(orientation="h", y=-0.3))
    return figure, table, notes
