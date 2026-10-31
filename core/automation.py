"""Conservative interpretation and semantic mapping; never overwrite originals."""

import math
import re
from hashlib import sha256
import json

import pandas as pd
from pandas.api.types import is_numeric_dtype, is_datetime64_any_dtype

from core.data_cleaning import missing_mask, conversion_preview

from core.catalogue import ALIASES, NUMERIC_ROLES



def normalized(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def identifier(name, values):
    label = normalized(name)
    protected = (any(label in ALIASES[role] for role in ("order_id", "customer_id", "product_id")) or label == "id" or label.endswith(("_id", "_code", "_no")) or
                 any(token in label for token in ("phone", "postal", "zip", "postcode")))
    text = values[~missing_mask(values)].astype("string").str.strip()
    return protected or bool(text.str.match(r"[+-]?0\d+").any())


def interpret(original):
    """All-or-nothing conversion per column; ambiguous/mixed data stays text."""
    working = original.copy(deep=True)
    log = []
    for column in working:
        values = working[column]
        present = values[~missing_mask(values)].astype("string").str.strip()
        reason = "Text retained; no unambiguous supported type."
        if present.empty:
            reason = "No nonmissing values."
        elif identifier(column, values):
            reason = "Identifier or leading-zero code retained as text."
        elif present.str.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?").all():
            converted, invalid = conversion_preview(values, "date")
            if not invalid.any():
                working[column] = converted
                reason = "Converted ISO dates; original values preserved."
            else:
                reason = "Invalid calendar date; text retained."
        elif present.str.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?").all():
            converted, invalid = conversion_preview(values, "number")
            # Large integers can lose identity/precision when used in arithmetic.
            too_precise = present.str.fullmatch(r"[+-]?\d{16,}").any()
            if not invalid.any() and not too_precise:
                working[column] = converted
                reason = "Converted plain finite numbers; blanks remain missing."
            else:
                reason = "Nonfinite or very large exact values retained as text."
        elif present.str.contains(r"\d/\d", regex=True).any():
            reason = "Ambiguous date format; choose a format in Prepare."
        log.append({"Column": column, "Interpretation": reason, "Type": str(working[column].dtype)})
    mapping, detection = detect_roles(working)
    return working, mapping, log + detection


def detect_roles(data):
    mapping, notes = {}, []
    for role, aliases in ALIASES.items():
        candidates = [c for c in data if normalized(c) in aliases]
        compatible = [c for c in candidates if
                      (is_numeric_dtype(data[c]) if role in NUMERIC_ROLES else
                       is_datetime64_any_dtype(data[c]) if role == "order_date" else True)]
        if len(compatible) > 1 and role.endswith("_id"):
            exact = [c for c in compatible if normalized(c) == role or normalized(c).endswith(("_id", "id"))]
            if len(exact) == 1:
                compatible = exact
        mapping[role] = compatible[0] if (len(candidates) == len(compatible) == 1) or (len(compatible) == 1 and role.endswith("_id")) else None
        if candidates:
            notes.append({"Column": ", ".join(candidates), "Interpretation":
                          f"{role}: " + ("explicit name and compatible type." if mapping[role]
                          else "ambiguous or incompatible; optional mapping needed."), "Type": "role"})
    return mapping, notes


def adapt_column_type(values, target_role):
    """Adapt a column's data type in-place when mapped to a canonical catalogue role.

    Returns (converted_series, success: bool, reason: str).
    """
    if target_role is None:
        return values, True, "Preserved as unmapped auxiliary attribute."

    missing = missing_mask(values)
    present = values[~missing]

    if target_role in NUMERIC_ROLES:
        if is_numeric_dtype(values):
            return values, True, "Already numeric."
        if present.empty:
            return pd.to_numeric(values, errors="coerce"), True, "Empty column converted to numeric float."
        text = values.astype("string").str.strip().mask(missing)
        cleaned = text.str.replace(r"[^\d.\-+eE]", "", regex=True)
        empty_after_clean = ~missing & (cleaned.str.len() == 0)
        converted = pd.to_numeric(cleaned, errors="coerce")
        finite = converted.map(lambda v: pd.notna(v) and math.isfinite(v))
        invalid = empty_after_clean | (~missing & (~finite | converted.isna()))
        if invalid.any():
            return values, False, f"Cannot convert {int(invalid.sum())} non-numeric value(s) to numbers."
        return converted, True, "Cleanly converted currency/formatted text to numeric."

    if target_role == "order_date":
        if is_datetime64_any_dtype(values):
            return values, True, "Already datetime."
        if present.empty:
            return pd.to_datetime(values, errors="coerce"), True, "Empty column converted to datetime."
        text = values.astype("string").str.strip().mask(missing)
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", None):
            try:
                if fmt:
                    converted = pd.to_datetime(text, format=fmt, exact=False, errors="coerce")
                else:
                    converted = pd.to_datetime(text, errors="coerce")
                invalid = ~missing & converted.isna()
                if not invalid.any():
                    return converted, True, f"Cleanly parsed dates ({fmt or 'flexible'})."
            except Exception:
                continue
        return values, False, "Cannot parse values as calendar dates."

    # Text / categorical / identifier roles
    if not is_numeric_dtype(values) and not is_datetime64_any_dtype(values):
        return values, True, "Preserved as text."
    return values.astype("string"), True, "Preserved as text identifier/label."


def default_settings(data, mapping, currency="Unspecified"):
    return {"mapping": mapping, "currency": currency, "filters": {}, "charts": [],
            "layout": 2, "cleaning_rules": [], "report": {},
            "models": {"frequency": "M", "horizon": 3, "clusters": 3, "iqr_multiplier": 1.5}}


def fingerprint(source_id, revision, settings):
    # Report formatting is not an analytical scope change; export signatures track it.
    analytical = {key: value for key, value in settings.items() if key != "report"}
    payload = json.dumps([source_id, revision, analytical], sort_keys=True, default=str)
    return sha256(payload.encode()).hexdigest()[:16]


ROLE_CONCEPTS = {
    "order_id": {"order", "id", "num", "number", "no", "invoice", "code", "transaction", "ordernumber"},
    "order_date": {"order", "date", "time", "datetime", "timestamp", "transaction", "sale", "invoice", "orderdate"},
    "customer_id": {"customer", "client", "account", "buyer", "name", "id", "number", "num", "customername"},
    "segment": {"segment", "tier", "group", "class", "dealsize", "deal", "size", "market", "status", "channel"},
    "product_id": {"product", "item", "sku", "code", "stockcode", "id", "part", "number", "productcode"},
    "product_name": {"product", "item", "name", "title", "description", "desc"},
    "category": {"category", "department", "line", "productline", "family", "group"},
    "sub_category": {"sub", "subcategory", "sub_category", "type"},
    "sales": {"sales", "sale", "revenue", "amount", "total", "turnover"},
    "quantity": {"quantity", "qty", "units", "unit", "sold", "ordered", "volume", "items"},
    "discount": {"discount", "rebate", "deduction"},
    "profit": {"profit", "margin", "earnings", "net"},
    "unit_price": {"price", "unitprice", "priceeach", "rate", "cost", "msrp", "list_price"},
    "unit_cost": {"unitcost", "unit_cost", "cost_per_unit"},
    "total_cost": {"cogs", "total_cost", "line_cost", "cost_of_goods"},
    "country": {"country", "nation", "ctry"},
    "state": {"state", "province", "st"},
    "city": {"city", "town", "municipality"},
    "region": {"region", "territory", "zone", "area", "district"},
    "currency": {"currency", "curr"},
}


def nlp_tokenize(header: str) -> set:
    """Decompose compound headers into subword semantic tokens."""
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(header)).lower()
    raw = [t for t in re.split(r"[^a-z0-9]+", s) if t]
    tokens = set(raw)
    subwords = ("order", "number", "num", "date", "time", "sale", "sales", "revenue",
                "quantity", "qty", "ordered", "price", "each", "unit", "cost", "cogs",
                "profit", "discount", "product", "item", "code", "line", "category",
                "customer", "client", "name", "deal", "size", "segment", "country",
                "state", "city", "region", "territory", "currency", "phone", "address",
                "postal", "zip", "contact", "first", "last", "status", "qtr", "month",
                "year", "msrp", "sold", "channel")
    for t in raw:
        for w in subwords:
            if len(t) > len(w) and w in t:
                tokens.add(w)
    return tokens


