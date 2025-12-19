
import re
import unicodedata
import pandas as pd
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
import os

# Try importing pypdf, but don't crash if missing (though we added it to requirements)
try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

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

# --- NEW PROFESSIONAL PARSER CLASSES ---

class StatementParsingError(Exception):
    """Base exception for parser errors."""
    pass

class MissingColumnsError(StatementParsingError):
    """Raised when the statement is missing required columns."""
    pass

class ExcelBankStatementParser:
    """
    Parser for Swedbank Excel statements.
    Manual locating of data table to handle merged cells or variable headers.
    """
    def __init__(self):
        self.COLUMN_MAP = {
            'payer': 'Gavėjas/Mokėtojas',
            'details': 'Paaiškinimai',
            'amount': 'Apyvarta',
            'iban': 'Sąskaita' # Or 'Mokėtojo sąskaita' etc.
        }

    def parse(self, filepath: str) -> List[Dict[str, Any]]:
        try:
            df = pd.read_excel(filepath, header=None)
        except Exception as e:
            raise StatementParsingError(f"Could not read the Excel file: {e}")

        # Find header row
        header_row_index = -1
        for i, row in df.iterrows():
            if any(str(cell).strip() == self.COLUMN_MAP['date'] for cell in row):
                header_row_index = i
                break
        
        if header_row_index == -1:
            raise StatementParsingError(f"Could not find the header row looking for '{self.COLUMN_MAP['date']}'.")

        df.columns = df.iloc[header_row_index]
        df = df.drop(range(header_row_index + 1))
        df = df.reset_index(drop=True)
        df.columns = df.columns.astype(str).str.strip()

        self._validate_columns(df)

        clean_transactions = []
        for _, row in df.iterrows():
            if row.isnull().all():
                continue
            processed_row = self._process_row(row)
            if processed_row:
                clean_transactions.append(processed_row)
        
        return clean_transactions

    def _validate_columns(self, df: pd.DataFrame):
        required_cols = self.COLUMN_MAP.values()
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise MissingColumnsError(f"Missing required columns: {', '.join(missing_cols)}")

    def _process_row(self, row: pd.Series) -> Dict[str, Any] | None:
        amount_str = str(row.get(self.COLUMN_MAP['amount'], '')).strip()
        if not amount_str:
            return None

        try:
            # Handle standard European formats if needed, but Swedbank export is usually standard
            # Swedbank Excel often uses ',' as decimal separator if locale is LT
            cleaned_amount_str = amount_str.replace('+', '').replace(',', '.')
            # Handle unicode minus or dash if present
            cleaned_amount_str = cleaned_amount_str.replace('−', '-') 
            amount = float(cleaned_amount_str)
        except (ValueError, TypeError):
            return None

        if amount < 0:
             return None

        date = str(row.get(self.COLUMN_MAP['date'], '')).strip()
        payer = str(row.get(self.COLUMN_MAP['payer'], '')).strip()
        details = str(row.get(self.COLUMN_MAP['details'], '')).strip()
        
        # Try to find IBAN
        iban = ""
        # Check potential IBAN columns
        potential_iban_cols = ['Sąskaita', 'Mokėtojo sąskaita', 'IBAN']
        for col in potential_iban_cols:
            if col in row.index:
                val = str(row.get(col, '')).strip()
                if val and len(val) > 10: # Basic length check
                     iban = val
                     break

        if not date:
            return None
            
        # If payer is empty, try to use Details as payer? No, keep empty.

        return {
            'date': date,
            'payer': payer,
            'details': details,
            'amount': amount,
            'iban': iban
        }

