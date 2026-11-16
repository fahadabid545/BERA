"""Cells written to a spreadsheet or CSV: text that starts like a formula is quoted, so a file
name or title someone chose can never run as a formula when the file is opened."""

FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_STARTS) else text
