
import unittest
import parsing
from parsing import SmartPDFParser

class MockPage:
    def __init__(self, text):
        self.text = text
    def extract_text(self):
        return self.text

class MockPdfReader:
    def __init__(self, pages_text):
        self.pages = [MockPage(t) for t in pages_text]

parsing.PdfReader = lambda f: MockPdfReader(f)
parsing.PYPDF_AVAILABLE = True

class TestParsingIssues(unittest.TestCase):
    def setUp(self):
        self.parser = SmartPDFParser()

    def test_advanced_cases(self):
        # Case 1: Name AFTER IBAN (possible if format varies)
        # Case 2: No IBAN present (internal transfer/cash?)
        # Case 3: Weird spacing within Name
        
        raw_text = """
2025-11-13 +10.00 LT237044060007980165 Aleškevičienė Greta Payment1
2025-11-13 +20.00 Butkienė ramunė PaymentNoIBAN
2025-11-13 +30.00 . Daiva  Šaltinienė  LT237044060007980000 . PaymentSpaces
"""
        parsing.PdfReader = lambda f: MockPdfReader([raw_text])
        txs = self.parser.parse("dummy.pdf")
        
        print("\n--- Advanced Parsing Results ---")
        for i, t in enumerate(txs):
            print(f"[{i}] Name: '{t['payer']}' | Details: '{t['details']}'")

        # Expectation: Names should be captured as payer, not details
        # For Case 1 (Name after IBAN), current logic might put it in Details
        # For Case 2 (No IBAN), split_details might work if 2 words
        
        # We suspect Case 1 might be the issue if the statement format varies.
        # But let's see.
        
    def test_trailing_garbage(self):
        # User reported these names specifically.
        # Maybe they are followed by something that looks like part of the name?
        # "Butkienė ramunė 123" -> split_details takes 2 words -> "Butkienė ramunė", remainder "123". Correct.
        pass

if __name__ == "__main__":
    unittest.main()