class XMLBankStatementParser:
    """
    Parser for ISO 20022 (camt.053) XML bank statements.
    """
    def __init__(self):
        self.ns = {'ns': 'urn:iso:std:iso:20022:tech:xsd:camt.053.001.02'}

    def parse(self, filepath: str) -> List[Dict[str, Any]]:
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
        except Exception as e:
            raise StatementParsingError(f"Could not parse XML file: {e}")

        entries = []
        # Find all Ntry elements. Handling potential namespace variations by stripping or using local-name() is safer, 
        # but using the fixed namespace derived from the file provided is consistent.
        # We'll use the namespace defined in __init__. 
        # Robustness check: if findall returns nothing, maybe namespace is different.
        
        ntry_elements = root.findall('.//ns:Ntry', self.ns)
        if not ntry_elements:
            # Try without namespace or wildcards if needed, but let's stick to the providing standard for now.
            pass

        for ntry in ntry_elements:
            try:
                row = self._process_entry(ntry)
                if row:
                    entries.append(row)
            except Exception:
                continue
                
        if not entries and not ntry_elements:
             raise StatementParsingError("No entries found in XML. Namespace might be mismatched.")
             
        return entries

    def _process_entry(self, ntry) -> Dict[str, Any]:
        # Booking Date
        date_el = ntry.find('ns:BookgDt/ns:Dt', self.ns)
        if date_el is None:
            return None
        date = date_el.text

        # Amount
        amount_el = ntry.find('ns:Amt', self.ns)
        if amount_el is None:
            return None
        try:
            if amount_el.text is None:
                return None
            val = float(amount_el.text)
        except (ValueError, TypeError):
            return None

        # Credit/Debit Indicator
        cd_el = ntry.find('ns:CdtDbtInd', self.ns)
        if cd_el is None:
            return None
        
        indicator = cd_el.text
        if indicator:
            indicator = indicator.upper()
        
        # FILTER: Only keep incoming (Credit) transactions
        if indicator == 'DBIT':
            return None
        
        amount = abs(val)

        # Transaction Details - Payer/Payee
        tx_dtls = ntry.find('ns:NtryDtls/ns:TxDtls', self.ns)
        payer = ""
        details = ""

        iban = ""

        if tx_dtls is not None:
            # Related Parties
            rltd = tx_dtls.find('ns:RltdPties', self.ns)
            if rltd is not None:
                # With DBIT filtered out, we are only handling CRDT (Income)
                # We want the Debtor (Sender)
                node = rltd.find('ns:Dbtr/ns:Nm', self.ns)
                
                if node is not None:
                    payer = node.text
                
                # Try to extract IBAN from structured node first
                iban_node = rltd.find('ns:DbtrAcct/ns:Id/ns:IBAN', self.ns)
                if iban_node is not None:
                     iban = iban_node.text
            
            # Remittance Info - Join ALL Ustrd tags
            rmt = tx_dtls.find('ns:RmtInf', self.ns)
            if rmt is not None:
                ustrd_nodes = rmt.findall('ns:Ustrd', self.ns)
                if ustrd_nodes:
                    details = " ".join([node.text for node in ustrd_nodes if node.text])
                
                # Also check Strd (Structured) for Ref
                if not details: # Or append to it? Let's check Strd as well.
                    strd_nodes = rmt.findall('ns:Strd', self.ns)
                    refs = []
                    for strd in strd_nodes:
                        # Extract Creditor Reference Information
                        cdtr_ref = strd.find('ns:CdtrRefInf/ns:Ref', self.ns)
                        if cdtr_ref is not None and cdtr_ref.text:
                            refs.append(cdtr_ref.text)
                    
                    if refs:
                        details_part = " ".join(refs)
                        if details:
                            details += " " + details_part
                        else:
                            details = details_part

        # Fallback: If IBAN is missing, try to find it in the details
        if not iban and details:
             # Use split_details to see if we can extract it
             _, found_iban, _ = split_details(details)
             if found_iban:
                 iban = found_iban

        return {
            'date': date,
            'payer': payer or "Unknown",
            'details': details,
            'amount': amount,
            'iban': iban
        }

