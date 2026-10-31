"""Versioned JSON settings on disk; no datasets or executable objects."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from uuid import uuid4

import pandas as pd
from core.automation import ALIASES, NUMERIC_ROLES
from core.catalogue import LEGACY_ROLES, canonical_mapping, analysis_table
from core.analysis import apply_filters
from core.charts import build_figure
from core.data_cleaning import apply_cleaning

TEMPLATE_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "templates"
    if Path(__file__).resolve().parent.name == "core"
    else Path(__file__).resolve().parent / "data" / "templates"
)
SETTING_KEYS = {"mapping", "currency", "filters", "charts", "layout", "cleaning_rules", "report", "models"}


def path_for(template_id, directory=TEMPLATE_DIR):
    if not isinstance(template_id, str) or not re.fullmatch(r"[a-f0-9]{32}", template_id):
        raise ValueError("Invalid template identifier.")
    return Path(directory) / f"{template_id}.json"


def validate(document):
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Unsupported template schema version.")
    path_for(document.get("id"))
    if not isinstance(document.get("name"), str) or not document["name"].strip() or len(document["name"]) > 100:
        raise ValueError("Template name must contain 1-100 characters.")
    settings = document.get("settings")
    if not isinstance(settings, dict) or set(settings) != SETTING_KEYS:
        raise ValueError("Invalid template settings structure.")
    if not isinstance(settings["mapping"], dict) or not set(settings["mapping"]) <= set(ALIASES) | set(LEGACY_ROLES):
        raise ValueError("Invalid field mappings.")
    if any(v is not None and not isinstance(v, str) for v in settings["mapping"].values()):
        raise ValueError("Mappings must be column names.")
    if not isinstance(settings["currency"], str) or len(settings["currency"]) > 32 or settings["layout"] not in (1, 2):
        raise ValueError("Invalid currency or layout.")
    for key in ("filters", "report", "models"):
        if not isinstance(settings[key], dict):
            raise ValueError(f"Invalid {key} structure.")
    for key in ("charts", "cleaning_rules"):
        if not isinstance(settings[key], list) or len(settings[key]) > 50 or any(not isinstance(x, dict) for x in settings[key]):
            raise ValueError(f"Invalid {key} structure.")
    json.dumps(document, allow_nan=False)
    document = deepcopy(document)
    document["settings"]["mapping"] = canonical_mapping(settings["mapping"])
    return document


def read_template(template_id, directory=TEMPLATE_DIR):
    path = path_for(template_id, directory)
    if path.stat().st_size > 1_000_000:
        raise ValueError("Template is too large.")
    try:
        return validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError("Template is not valid JSON settings.") from error


def list_templates(directory=TEMPLATE_DIR):
    result, errors = [], []
    if Path(directory).exists():
        for path in sorted(Path(directory).glob("*.json")):
            try:
                result.append(read_template(path.stem, directory))
            except (OSError, ValueError) as error:
                errors.append(f"{path.name}: {error}")
    return result, errors


def save_template(name, description, settings, template_id=None, directory=TEMPLATE_DIR):
    template_id = template_id or uuid4().hex
    path = path_for(template_id, directory)
    now = datetime.now(timezone.utc).isoformat()
    created = read_template(template_id, directory)["created"] if path.exists() else now
    # Explicit allowlist: session data, findings, predictions and drafts never enter JSON.
    chosen = {key: deepcopy(settings[key]) for key in SETTING_KEYS}
    document = validate(dict(schema_version=1, id=template_id, name=name.strip(),
                             description=str(description)[:1000], created=created, updated=now, settings=chosen))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix("." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)
    return document


def delete_template(template_id, directory=TEMPLATE_DIR):
    path_for(template_id, directory).unlink()


def compatible_settings(data, defaults, document):
    """Apply compatible pieces by column name; explain each rejected piece."""
    saved = validate(document)["settings"]
    result, warnings = deepcopy(defaults), []
    working = data.copy(deep=True)
    applied_rules = []
    for rule in saved["cleaning_rules"]:
        try:
            allowed = {k: v for k, v in rule.items() if k in {"action", "columns", "fill_value", "date_format"}}
            working = apply_cleaning(working, **allowed)
            applied_rules.append(allowed)
        except (ValueError, TypeError, KeyError) as error:
            warnings.append(f"Preparation skipped: {error}")
    result["cleaning_rules"] = applied_rules
    for role, column in saved["mapping"].items():
        if column is None:
            result["mapping"][role] = None
        elif column not in working:
            warnings.append(f"Mapping {role} skipped: missing column {column}.")
        elif role in NUMERIC_ROLES and not pd.api.types.is_numeric_dtype(working[column]):
            warnings.append(f"Mapping {role} skipped: {column} is not numeric.")
        elif role == "order_date" and not pd.api.types.is_datetime64_any_dtype(working[column]):
            warnings.append(f"Mapping date skipped: {column} is not a date.")
        else:
            result["mapping"][role] = column
    result["currency"], result["layout"] = saved["currency"], saved["layout"]
    supported = analysis_table(working, result["mapping"])
    result["filters"] = {}
    for column, rule in saved["filters"].items():
        try:
            if column not in supported or not isinstance(rule, dict):
                raise ValueError("Column or rule unavailable.")
            if rule.get("kind") == "category" and not set(rule.get("values", [])) <= set(working[column].dropna()):
                raise ValueError("One or more selected categories are absent.")
            filtered = apply_filters(working, {column: rule})
            if filtered.empty and len(working):
                raise ValueError("This filter matches no rows in the new data.")
            result["filters"][column] = deepcopy(rule)
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            warnings.append(f"Filter {column} skipped: {error}")
    result["charts"] = []
    for chart in saved["charts"]:
        try:
            build_figure(working, chart, result["mapping"])
            result["charts"].append(deepcopy(chart))
        except (ValueError, KeyError, TypeError) as error:
            warnings.append(f"Chart skipped: {error}")
    models = saved["models"]
    result["models"] = {
        "frequency": models.get("frequency") if models.get("frequency") in ("D", "W", "M") else "M",
        "horizon": max(1, min(12, int(models.get("horizon", 3)))),
        "clusters": max(2, min(6, int(models.get("clusters", 3)))),
        "iqr_multiplier": max(0.5, min(5., float(models.get("iqr_multiplier", 1.5))))}
    for key in ("target", "anomaly_column"):
        column = models.get(key)
        if column is None:
            result["models"][key] = None
        elif column in supported and pd.api.types.is_numeric_dtype(supported[column]):
            result["models"][key] = column
        else:
            warnings.append(f"Analysis setting {key} skipped: unavailable numeric column {column}.")
    # Report preferences describe structure only; no previous interpretation/action text.
    preferences = saved["report"]
    result["report"] = {
        "title": str(preferences.get("title", "Business performance review"))[:150],
        "methods": [m for m in preferences.get("methods", []) if m in ("Forecasting", "Customer segmentation", "Anomalies")],
        "finding_kinds": [k for k in preferences.get("finding_kinds", []) if k in ("duplicates", "missing", "concentration", "cost_coverage", "growth", "records")],
        "chart_ids": [c for c in preferences.get("chart_ids", []) if c in {chart["id"] for chart in result["charts"]}],
    } if preferences else {}
    return working, result, warnings
