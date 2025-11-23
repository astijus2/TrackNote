# --- START OF FILE parsing.py ---

import re
import unicodedata
import pandas as pd
from typing import List, Dict, Any

# --- ORIGINAL FUNCTIONS (REQUIRED BY APP.PY) ---

# IBAN: LT + 16..20 digits (some rows may be short/mistyped), allow spaces
IBAN_RE = re.compile(r"(?i)LT\s*\d(?:\s*\d){15,19}")

def _clean_iban(raw: str) -> str:
    # Keep 'LT' + digits, remove inner spaces
    raw = raw.strip()
    if not raw:
        return ""
    letters = "".join(ch for ch in raw if ch.isalpha()).upper()
    digits  = "".join(ch for ch in raw if ch.isdigit())
    return ("LT" if letters.upper().startswith("LT") else letters[:2].upper()) + digits

def normalize(s: str) -> str:
    s = (s or "").lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return " ".join(s.split())

def split_details(details_raw: str):
    """
    Robustly split 'Name ... LT######## ... Comment' into (name, iban, comment).
    Works with weird spacing/newlines and partial IBANs.
    """
    if not details_raw:
        return "", "", ""
    m = IBAN_RE.search(details_raw)
    if m:
        # Slice by indices to avoid spacing mismatches
        start, end = m.span()
        iban_raw = details_raw[start:end]
        name = " ".join(details_raw[:start].split())
        comment = details_raw[end:].strip(" \t-,:;")
        iban = _clean_iban(iban_raw)
    else:
        # No IBAN found: take first two tokens as name, rest as comment
        parts = details_raw.split()
        name = " ".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else "")
        comment = details_raw[len(name):].strip()
        iban = ""
    return name, iban, comment

# --- NEW PROFESSIONAL PARSER CLASS ---

# Define custom exceptions for clear error handling
class StatementParsingError(Exception):
    """Base exception for parser errors."""
    pass

class MissingColumnsError(StatementParsingError):
    """Raised when the statement is missing required columns."""
    pass

class BankStatementParser:
    """
    A professional, robust parser for Swedbank Excel statements.
    It manually locates the data table to handle files with merged cells or variable headers.
    """
    def __init__(self):
        # Configuration is centralized here.
        self.COLUMN_MAP = {
            'date': 'Data',
            'payer': 'Gavėjas/Mokėtojas',
            'details': 'Paaiškinimai',  # <-- THIS IS THE FIX
            'amount': 'Apyvarta'
        }

    def parse(self, filepath: str) -> List[Dict[str, Any]]:
        """
        Parses the given Excel file and returns a list of clean transaction data.
        Raises errors if the file format is invalid.
        """
        try:
            # Step 1: Read the entire sheet as raw data, without assuming any header.
            df = pd.read_excel(filepath, header=None)
        except Exception as e:
            raise StatementParsingError(f"Could not read the Excel file. It might be corrupted or in an old format.\n\nDetails: {e}")

        # Step 2: Manually find the header row by looking for the 'Data' column.
        header_row_index = -1
        for i, row in df.iterrows():
            # Check if any cell in the row contains our anchor value ('Data').
            if any(str(cell).strip() == self.COLUMN_MAP['date'] for cell in row):
                header_row_index = i
                break
        
        if header_row_index == -1:
            raise StatementParsingError(f"Could not find the header row. Please ensure the file contains a '{self.COLUMN_MAP['date']}' column.")

        # Step 3: Set the found row as the header and discard everything above it.
        df.columns = df.iloc[header_row_index]
        df = df.drop(range(header_row_index + 1))
        df = df.reset_index(drop=True)
        
        # Clean column names to remove any leading/trailing whitespace or newlines.
        df.columns = df.columns.astype(str).str.strip()

        self._validate_columns(df)

        clean_transactions = []
        for _, row in df.iterrows():
            # Stop processing if we hit an empty row, which often signifies the end of the table.
            if row.isnull().all():
                break
            processed_row = self._process_row(row)
            if processed_row:
                clean_transactions.append(processed_row)
        
        return clean_transactions

    def _validate_columns(self, df: pd.DataFrame):
        """Checks if all required columns exist in the DataFrame."""
        required_cols = self.COLUMN_MAP.values()
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise MissingColumnsError(f"The statement is missing the following required columns: {', '.join(missing_cols)}")

    def _process_row(self, row: pd.Series) -> Dict[str, Any] | None:
        """Cleans and validates a single row of data."""
        amount_str = str(row.get(self.COLUMN_MAP['amount'], '')).strip()
        if not amount_str:
            return None

        try:
            cleaned_amount_str = amount_str.replace('+', '').replace(',', '.')
            amount = float(cleaned_amount_str)
        except (ValueError, TypeError):
            return None

        date = str(row.get(self.COLUMN_MAP['date'], '')).strip()
        payer = str(row.get(self.COLUMN_MAP['payer'], '')).strip()
        details = str(row.get(self.COLUMN_MAP['details'], '')).strip()

        if not date or not payer:
            return None

        return {
            'date': date,
            'payer': payer,
            'details': details,
            'amount': amount
        }

# --- END OF FILE parsing.py ---