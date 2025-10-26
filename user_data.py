import json, os, sys
from pathlib import Path
from typing import Optional, Dict, Any

PRODUCT_NAME = "TrackNote"

def _platform_data_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / PRODUCT_NAME

def user_data_dir() -> Path:
    p = _platform_data_dir()
    p.mkdir(parents=True, exist_ok=True)
    (p / "logs").mkdir(parents=True, exist_ok=True)
    return p

# ----- Notes store -----
def _notes_path() -> Path:
    return user_data_dir() / "notes_store.json"

def load_notes() -> Dict[str, str]:
    p = _notes_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_notes(notes: Dict[str, str]) -> None:
    try:
        _notes_path().write_text(
            json.dumps(notes or {}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass  # never crash UI on IO errors

# ----- User config (copy of bundled config.json) -----
def _user_config_path() -> Path:
    return user_data_dir() / "user_config.json"

def _bundle_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", os.getcwd()))
    return Path(os.getcwd())

def create_user_config_if_missing(version: str = "") -> None:
    upath = _user_config_path()
    if upath.exists():
        return
    # copy defaults from bundled config.json if present
    data = {}
    try:
        bundle_cfg = _bundle_base() / "config.json"
        if bundle_cfg.exists():
            data = json.loads(bundle_cfg.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    
    # Set first run date (NEW!)
    import datetime
    data["first_run_date"] = datetime.datetime.now().isoformat()
    
    if version:
        data.setdefault("version", version)
    try:
        upath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def read_user_config() -> Dict[str, Any]:
    upath = _user_config_path()
    if not upath.exists():
        create_user_config_if_missing()
    try:
        return json.loads(upath.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_user_config(cfg: Dict[str, Any]) -> None:
    try:
        _user_config_path().write_text(json.dumps(cfg or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

# ----- License key -----
def _license_path() -> Path:
    return user_data_dir() / "license.key"

def read_license_key() -> Optional[str]:
    p = _license_path()
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return None

def store_license_key(key: str) -> None:
    try:
        _license_path().write_text((key or "").strip(), encoding="utf-8")
    except Exception:
        pass
