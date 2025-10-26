import re, unicodedata

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
