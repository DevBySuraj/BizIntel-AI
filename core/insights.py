"""Reproducible observations and separate, non-executing action suggestions."""
from core.kpi import compute_dimension_breakdown


def findings(context):
    data, metrics, scope = context["data"], context["metrics"], context["scope"]
    output = []

    def add(kind, statement, evidence, action, limitation, columns):
        output.append({"id": kind + ":" + scope["id"], "kind": kind,
                       "statement": statement, "evidence": evidence, "suggestion": action,
                       "limitation": limitation, "columns": columns, "scope": scope,
                       "coverage": f"{metrics['usable_records']} of {len(data)} rows with valid revenue",
                       "support": "Dashboard chart / formula and scoped data table"})

    if data.empty:
        return output
    quality = context["quality"]
    if quality["Duplicate rows beyond first"]:
        count = quality["Duplicate rows beyond first"]
        add("duplicates", f"{count} exact duplicate records are present.",
            "Count of exact repeats beyond the first, across all columns.",
            "Review source records before choosing whether to remove duplicates.",
            "Repeated records may be legitimate; nothing was deleted.", list(data.columns))
    if quality["Missing cells"]:
        add("missing", f"{quality['Missing cells']} cells are missing in this scope.",
            "Null or whitespace-only cells; literal NA/null codes are retained.",
            "Review completeness of fields needed for the business question.",
            "Missing cells are not automatically zeros.", list(data.columns))
    dimension = next((context["settings"]["mapping"].get(c) for c in ("category", "region", "product_name")
                      if context["settings"]["mapping"].get(c) in data), None)
    if dimension and metrics["total_revenue"] is not None and metrics["total_revenue"] > 0 and not metrics["return_records"]:
        table = compute_dimension_breakdown(data, dimension, metrics["revenue_series"], metrics["usable_mask"])
        if not table.empty:
            top = table.iloc[0]
            add("concentration", f"{top[dimension]} contributes {top['Share %']:.1f}% of recorded revenue.",
                f"{top['Revenue']:,.2f} / {metrics['total_revenue']:,.2f} × 100; {metrics['currency']}. Full denominator before top-N.",
                f"Review demand and stock availability for {top[dimension]} before planning inventory.",
                "Revenue share alone does not establish profitability or future demand.", [dimension])
    if metrics["missing_cost_records"] and metrics["profit_basis"] == "calculated_gross":
        add("cost_coverage", f"Costs are missing for {metrics['missing_cost_records']} revenue records.",
            "Gross profit and margin are withheld until corresponding cost coverage is complete.",
            "Obtain the missing cost information before making margin decisions.",
            "Missing costs are not treated as zero.", ["cost"])
    growth = context["growth"]
    if not growth.empty and growth["Growth %"].notna().any():
        row = growth.dropna(subset=["Growth %"]).iloc[-1]
        add("growth", f"Revenue changed {row['Growth %']:+.1f}% in {row['Period']:%B %Y}.",
            "(Current completed month - previous completed month) / previous month × 100.",
            "Investigate product mix and operational context before changing your plan.",
            "Observed date boundaries cannot guarantee complete source-system reporting.", [context["settings"]["mapping"].get("order_date")])
    if not output:
        add("records", f"This scope contains {len(data):,} records and {len(data.columns)} columns.",
            "Counts of the active filtered table.", "Review the chart patterns and field definitions before drawing conclusions.",
            "No unsupported business conclusion has been inferred.", list(data.columns))
    return output
