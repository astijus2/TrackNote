"""
Google Sheets caching to reduce load times and API quota usage.
"""

import json
import time
from pathlib import Path
from user_data import user_data_dir

# Cache configuration
CACHE_DURATION = 300  # 5 minutes (300 seconds)
CACHE_FILE = user_data_dir() / "sheets_cache.json"


def get_cached_sheets(spreadsheet_id: str, tab_name: str):
    """
    Get cached Sheets data if still fresh.
    
    Args:
        spreadsheet_id: Google Sheets ID
        tab_name: Tab/worksheet name
        
    Returns:
        List of rows if cache is fresh, None otherwise
    """
    try:
        if not CACHE_FILE.exists():
            return None
        
        # Load cache file
        cache_data = json.loads(CACHE_FILE.read_text())
        
        # Check if cache matches this sheet
        if cache_data.get('spreadsheet_id') != spreadsheet_id:
            return None
        if cache_data.get('tab_name') != tab_name:
            return None
        
        # Check if cache is still fresh (within 5 minutes)
        cached_time = cache_data.get('timestamp', 0)
        age_seconds = time.time() - cached_time
        
        if age_seconds > CACHE_DURATION:
            return None  # Cache expired
        
        # Cache is fresh - return the data
        rows = cache_data.get('rows', [])
        print(f"✓ Using cached Sheets data (age: {int(age_seconds)}s)")
        return rows
    
    except Exception as e:
        # If anything goes wrong reading cache, just return None
        print(f"⚠ Cache read error: {e}")
        return None


def save_sheets_cache(spreadsheet_id: str, tab_name: str, rows: list):
    """
    Save Sheets data to cache.
    
    Args:
        spreadsheet_id: Google Sheets ID
        tab_name: Tab/worksheet name
        rows: List of row tuples to cache
    """
    try:
        # Ensure cache directory exists
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Prepare cache data
        cache_data = {
            'spreadsheet_id': spreadsheet_id,
            'tab_name': tab_name,
            'timestamp': time.time(),
            'rows': rows,
            'row_count': len(rows)
        }
        
        # Write to file
        CACHE_FILE.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2))
        print(f"✓ Cached {len(rows)} rows from Sheets")
        
    except Exception as e:
        # Don't crash if caching fails - just log it
        print(f"⚠ Could not save cache: {e}")


def clear_cache():
    """Clear the Sheets cache file."""
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
            print("✓ Sheets cache cleared")
            return True
        else:
            print("ℹ No cache file to clear")
            return False
    except Exception as e:
        print(f"⚠ Could not clear cache: {e}")
        return False


def get_cache_info():
    """
    Get information about the current cache.
    
    Returns:
        Dict with cache info, or None if no cache exists
    """
    try:
        if not CACHE_FILE.exists():
            return None
        
        cache_data = json.loads(CACHE_FILE.read_text())
        
        timestamp = cache_data.get('timestamp', 0)
        age_seconds = time.time() - timestamp
        is_fresh = age_seconds <= CACHE_DURATION
        
        return {
            'spreadsheet_id': cache_data.get('spreadsheet_id', 'unknown'),
            'tab_name': cache_data.get('tab_name', 'unknown'),
            'row_count': cache_data.get('row_count', 0),
            'age_seconds': int(age_seconds),
            'age_minutes': round(age_seconds / 60, 1),
            'is_fresh': is_fresh,
            'expires_in': max(0, CACHE_DURATION - age_seconds) if is_fresh else 0
        }
    except Exception:
        return None