"""
Data source abstraction - supports both local files and Google Sheets.
"""

from pathlib import Path
from typing import List, Tuple, Optional
import pandas as pd
from sheets_cache import get_cached_sheets, save_sheets_cache
import sys
import os


def get_resource_path(relative_path):
    """
    Get absolute path to resource - works for dev and for PyInstaller bundle.
    When running as bundled app, resources are in sys._MEIPASS.
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # Running in development/normal mode
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)


def _col_idx(letter: str) -> int:
    """Convert column letter to index: A->0, B->1, ..."""
    return ord(letter.upper()) - ord('A')


# ===== FILE SOURCE =====

def fetch_rows_from_file(file_path: str, cfg: dict) -> List[Tuple]:
    """
    Read from local Excel/CSV file.
    Returns list of tuples: (row_no, date, price, details)
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Load WITHOUT treating first row as header - read all rows as data
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False, header=None)
    else:
        df = pd.read_excel(path, dtype=str, engine="openpyxl", header=None)
    
    df = df.fillna("")
    rows = []

    # Use column indices (B=1, D=3, E=4 when 0-indexed)
    date_col = cfg.get("date_col", "B")
    price_col = cfg.get("price_col", "D")
    details_col = cfg.get("details_col", "E")
    
    bi = _col_idx(date_col)
    di = _col_idx(price_col)
    ei = _col_idx(details_col)
    
    max_cols = max(bi, di, ei) + 1
    values = df.astype(str).values.tolist()

    for idx, row in enumerate(values, start=1):
        # Pad short rows
        if len(row) < max_cols:
            row = row + [""] * (max_cols - len(row))
            
        date = row[bi] if bi < len(row) else ""
        price = row[di] if di < len(row) else ""
        details = row[ei] if ei < len(row) else ""
        
        rows.append((idx, str(date), str(price), str(details)))

    return rows


def test_file_source(file_path: str, cfg: dict = None) -> Tuple[int, Optional[str]]:
    """
    Test file source. Returns (row_count, error_message).
    If successful, error_message is None.
    """
    try:
        # Use minimal config for testing
        if cfg is None:
            cfg = {
                "date_col": "B",
                "price_col": "D", 
                "details_col": "E"
            }
        
        rows = fetch_rows_from_file(file_path, cfg)
        
        # Validate we got some data
        if not rows:
            return 0, "File is empty or has no data"
            
        # Check for reasonable data
        has_data = any(row[1] or row[2] or row[3] for row in rows)
        if not has_data:
            return len(rows), "Warning: No data found in expected columns"
            
        return len(rows), None
        
    except FileNotFoundError:
        return 0, "File not found"
    except pd.errors.EmptyDataError:
        return 0, "File is empty"
    except Exception as e:
        return 0, f"Error reading file: {str(e)}"


# ===== GOOGLE SHEETS SOURCE =====

