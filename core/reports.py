"""Scope-bound report assembly and local exports; never execute actions."""
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path
import re

import pandas as pd
import plotly.io as pio
from core.charts import build_figure
from core.insights import findings

LABELS = {"total_revenue": "Sales", "total_cost": "Cost of goods", "total_profit": "Gross profit",
          "profit_margin": "Gross margin (%)", "total_orders": "Orders", "aov": "Average order value", "units_sold": "Units sold"}


def csv_bytes(data, spreadsheet_safe=True):
    output = data.copy(deep=True)
    if spreadsheet_safe:
        def safe(value):
            if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r"))):
                if re.fullmatch(r"-\d+(?:\.\d+)?", value.strip()):
                    return value
                return "'" + value
            return value
        for column in output:
            if not pd.api.types.is_numeric_dtype(output[column]):
                output[column] = output[column].map(safe)
        output.columns = [safe(c) for c in output.columns]
    return output.to_csv(index=False).encode("utf-8-sig")


def assemble_report(ctx, title, selected_ids, chart_ids, actions=None, interpretation="", methods=None):
    metrics = ctx["metrics"]
    figures, warnings = [], list(metrics["notices"])
    for setting in ctx["settings"]["charts"]:
        if setting["id"] in chart_ids:
            try:
                figure, _, notes = build_figure(ctx["data"], setting, ctx["settings"]["mapping"], metrics["monetary_ok"])
                figures.append({"figure": figure, "title": setting["title"], "notes": " · ".join(notes)})
            except ValueError as error:
                warnings.append(str(error))
    chosen = [f for f in findings(ctx) if f["id"] in selected_ids]
    values = [{"Metric": label, "Value": "Unavailable" if metrics[key] is None else f"{metrics[key]:,.2f}",
               "Explanation": metrics["reasons"][key] if metrics[key] is None else
               metrics["revenue_mode"] if key == "total_revenue" else metrics["cost_mode"] if key == "total_cost" else
               {"total_profit": metrics["profit_mode"], "profit_margin": metrics["profit_label"] + " / positive sales × 100",
                "units_sold": "Sum of quantity, including returns; complete scoped quantity coverage",
                "total_orders": "Distinct nonblank order IDs", "aov": "Revenue / distinct orders; complete matched cohort"}.get(key, "")}
              for key, label in {**LABELS, "total_profit": metrics["profit_label"],
                                 "profit_margin": metrics["margin_label"] + " (%)"}.items()]
    return {"title": title or "BizIntel AI business report", "scope": ctx["scope"],
            "generated": datetime.now(timezone.utc).isoformat(), "quality": ctx["quality"],
            "metrics": values, "findings": chosen, "charts": figures, "actions": actions or {},
            "interpretation": interpretation, "methods": methods or [], "warnings": warnings,
            "coverage": f"Sales: {metrics['usable_records']}/{metrics['total_records']} records. Missing costs: {metrics['missing_cost_records']}. Negative/return rows: {metrics['return_records']}.",
            "limitations": "Descriptive findings are associations, not causes. Suggested actions require human review. Calculated gross profit excludes operating expenses. Reported profit follows the source definition; it is not assumed gross or net. Discount is never deducted automatically. Currency labels do not convert exchange rates. Source completeness is not guaranteed. Duplicates remain unless explicitly removed. No business action was executed."}