class SmartPDFParser:
    """
    Robust Stream-Based Parser.
    Instead of line-by-line, it treats text as a stream and segments by Date.
    """
    def parse(self, filepath: str) -> List[Dict[str, Any]]:
        if not PYPDF_AVAILABLE:
            raise StatementParsingError("pypdf library is not installed.")

        try:
            reader = PdfReader(filepath)
            full_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    full_text.append(text)
            
            # Join with spaces to handle wrapping, but keep some structure if possible?
            # Actually, newlines are useful delimiters. Let's keep them but maybe clean up later.
            full_stream = "\n".join(full_text)
        except Exception as e:
            raise StatementParsingError(f"Could not read PDF: {e}")

        clean_transactions = []
        
        # 1. Find all Date Anchors (YYYY-MM-DD)
        # We assume transactions start with a date.
        date_iter = re.finditer(r'(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)', full_stream)
        
        # Store (start_index, date_str) tuples
        anchors = []
        for m in date_iter:
            anchors.append((m.start(), m.group(1)))
            
        if not anchors:
            raise StatementParsingError("No dates found in PDF. Unknown format.")
            
        # 2. Process blocks between anchors
        for i in range(len(anchors)):
            start_idx, date_str = anchors[i]
            
            # End index is the start of the next date, or end of string
            if i < len(anchors) - 1:
                end_idx = anchors[i+1][0]
            else:
                end_idx = len(full_stream)
            
            # Extract raw block text
            raw_block = full_stream[start_idx:end_idx]
            
            # Remove the date itself from the start (it matches date_str)
            # The regex matched at start_idx, so `date_str` is at the beginning.
            # We skip its length.
            block_content = raw_block[len(date_str):].strip()
            
            parsed_tx = self._parse_block(date_str, block_content)
            if parsed_tx:
                clean_transactions.append(parsed_tx)
                
        return clean_transactions

    def _parse_block(self, date_str: str, text: str) -> Dict[str, Any] | None:
        """
        Extracts Amount, Name, IBAN, Details from a text block.
        """
        # 1. Extract Amount
        # Look for the first valid amount pattern.
        # Pattern: space/start + [+-]? + digits + [.,] + digit{2}
        # We want to be strict about boundary to avoid picking up ID numbers.
        # But flexible about spaces between sign and number: `+ 98.00` (unlikely but possible)
        # or `98 .00` (bad OCR). Let's stick to standard `[-+]?\d+[.,]\d{2}`.
        
        # Capture: (Sign)(Integer part)(Separator)(Decimal part)
        amt_pattern = re.compile(r'(?<![\d.,])([+−-]?)(\d[\d\s]*)[.,](\d{2})(?![\d.,])')
        
        # We take the *first* match as the transaction amount.
        m_amt = amt_pattern.search(text)
        if not m_amt:
            return None # No amount found -> maybe not a transaction row?

        # Parse Amount
        sign, integer_part, decimal_part = m_amt.groups()
        
        # Clean integer part (remove spaces)
        integer_part = integer_part.replace(' ', '').replace('\xa0', '')
        
        # Reconstruct valid float string
        raw_float_str = f"{sign}{integer_part}.{decimal_part}".replace('−', '-')
        try:
            amount = float(raw_float_str)
        except ValueError:
            return None
            
        if amount < 0:
            return None # Skip outgoing
            
        # 2. Extract IBAN
        # IBAN regex (LT...)
        # We use the global IBAN_RE or a local one.
        m_iban = IBAN_RE.search(text)
        iban = ""
        if m_iban:
            iban = _clean_iban(m_iban.group(0))
        
        # 3. Separate Name and Details
        # Strategy: Remove Amount substring. Remove IBAN substring. Clean up.
        # The remainder is "Name + Comments". 
        # Usually, Name appears BEFORE the text block or right after date/amount?
        # Actually, in the user example: "2025-11-13 +98.00 ALEŠKEVIČIENĖ GRETA LT..."
        # So structure is: [Date] [Amount] [Name] [IBAN] [Comment]
        
        # Let's effectively "mask" the parts we found to isolate the text.
        
        # Get spans to remove
        spans_to_remove = []
        spans_to_remove.append(m_amt.span())
        if m_iban:
           spans_to_remove.append(m_iban.span())
           
        # Sort spans descending to remove correctly
        spans_to_remove.sort(key=lambda x: x[0], reverse=True)
        
        remaining_text = text
        for start, end in spans_to_remove:
            # Replace with space
            remaining_text = remaining_text[:start] + " " + remaining_text[end:]
            
        # Collapse spaces
        clean_rem = list(filter(None, remaining_text.split())) # Token list
        
        # Heuristic: 
        # If IBAN was found:
        #   Everything BEFORE IBAN's original position -> Name
        #   Everything AFTER IBAN's original position -> Comment
        # But we just mashed it into a string.
        # Let's retry using positions relative to the IBAN index in the *original* string.
        
        final_name = ""
        final_comment = ""
        
        if m_iban:
            iban_start_idx = m_iban.start()
            
            # Name part is mainly before IBAN, excluding Amount
            # We need to construct a "Name" string from text distinct from amount/IBAN
            
            # Simple approach: 
            # 1. Take substring [0 : iban_start]
            # 2. Remove Amount from it
            # 3. Clean
            
            pre_iban_text = text[:iban_start_idx]
            
            # Remove amount if it was in this region
            if m_amt.start() < iban_start_idx:
                # Amount is before IBAN
                # Remove it
                pre_iban_text = pre_iban_text[:m_amt.start()] + " " + pre_iban_text[m_amt.end():]
                
            final_name = " ".join(pre_iban_text.split())
            
            # Comment part is AFTER IBAN
            post_iban_text = text[m_iban.end():]
            
            # Remove amount if it was here (unlikely for Swedbank, but possible)
            if m_amt.start() > m_iban.end():
                 post_iban_text = post_iban_text[:m_amt.start()-m_iban.end()] + " " + post_iban_text[m_amt.end()-m_iban.end():]
            
            final_comment = " ".join(post_iban_text.split())

            # FIX: If Name was not found before IBAN, it might be AFTER IBAN (e.g. "Date Amount IBAN Name Details")
            # In that case, `final_name` is empty (or just spaces), and `final_comment` contains "Name Details".
            if not final_name and final_comment:
                # Use split_details heuristic to extract name from the comment block
                extracted_name, _, extracted_details = split_details(final_comment)
                if extracted_name:
                    final_name = extracted_name
                    final_comment = extracted_details
            
        else:
            # No IBAN. Everything is Name/Comment.
            # Use the robust split helper
            full_str = " ".join(clean_rem)
            final_name, final_iban_dummy, final_comment = split_details(full_str)
            
        return {
            'date': date_str,
            'payer': final_name if final_name else "Statement Entry",
            'details': final_comment,
            'amount': amount,
            'iban': iban
        }