def analyze_column_semantics(data, mapping):
    """Categorize columns into active business fields, suggested mappings, and preserved auxiliary metadata."""
    assigned_columns = {v: k for k, v in mapping.items() if v}
    unmapped_roles = {r for r in ALIASES if r not in mapping or not mapping[r]}

    active_fields = []
    suggested_mappings = []
    auxiliary_fields = []

    for column in data.columns:
        dtype_str = str(data[column].dtype)
        norm = normalized(column)
        tokens = nlp_tokenize(column)

        if column in assigned_columns:
            role = assigned_columns[column]
            active_fields.append({
                "column": column,
                "role": role,
                "type": dtype_str,
                "status": "Active Core Field",
                "reason": "Direct catalogue alias match" if norm in ALIASES.get(role, set()) else "Semantic NLP match",
            })
            continue

        best_role, best_score = None, 0
        for role in unmapped_roles:
            is_compat = (is_numeric_dtype(data[column]) if role in NUMERIC_ROLES else
                         is_datetime64_any_dtype(data[column]) if role == "order_date" else True)
            if not is_compat:
                continue
            concepts = ROLE_CONCEPTS.get(role, set())
            overlap = len(tokens.intersection(concepts))
            if overlap > best_score:
                best_score = overlap
                best_role = role

        if best_role and best_score >= 1 and ("msrp" in tokens or "list" in tokens or best_score >= 2):
            suggested_mappings.append({
                "column": column,
                "suggested_role": best_role,
                "type": dtype_str,
                "confidence": "Suggested Match",
                "reason": f"Semantic affinity with '{best_role}'. Can be mapped in settings below.",
            })
            continue

        if any(t in tokens for t in ("phone", "tel", "mobile", "fax")):
            category = "Customer Contact"
            explanation = "Phone/contact detail; preserved for CRM review and exports, excluded from KPI math."
        elif any(t in tokens for t in ("address", "street", "addr", "postal", "zip", "postcode")):
            category = "Mailing / Shipping Address"
            explanation = "Street routing address; preserved for shipping and exports, excluded from regional KPIs."
        elif any(t in tokens for t in ("contact", "first", "last")):
            category = "Contact Person"
            explanation = "Individual contact representative; preserved for export."
        elif any(t in tokens for t in ("line", "sequence", "orderlinenumber")) and "number" in tokens:
            category = "Line Item Index"
            explanation = "Internal line sequence within order; preserved for raw exports."
        elif any(t in tokens for t in ("qtr", "quarter", "month", "year")) and is_numeric_dtype(data[column]):
            category = "Calendar Breakdown"
            explanation = "Calendar integer component; order_date supplies continuous time series."
        elif "status" in tokens:
            category = "Order Lifecycle"
            explanation = "Order status (e.g. Shipped/Cancelled); available for filtering in Prepare."
        elif "msrp" in tokens:
            category = "Reference Price"
            explanation = "Manufacturer list price; actual realized price is used for sales analytics."
        else:
            category = "Operational Attribute"
            explanation = "Auxiliary source attribute; safely preserved intact in raw preview and cleaned exports."

        auxiliary_fields.append({
            "column": column,
            "type": dtype_str,
            "category": category,
            "explanation": explanation,
        })

    return {
        "active": active_fields,
        "suggested": suggested_mappings,
        "auxiliary": auxiliary_fields,
    }


def currency_status(data, mapping, declared="Unspecified"):
    column = mapping.get("currency")
    if column and column in data:
        codes = data.loc[~missing_mask(data[column]), column].astype(str).str.strip().str.upper().unique()
        if len(codes) > 1:
            return "Mixed currencies", False, "Filter currency to a single value before monetary analysis."
        if missing_mask(data[column]).any():
            return "Incomplete currency", False, "Some rows lack currency; filter or prepare them explicitly."
        if len(codes) == 1:
            return str(codes[0]), True, "Currency from the dataset; no exchange conversion."
    label = declared if declared and declared != "Unspecified" else "Currency unspecified"
    return label, True, "Currency labels do not convert monetary values."
