"""Serializable chart settings. Figures are always rebuilt from current data."""
from uuid import uuid4
import numpy as np
import pandas as pd
import plotly.express as px
from core.dashboard import column_groups
from core.data_cleaning import missing_mask
from core.kpi import monetary_series
from core.catalogue import analysis_table, check_measure

PALETTES = {
    "Vibrant Rainbow": ["#2563EB", "#087F8C", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#06B6D4"],
    "Teal & Ocean": ["#087F8C", "#0EA5E9", "#3B82F6", "#10B981", "#F59E0B", "#8B5CF6"],
    "Royal Blue & Indigo": ["#2563EB", "#4F46E5", "#0284C7", "#059669", "#D97706", "#7C3AED"],
    "Sunset & Warm": ["#EA580C", "#D97706", "#DC2626", "#087F8C", "#2563EB", "#7C3AED"],
    "Emerald & Fresh": ["#059669", "#10B981", "#0284C7", "#6366F1", "#F59E0B", "#84CC16"],
    "Purple & Violet": ["#7C3AED", "#8B5CF6", "#EC4899", "#087F8C", "#0EA5E9", "#F59E0B"],
    "Navy Classic": ["#102A43", "#087F8C", "#2563EB", "#475569", "#F59E0B", "#10B981"],
    "Accessible": ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"],
    "Teal": ["#087F8C", "#2563EB", "#102A43", "#F59E0B", "#10B981"]
}
KINDS = ["Bar", "Line", "Histogram", "Scatter", "Box"]


def spec(kind, x, y=None, title="", aggregation="sum", **kwargs):
    return {"id": uuid4().hex, "kind": kind, "x": x, "y": y,
            "title": title, "aggregation": aggregation, "group": None,
            "palette": "Vibrant Rainbow", "top_n": 12, "sort": "Descending", "labels": False,
            "x_label": "", "y_label": "", "enabled": True, **kwargs}


def suggestions(data, mapping, money_ok=True):
    data = analysis_table(data, mapping)
    groups = column_groups(data)
    revenue, _ = monetary_series(data, mapping)
    result = []
    palettes_cycle = ["Teal & Ocean", "Vibrant Rainbow", "Royal Blue & Indigo", "Sunset & Warm"]
    if money_ok and revenue.notna().any():
        date = mapping.get("order_date")
        if date in groups["date"]:
            result.append(spec("Line", date, "@revenue", "Sales over time", palette="Teal & Ocean"))
        for idx, role in enumerate(("category", "region", "product_name"), 1):
            column = mapping.get(role)
            if column:
                chosen_pal = palettes_cycle[idx % len(palettes_cycle)]
                result.append(spec("Bar", column, "@revenue", f"Sales by {column}", palette=chosen_pal))
                if len(result) >= 3:
                    break
    if not result:
        if groups["text"]:
            category = next((c for c in groups["text"] if not c.lower().endswith("id")), groups["text"][0])
            result.append(spec("Bar", category, title=f"Records by {category}", aggregation="count", palette="Vibrant Rainbow"))
        if groups["number"]:
            result.append(spec("Histogram", groups["number"][0], title=f"Distribution of {groups['number'][0]}", palette="Royal Blue & Indigo"))
        if len(groups["number"]) >= 2:
            result.append(spec("Scatter", *groups["number"][:2], title="Numeric relationship", palette="Teal & Ocean"))
    return result


def build_figure(data, setting, mapping, money_ok=True, height=220):
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

    # Use multi-color bar styling when no distinct group column is specified
    color_prop = "group" if group else ("x" if kind == "Bar" else None)
    palette_seq = PALETTES.get(setting.get("palette"), PALETTES["Vibrant Rainbow"])
    options = {
        "data_frame": table,
        "x": "x",
        "color": color_prop,
        "color_discrete_sequence": palette_seq,
        "labels": {
            "x": setting.get("x_label") or x,
            "y": setting.get("y_label") or ("Records" if agg == "count" else "Sales" if y == "@revenue" else str(y)),
            "group": group or ""
        },
        "title": setting.get("title") or kind
    }
    if kind == "Histogram":
        figure = px.histogram(**options, nbins=20)
        figure.update_yaxes(title_text=setting.get("y_label") or "Record count")
    else:
        options["y"] = "y"
        figure = {"Bar": px.bar, "Line": px.line, "Scatter": px.scatter, "Box": px.box}[kind](**options)
    
    # Avoid overcrowded markers on dense time series line charts (>15 data points)
    if kind == "Line":
        if len(table) > 15:
            figure.update_traces(mode="lines", line=dict(width=2.5))
        else:
            figure.update_traces(mode="lines+markers", line=dict(width=2), marker=dict(size=5))
        figure.update_traces(hovertemplate="%{x}<br><b>%{y:,.2f}</b><extra></extra>")
    elif kind == "Bar":
        figure.update_traces(marker=dict(line=dict(width=0)))
        if setting.get("labels") and len(table) <= 12:
            figure.update_traces(texttemplate="%{y:,.2f}", textposition="auto")
        figure.update_traces(hovertemplate="%{x}<br><b>%{y:,.2f}</b><extra></extra>" if agg != "count" else "%{x}<br><b>%{y:,} records</b><extra></extra>")
        # Hide redundant legend when coloring single-variable bars by x
        if not group and color_prop == "x":
            figure.update_layout(showlegend=False)
    elif kind == "Scatter":
        figure.update_traces(marker=dict(size=7, opacity=0.85), hovertemplate="X: %{x:,.2f}<br>Y: %{y:,.2f}<extra></extra>")

    figure.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=30, r=15, t=32, b=26),
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", color="#0F172A", size=11),
        paper_bgcolor="white",
        plot_bgcolor="white",
        legend=dict(orientation="h", y=-0.22, x=0, font=dict(size=10, color="#475569"))
    )
    figure.update_xaxes(showgrid=True, gridcolor="#EBF1F6", linecolor="#CBD5E1", tickfont=dict(size=10, color="#475569"))
    figure.update_yaxes(showgrid=True, gridcolor="#EBF1F6", linecolor="#CBD5E1", tickfont=dict(size=10, color="#475569"))
    return figure, table, notes