def fetch_rows_from_sheets(spreadsheet_id: str, tab_name: str, 
                           credentials_path: str, cfg: dict) -> List[Tuple]:
    """
    Read from Google Sheets using service account.
    Returns list of tuples: (row_no, date, price, details)
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        raise ImportError(
            "Google Sheets support requires: pip install gspread google-auth"
        )

    # Authenticate - use get_resource_path for bundled app compatibility
    scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    resolved_path = get_resource_path(credentials_path)
    creds = Credentials.from_service_account_file(resolved_path, scopes=scopes)
    client = gspread.authorize(creds)

    # Open sheet
    try:
        sheet = client.open_by_key(spreadsheet_id)
        worksheet = sheet.worksheet(tab_name)
    except gspread.exceptions.SpreadsheetNotFound:
        raise ValueError(f"Sheet not found. Make sure to share it with the service account.")
    except gspread.exceptions.WorksheetNotFound:
        raise ValueError(f"Tab '{tab_name}' not found in spreadsheet")

    # Get all values
    values = worksheet.get_all_values()
    
    if not values:
        return []

    # Parse based on config (column letters like B/D/E)
    date_col = cfg.get("date_col", "B")
    price_col = cfg.get("price_col", "D")
    details_col = cfg.get("details_col", "E")
    
    bi = _col_idx(date_col)
    di = _col_idx(price_col)
    ei = _col_idx(details_col)
    
    rows = []
    
    # Include ALL rows starting from row 1
    for row_no, row in enumerate(values, start=1):
        # Pad short rows
        max_cols = max(bi, di, ei) + 1
        if len(row) < max_cols:
            row = row + [""] * (max_cols - len(row))
            
        date = row[bi] if bi < len(row) else ""
        price = row[di] if di < len(row) else ""
        details = row[ei] if ei < len(row) else ""
        
        rows.append((row_no, date, price, details))

    return rows


def test_sheets_source(credentials_path: str, spreadsheet_id: str, 
                       tab_name: str, cfg: dict = None) -> Tuple[int, Optional[str]]:
    """
    Test Google Sheets connection. Returns (row_count, error_message).
    If successful, error_message is None.
    """
    try:
        if cfg is None:
            cfg = {
                "date_col": "B",
                "price_col": "D",
                "details_col": "E"
            }
        
        rows = fetch_rows_from_sheets(spreadsheet_id, tab_name, credentials_path, cfg)
        
        if not rows:
            return 0, "Sheet is empty or has no data rows"
            
        # Check for reasonable data
        has_data = any(row[1] or row[2] or row[3] for row in rows)
        if not has_data:
            return len(rows), "Warning: No data found in expected columns"
            
        return len(rows), None
        
    except ImportError as e:
        return 0, f"Missing library: {str(e)}"
    except ValueError as e:
        return 0, str(e)
    except Exception as e:
        # More detailed error for auth issues
        error_str = str(e).lower()
        if 'permission' in error_str or 'forbidden' in error_str:
            return 0, "Permission denied. Share the sheet with your service account email."
        elif 'not found' in error_str:
            return 0, "Sheet not found. Check the Spreadsheet ID."
        else:
            return 0, f"Connection error: {str(e)}"


# ===== UNIFIED INTERFACE =====

def fetch_rows(cfg: dict) -> List[Tuple]:
    """
    Fetch rows from configured data source (with caching for Sheets).
    """
    # CRITICAL: Define source at the VERY START
    source = cfg.get("data_source", cfg.get("source", "file"))
    
    # Google Sheets with caching
    if source == "google_sheets" or source == "sheets":
        spreadsheet_id = cfg.get("spreadsheet_id", "")
        tab_name = cfg.get("tab_name", "Sheet1")
        credentials_path = cfg.get("credentials_path", "")
        
        if not spreadsheet_id:
            raise ValueError("No spreadsheet_id configured")
        if not credentials_path:
            raise ValueError("No credentials_path configured")
        
        # Try cache first
        cached = get_cached_sheets(spreadsheet_id, tab_name)
        # --- THIS IS THE FIX ---
        # The condition is now `is not None` so that an empty but valid cache (`[]`)
        # does not prevent a fresh fetch. It will only return if the cache is valid and fresh.
        if cached is not None:
            print(f"✓ Using cached Sheets data ({len(cached)} rows)")
            return cached
        
        # Fetch from Google Sheets
        print("📊 Fetching from Google Sheets (this may take a moment)...")
        rows = fetch_rows_from_sheets(spreadsheet_id, tab_name, credentials_path, cfg)
        
        # Save to cache
        save_sheets_cache(spreadsheet_id, tab_name, rows)
        
        return rows
    
    # Local file (no caching needed - already fast)
    elif source == "file":
        file_path = cfg.get("file_path")
        if not file_path:
            raise ValueError("No file_path configured")
        return fetch_rows_from_file(file_path, cfg)
    
    else:
        raise ValueError(f"Unknown source type: {source}")


def test_connection(cfg: dict) -> Tuple[int, Optional[str]]:
    """
    Test the configured data source.
    Returns (row_count, error_message). Error is None on success.
    """
    source = cfg.get("data_source", cfg.get("source", "file"))
    
    if source == "file":
        file_path = cfg.get("file_path")
        if not file_path:
            return 0, "No file path configured"
        return test_file_source(file_path, cfg)
        
    elif source == "google_sheets" or source == "sheets":
        spreadsheet_id = cfg.get("spreadsheet_id")
        tab_name = cfg.get("tab_name", "Sheet1")
        credentials_path = cfg.get("credentials_path")
        
        if not spreadsheet_id:
            return 0, "No spreadsheet ID configured"
        if not credentials_path:
            return 0, "No credentials configured"
            
        return test_sheets_source(credentials_path, spreadsheet_id, tab_name, cfg)
        
    else:
        return 0, f"Unknown source type: {source}"


# ===== CONVENIENCE FUNCTIONS =====

def is_configured(cfg: dict) -> bool:
    """Check if a data source is properly configured."""
    source = cfg.get("data_source", cfg.get("source", "file"))
    
    if source == "file":
        return bool(cfg.get("file_path"))
    elif source == "google_sheets" or source == "sheets":
        return bool(cfg.get("spreadsheet_id") and cfg.get("credentials_path"))
    else:
        return False


def get_source_description(cfg: dict) -> str:
    """Get a human-readable description of the data source."""
    source = cfg.get("data_source", cfg.get("source", "file"))
    
    if source == "file":
        path = cfg.get("file_path", "")
        if path:
            return f"File: {Path(path).name}"
        return "No file selected"
        
    elif source == "google_sheets" or source == "sheets":
        sheet_id = cfg.get("spreadsheet_id", "")
        tab = cfg.get("tab_name", "Sheet1")
        if sheet_id:
            return f"Google Sheets: {sheet_id[:20]}... / {tab}"
        return "No sheet configured"
        
    return "Unknown source"