# Alias the new class to the old name so we don't break the Factory 
# (Or we could update the Factory, but this is cleaner diff-wise)
PDFBankStatementParser = SmartPDFParser

class BankStatementParser:
    """
    Facade class that delegates to the appropriate parser based on file extension.
    """
    def parse(self, filepath: str) -> List[Dict[str, Any]]:
        ext = os.path.splitext(filepath)[1].lower()
        
        if ext in ('.xlsx', '.xls'):
            transactions = ExcelBankStatementParser().parse(filepath)
        elif ext == '.xml':
            transactions = XMLBankStatementParser().parse(filepath)
        elif ext == '.pdf':
            transactions = PDFBankStatementParser().parse(filepath)
        else:
            raise StatementParsingError(f"Unsupported file format: {ext}")
            
        # Filter out irrelevant transactions
        return [t for t in transactions if not self.should_ignore_transaction(t)]

    def should_ignore_transaction(self, transaction: Dict[str, Any]) -> bool:
        """
        Check if transaction should be ignored based on details.
        Filters out merchant terminal payouts/settlements.
        """
        details = transaction.get('details', '')
        if not details:
            return False
            
        # Check for the specific pattern mentioned by user:
        # "Swedbank IMONE... PREKYB. ID... TERM. SK...."
        # We'll check for the co-existence of "PREKYB. ID" and "TERM. SK."
        # using a case-insensitive check to be safe, although the example was uppercase.
        
        details_upper = details.upper()
        if "PREKYB. ID" in details_upper and "TERM. SK." in details_upper:
            return True
            
        return False