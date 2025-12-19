import re
import unittest
from parsing import SmartPDFParser

class MockPage:
    def __init__(self, text):
        self.text = text
    def extract_text(self):
        return self.text

class MockPdfReader:
    def __init__(self, pages_text):
        self.pages = [MockPage(t) for t in pages_text]

# Patch parsing.py to use our MockPdfReader
import parsing
parsing.PdfReader = lambda f: MockPdfReader(f) # f is ignored string here
parsing.PYPDF_AVAILABLE = True

class TestSmartPDFParser(unittest.TestCase):
    def setUp(self):
        self.parser = SmartPDFParser()

    def test_multiline_and_plus_sign(self):
        # This simulates the "Stream" of text coming from PDF
        # Note: Newlines, weird spaces, etc.
        # User Case 1: "2025-11-13 +98.00 ALEŠKEVIČIENĖ GRETA LT..."
        # User Case 2: "2025-11-14 +78.00 AUŠRA SEREIKIENĖ LT... Aušra Ausryte" (spanning lines potentially)
        
        raw_text = """
        HEADER STUFF
        
        2025-11-13 +98.00 ALEŠKEVIČIENĖ 
        GRETA LT237044060007980165 užsak.nr3279,prekėF95xljuodas
        
        2025-11-14 +78.00 
        AUŠRA SEREIKIENĖ LT227300010138198179 
        Aušra Ausryte
        
        2025-11-01 -10.00 OUTGOING PAYMENT SHOULD BE SKIPPED
        
        FOOTER STUFF
        """
        
        
        # Redoing the patch logic slightly for this test method:
        parsing.PdfReader = lambda f: MockPdfReader([raw_text])
        
        txs = self.parser.parse("dummy.pdf")
        
        print("\nParsed Transactions:")
        for t in txs:
            print(t)
            
        self.assertEqual(len(txs), 2, "Should parse 2 incoming transactions (skipped 1 outgoing)")
        
        # Check Tx 1
        t1 = txs[0]
        self.assertEqual(t1['date'], '2025-11-13')
        self.assertEqual(t1['amount'], 98.00)
        self.assertEqual(t1['iban'], 'LT237044060007980165')
        self.assertIn('ALEŠKEVIČIENĖ GRETA', t1['payer'])
        self.assertIn('užsak.nr3279', t1['details'])
        
        # Check Tx 2
        t2 = txs[1]
        self.assertEqual(t2['date'], '2025-11-14')
        self.assertEqual(t2['amount'], 78.00)
        self.assertEqual(t2['iban'], 'LT227300010138198179')
        self.assertIn('AUŠRA SEREIKIENĖ', t2['payer'])
        self.assertIn('Aušra Ausryte', t2['details'])

if __name__ == "__main__":
    unittest.main()
