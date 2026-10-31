"""Validate a CSV or Excel upload and return its contents as a Pandas table."""

import csv
import datetime
from io import BytesIO, StringIO

import openpyxl
import pandas as pd

MAX_UPLOAD_MB = 10
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def load_csv(filename: str, contents: bytes) -> pd.DataFrame:
    """Read a UTF-8 CSV or .xlsx workbook without changing values or data types.

    Raise ValueError with a user-friendly message if the file is unsupported.
    Parse once with Python's CSV reader or openpyxl so duplicate headers and
    uneven rows are caught before Pandas can rename columns or infer types.
    """
    ext = filename.lower()
    if not (ext.endswith(".csv") or ext.endswith(".xlsx")):
        raise ValueError("Choose a file with a .csv extension or .xlsx extension.")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise ValueError("The file is too large. Choose a file of 10 MB or less.")

    if ext.endswith(".xlsx"):
        return _read_excel(contents)
    return _read_csv(contents)


def _read_csv(contents: bytes) -> pd.DataFrame:
    try:
        # utf-8-sig also accepts the optional BOM written by some spreadsheet apps.
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(
            "The file is not UTF-8 text. Export it as CSV UTF-8 and try again."
        ) from error

    if not text.strip():
        raise ValueError("The file is empty. Add column names and at least one data row.")
    if "\x00" in text:
        raise ValueError("The file contains null bytes. Export it as CSV UTF-8 and try again.")

    headers = None
    records = []
    reader = csv.reader(StringIO(text, newline=""), strict=True)
    try:
        for row in reader:
            # An empty physical line has no cells; a row such as ',,' has cells.
            if not row:
                continue
            if headers is None:
                headers = row
                if len(headers) == 1 and any(separator in headers[0] for separator in (';', '\t')):
                    raise ValueError("This looks like a semicolon/tab-separated file. Export comma-separated CSV UTF-8.")
                if any(not name.strip() for name in headers):
                    raise ValueError("Every column needs a nonempty name in the header row.")
                if len(set(headers)) != len(headers):
                    raise ValueError("Column names must be unique. Rename duplicate headers.")
            else:
                if len(row) != len(headers):
                    raise ValueError(
                        f"The record ending on line {reader.line_num} has {len(row)} "
                        f"fields; the header has {len(headers)}. Check commas and quotes."
                    )
                records.append(row)
    except csv.Error as error:
        raise ValueError(
            "The CSV could not be read. Check quotation marks and very large cells "
            "(each field must fit within the CSV reader's limit)."
        ) from error

    if not records:
        raise ValueError("The CSV has column names but no data rows. Add at least one row.")

    # CSV cells are strings: keep blanks, leading zeros, and literal 'NA' unchanged.
    return pd.DataFrame(records, columns=headers, dtype=str)


def _read_excel(contents: bytes) -> pd.DataFrame:
    try:
        wb = openpyxl.load_workbook(BytesIO(contents), read_only=True, data_only=True)
    except Exception as error:
        raise ValueError("The Excel file could not be read. Ensure it is a valid .xlsx workbook.") from error

    sheet = wb.active
    if sheet is None:
        raise ValueError("The Excel workbook contains no active worksheet.")

    rows_iter = sheet.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        raise ValueError("The Excel file is empty. Add column names and at least one data row.")

    headers = [str(cell).strip() if cell is not None else "" for cell in header_row]
    while headers and not headers[-1]:
        headers.pop()

    if not headers or all(not h for h in headers):
        raise ValueError("The Excel file is empty. Add column names and at least one data row.")
    if any(not name for name in headers):
        raise ValueError("Every column needs a nonempty name in the header row.")
    if len(set(headers)) != len(headers):
        raise ValueError("Column names must be unique. Rename duplicate headers.")

    records = []
    for row in rows_iter:
        if not any(v is not None and str(v).strip() != "" for v in row):
            continue
        row_strs = []
        for v in row[:len(headers)]:
            if v is None:
                row_strs.append("")
            elif isinstance(v, datetime.datetime):
                if v.hour == 0 and v.minute == 0 and v.second == 0:
                    row_strs.append(v.strftime("%Y-%m-%d"))
                else:
                    row_strs.append(v.strftime("%Y-%m-%d %H:%M:%S"))
            elif isinstance(v, datetime.date):
                row_strs.append(v.strftime("%Y-%m-%d"))
            else:
                row_strs.append(str(v))
        while len(row_strs) < len(headers):
            row_strs.append("")
        records.append(row_strs)

    if not records:
        raise ValueError("The Excel file has column names but no data rows. Add at least one row.")

    return pd.DataFrame(records, columns=headers, dtype=str)


load_table = load_csv
