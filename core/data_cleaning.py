"""Small, testable profiling and cleaning operations; never mutate the input."""

import math

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_integer_dtype, is_numeric_dtype

DATE_FORMATS = {
    "YYYY-MM-DD (2026-10-28)": "%Y-%m-%d",
    "DD/MM/YYYY (28/10/2026)": "%d/%m/%Y",
    "MM/DD/YYYY (10/28/2026)": "%m/%d/%Y",
}
ACTIONS = [
    "Remove duplicate rows",
    "Drop rows with missing values",
    "Fill missing values",
    "Convert to number",
    "Convert to date",
]


def missing_mask(values: pd.Series) -> pd.Series:
    """Count nulls and whitespace-only strings, but not literal 'NA' or 'null'."""
    return values.isna() | values.astype("string").str.strip().eq("").fillna(False)


def conversion_preview(values: pd.Series, kind: str, date_format="%Y-%m-%d"):
    """Return a candidate column and a mask of invalid nonmissing source values.

    Coercion is used only to detect failures. apply_cleaning refuses to save the
    candidate if any invalid nonmissing values would be lost.
    """
    missing = missing_mask(values)
    text = values.astype("string").str.strip().mask(missing)
    if kind == "number":
        if is_datetime64_any_dtype(values):
            raise ValueError("A date column cannot be converted to a number here.")
        converted = pd.to_numeric(text, errors="coerce")
        finite = converted.map(lambda value: pd.notna(value) and math.isfinite(value))
        invalid = ~missing & (~finite | converted.isna())
    elif kind == "date":
        if date_format not in DATE_FORMATS.values():
            raise ValueError("Choose one of the supported date formats.")
        converted = (
            values.copy(deep=True) if is_datetime64_any_dtype(values)
            else pd.to_datetime(text, format=date_format, exact=False, errors="coerce")
        )
        invalid = ~missing & converted.isna()
    else:
        raise ValueError("Choose number or date conversion.")
    return converted, invalid


def profile_data(data: pd.DataFrame) -> pd.DataFrame:
    """Describe every column. Type hints are suggestions, not business rules."""
    rows = []
    for column in data.columns:
        values = data[column]
        missing = missing_mask(values)
        present = values[~missing]
        numeric_count = date_count = 0
        if is_datetime64_any_dtype(values):
            hint = "Date already assigned"
        elif is_numeric_dtype(values):
            hint = "Number already assigned"
        elif present.empty:
            hint = "No nonmissing values to assess"
        else:
            _, bad_numbers = conversion_preview(present, "number")
            _, bad_dates = conversion_preview(present, "date")
            numeric_count = int((~bad_numbers).sum())
            date_count = int((~bad_dates).sum())
            name = str(column).strip().lower()
            leading_zeros = present.astype("string").str.match(r"[+-]?0\d+").any()
            if name == "id" or name.endswith("_id") or leading_zeros:
                hint = "Keep text if this is an identifier"
            elif numeric_count == len(present):
                hint = "Number candidate; confirm its meaning"
            elif date_count == len(present):
                hint = "Date candidate (YYYY-MM-DD)"
            elif numeric_count or date_count:
                hint = "Mixed values; review before conversion"
            else:
                hint = "Text; no supported number/date pattern found"
        rows.append({
            "Column": column,
            "Current dtype": str(values.dtype),
            "Missing": int(missing.sum()),
            "Missing %": round(100 * missing.sum() / len(data), 1) if len(data) else 0.0,
            "Number-compatible text": numeric_count,
            "ISO-date-compatible text": date_count,
            "Type guidance": hint,
        })
    return pd.DataFrame(rows)


def quality_summary(data: pd.DataFrame) -> dict:
    return {
        "Rows": len(data),
        "Columns": len(data.columns),
        "Missing cells": sum(int(missing_mask(data[c]).sum()) for c in data.columns),
        "Duplicate rows beyond first": int(data.duplicated().sum()),
    }


def apply_cleaning(data: pd.DataFrame, action: str, columns=None,
                   fill_value="", date_format="%Y-%m-%d") -> pd.DataFrame:
    """Apply exactly one explicit action to a copy, or raise ValueError unchanged."""
    if action not in ACTIONS:
        raise ValueError("Choose a supported cleaning action.")
    result = data.copy(deep=True)
    columns = columns or []
    if action == "Remove duplicate rows":
        return result.drop_duplicates(keep="first")
    if not columns:
        raise ValueError("Select at least one column.")
    if any(column not in data.columns for column in columns):
        raise ValueError("A selected column is not in the current dataset.")
    if action == "Drop rows with missing values":
        drop = pd.Series(False, index=result.index)
        for column in columns:
            drop |= missing_mask(result[column])
        return result.loc[~drop]
    if len(columns) != 1:
        raise ValueError("Select exactly one column for this action.")
    column = columns[0]
    values = result[column]
    if action == "Fill missing values":
        if not str(fill_value).strip():
            raise ValueError("Enter a nonblank replacement value.")
        if not missing_mask(values).any():
            return result
        replacement = fill_value
        if is_numeric_dtype(values) or is_datetime64_any_dtype(values):
            kind = "date" if is_datetime64_any_dtype(values) else "number"
            converted, invalid = conversion_preview(pd.Series([str(fill_value)]), kind, date_format)
            if invalid.any():
                raise ValueError("The replacement must match the column's number/date type.")
            replacement = converted.iloc[0]
            # Nullable integer columns cannot hold a fractional replacement.
            if is_integer_dtype(values) and replacement % 1 != 0:
                result[column] = values.astype("Float64")
        try:
            result.loc[missing_mask(values), column] = replacement
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("The replacement is outside this column's supported type or range.") from error
    else:
        kind = "number" if action == "Convert to number" else "date"
        converted, invalid = conversion_preview(values, kind, date_format)
        if invalid.any():
            raise ValueError(
                f"Conversion blocked: {int(invalid.sum())} nonmissing values are invalid. "
                "The working data is unchanged. Correct the source file and re-upload, "
                "or choose a different column/date format."
            )
        if missing_mask(values).all():
            raise ValueError("This column has no nonmissing values to convert.")
        result[column] = converted
    return result