def report_sections(report):
    """Identical text sections drive the on-screen preview, HTML and PDF."""
    scope = report["scope"]
    filter_text = []
    for column, rule in scope["filters"].items():
        detail = ", ".join(map(str, rule.get("values", []))) if rule["kind"] == "category" else (
            f"last {rule['days']} days" if rule.get("mode") == "last_days" else " to ".join(map(str, rule.get("range", []))))
        filter_text.append(f"{column}: {detail}; missing values {'included' if rule.get('include_missing') else 'excluded'}")
    quality_text = "; ".join(f"{key}: {value:,}" for key, value in report["quality"].items())
    interpreted = [f"{h['Column']}: {h['Interpretation']}" for h in scope["preparation"]
                   if h.get("Interpretation", "").startswith("Converted")]
    manual = ["; ".join(f"{key}: {value}" for key, value in h.items()) for h in scope["preparation"] if "Action" in h]
    preparation_text = ["Original upload preserved. Only safe number/date interpretation runs automatically."] + interpreted + manual
    sections = [("Dataset and scope", [f"{scope['dataset']} | version {scope['version']} | {scope['rows']} of {scope['total_rows']} records | {scope['currency']}",
                 f"Generated UTC: {report['generated']} | Scope ID: {scope['id']}",
                 "Filters: " + ("; ".join(filter_text) or "All records"), report["coverage"]]),
                ("Quality and preparation", [quality_text, *preparation_text]),
                ("Business metrics", [f"{r['Metric']}: {r['Value']}. {r['Explanation']}" for r in report["metrics"]])]
    for finding in report["findings"]:
        action = report["actions"].get(finding["id"], {"status": "Suggested", "text": finding["suggestion"]})
        sections.append(("Calculated finding", [finding["statement"], "Evidence: " + finding["evidence"],
                        "Coverage: " + finding["coverage"], "Limit: " + finding["limitation"],
                        f"Action ({action['status']}): {action['text']}"]))
    sections += [("User's final interpretation", [report["interpretation"] or "No final interpretation entered."]),
                 ("Included methods and evaluation", report["methods"] or ["No advanced method selected for this report."]),
                 ("Limitations", [report["limitations"], *report["warnings"]])]
    return sections


def html_bytes(report):
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
             '<style>body{font:16px Arial;color:#173451;background:#f5f7fb;margin:0}main{max-width:1050px;margin:auto;padding:32px}section{background:white;padding:22px;margin:18px 0;border:1px solid #dfe6ee;border-radius:8px}h1,h2{color:#10243a}p{overflow-wrap:anywhere;line-height:1.5}</style>',
             '<title>'+escape(report['title'])+'</title><main><h1>'+escape(report['title'])+'</h1>']
    for heading, paragraphs in report_sections(report):
        parts.append('<section><h2>'+escape(heading)+'</h2>')
        parts.extend('<p>'+escape(str(p))+'</p>' for p in paragraphs)
        parts.append('</section>')
    for index, chart in enumerate(report["charts"]):
        parts.append('<section><h2>'+escape(chart['title'])+'</h2>')
        parts.append(pio.to_html(chart["figure"], full_html=False, include_plotlyjs=True if index == 0 else False,
                                 include_mathjax=False, div_id=f"chart-{index}", config={"responsive": True}))
        parts.append('<p>'+escape(chart['notes'])+'</p></section>')
    parts.append('</main></html>')
    return ''.join(parts).encode('utf-8')


def pdf_bytes(report):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, KeepTogether
    font_name = "Helvetica"
    for font in (Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        if font.exists():
            if "BizIntel" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("BizIntel", str(font)))
            font_name = "BizIntel"
            break
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font_name
        style.textColor = colors.HexColor("#173451")
        style.wordWrap = "CJK"
    styles["BodyText"].leading = 15
    styles["BodyText"].spaceAfter = 7
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=(595.28,841.89), rightMargin=42, leftMargin=42,
                            topMargin=42, bottomMargin=42, title=report["title"])
    story = [Paragraph(escape(report["title"]), styles["Title"]), Spacer(1,12)]
    for heading, paragraphs in report_sections(report):
        story.append(Paragraph(escape(heading), styles["Heading2"]))
        for paragraph in paragraphs:
            story.append(Paragraph(escape(str(paragraph)), styles["BodyText"]))
    pio.defaults.mathjax = None
    for chart in report["charts"]:
        png = chart["figure"].to_image(format="png", width=1000, height=480, scale=1.5)
        story.append(KeepTogether([Paragraph(escape(chart["title"]), styles["Heading2"]),
                      Image(BytesIO(png), width=510, height=244.8),
                      Paragraph(escape(chart["notes"]), styles["BodyText"])]))
    def footer(canvas, document):
        canvas.setFont(font_name, 8)
        canvas.drawString(42, 22, "BizIntel AI | Decision support; human review required")
        canvas.drawRightString(553, 22, str(document.page))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
