
import unittest
import xml.etree.ElementTree as ET
from parsing import XMLBankStatementParser

class TestXMLParsing(unittest.TestCase):
    def setUp(self):
        self.parser = XMLBankStatementParser()

    def test_structured_remittance_info(self):
        # XML snippet simulating the issue (Strd instead of Ustrd)
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
    <BkToCstmrStmt>
        <Stmt>
            <Ntry>
                <BookgDt><Dt>2025-11-06</Dt></BookgDt>
                <Amt Ccy="EUR">40.00</Amt>
                <CdtDbtInd>CRDT</CdtDbtInd>
                <NtryDtls>
                    <TxDtls>
                        <RltdPties>
                            <Dbtr><Nm>DAIVA ŠALTINIENĖ</Nm></Dbtr>
                            <DbtrAcct><Id><IBAN>LT057300010009757487</IBAN></Id></DbtrAcct>
                        </RltdPties>
                        <RmtInf>
                            <Strd>
                                <CdtrRefInf>
                                    <Tp><CdOrPrtry><Cd>SCOR</Cd></CdOrPrtry></Tp>
                                    <Ref>304615435</Ref>
                                </CdtrRefInf>
                            </Strd>
                        </RmtInf>
                    </TxDtls>
                </NtryDtls>
            </Ntry>
        </Stmt>
    </BkToCstmrStmt>
</Document>
"""
        # Save to temp file
        with open("temp_test.xml", "w") as f:
            f.write(xml_content)

        results = self.parser.parse("temp_test.xml")
        
        print("\nParsed XML Transaction:")
        print(results[0])

        self.assertEqual(len(results), 1)
        # Verify Name
        self.assertEqual(results[0]['payer'], "DAIVA ŠALTINIENĖ")
        # Verify Details - This should contain the Ref value "304615435"
        # Currently it will likely fail (be empty)
        self.assertIn("304615435", results[0]['details'], "Details should contain the Structured Reference")

if __name__ == "__main__":
    unittest.main()
