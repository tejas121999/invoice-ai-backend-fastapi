import unittest

from app.utils.invoice_parser import parse_invoice_fields


INVOICE_57_TEXT = """FREELANCE INVOICE

1909 Sugar Camp Road, Owatonna, MN, 5506 - (123) 1234567

Client Information                     Invoice Details

Email                                       Invoice Number
bmcvane0@uol.com.br                         4

Phone Number                              Invoice Date
+12 (33) 540-1602                                08/21/2016

Address
009 John Wall Avenue, 79737 South
Parkway
Louisville, Kentucky, 40225
United States

Service List

 Description                                                            Amount

 Napkin -
 Beverage 1 Ply                                                                    $3.00
 $3.00 x 1

 Bread Bowl Plain
                                                                                 $36.00
 $36.00 x 1

                                       Total                                                $39.00

                Thank You For Your Business!
"""

INVOICE_56_TEXT = """BrightWave Technologies

245 Market Street

San Francisco

United StatesInvoice 94105

BILL TO: INVOICE #

Northstar Retail Inc. BW-2026-0810

880 Madison Avenue DATE

New York 10-Aug-2026

United States INVOICE DUE DATE

10021 25-Aug-2026

ITEMS DESCRIPTION QUANTITY PRICE TAX AMOUNT

Laptop Dock USB-C 12-in-1 docking station 2 $189.00 9% $412.02

Wireless Combo Wireless keyboard and mouse 3 $79.00 9% $258.33

IPS Monitor 27-inch Full HD IPS monitor 2 $249.00 9% $542.82

Power Adapter USB-C 100W power adapter 2 $59.00 9% $128.62

HD Webcam 1080p webcam with microphone 1 $89.00 9% $97.01

Laptop Stand Adjustable aluminum laptop stand 2 $45.00 9% $98.10

NOTES: TOTAL

Payment due within 15 days. Thank you for your business. $1,536.90

This invoice was generated with the help of Wave Financial Inc."""


class InvoiceParserRegressionTests(unittest.TestCase):
    def test_invoice_57_two_column_number_and_unidentified_vendor(self):
        fields = parse_invoice_fields(INVOICE_57_TEXT)["fields"]

        self.assertEqual(fields["invoiceNumber"], "4")
        self.assertIsNone(fields["vendorName"])
        self.assertEqual(fields["invoiceDate"], "2016-08-21")
        self.assertIsNone(fields["dueDate"])
        self.assertIsNone(fields["subtotal"])
        self.assertIsNone(fields["taxAmount"])
        self.assertEqual(fields["totalAmount"], 39.0)
        # Existing currency mapping treats a dollar symbol as USD; this is a
        # heuristic, not proof of the invoice's ISO currency.
        self.assertEqual(fields["currency"], "USD")

    def test_invoice_56_header_fields_and_split_total(self):
        fields = parse_invoice_fields(INVOICE_56_TEXT)["fields"]

        self.assertEqual(fields["invoiceNumber"], "BW-2026-0810")
        self.assertEqual(fields["vendorName"], "BrightWave Technologies")
        self.assertEqual(fields["invoiceDate"], "2026-08-10")
        self.assertEqual(fields["dueDate"], "2026-08-25")
        self.assertIsNone(fields["subtotal"])
        self.assertIsNone(fields["taxAmount"])
        self.assertEqual(fields["totalAmount"], 1536.9)
        self.assertEqual(fields["currency"], "USD")

    def test_existing_labeled_invoice_fields(self):
        text = """Invoice Number: INV-2026-1001
Vendor Name: Example Ltd.
Invoice Date: 01-Jun-2026
Due Date: 15-Jun-2026
Subtotal: 10000.00
Tax Amount: 1800.00
Total Amount: 11800.00"""

        fields = parse_invoice_fields(text)["fields"]

        self.assertEqual(fields["invoiceNumber"], "INV-2026-1001")
        self.assertEqual(fields["vendorName"], "Example Ltd.")
        self.assertEqual(fields["invoiceDate"], "2026-06-01")
        self.assertEqual(fields["dueDate"], "2026-06-15")
        self.assertEqual(fields["subtotal"], 10000.0)
        self.assertEqual(fields["taxAmount"], 1800.0)
        self.assertEqual(fields["totalAmount"], 11800.0)

    def test_existing_invoice_number_formats(self):
        for value in ("INV-2026-1001", "BW-2026-0810"):
            with self.subTest(value=value):
                fields = parse_invoice_fields(
                    f"Invoice Number: {value}"
                )["fields"]
                self.assertEqual(fields["invoiceNumber"], value)

    def test_numeric_invoice_number_ignores_email_phone_and_postal_code(self):
        text = """Email Invoice Number
test@example.com 4
Phone Number
+1 (555) 123-4567
Postal Code
12345
Invoice Date
08/21/2016"""

        self.assertEqual(
            parse_invoice_fields(text)["fields"]["invoiceNumber"],
            "4"
        )

    def test_phone_or_postal_code_is_not_an_invoice_number(self):
        for text in (
            "Invoice Number\n+1 (555) 123-4567",
            "Invoice Number\n12345",
            "Invoice Number\n08/21/2016",
        ):
            with self.subTest(text=text):
                self.assertIsNone(
                    parse_invoice_fields(text)["fields"]["invoiceNumber"]
                )

    def test_generic_titles_are_not_vendor_names(self):
        for title in ("INVOICE", "FREELANCE INVOICE", "TAX INVOICE", "BILL"):
            with self.subTest(title=title):
                self.assertIsNone(
                    parse_invoice_fields(title)["fields"]["vendorName"]
                )

    def test_same_line_total_formats(self):
        cases = {
            "Total $39.00": 39.0,
            "TOTAL 39.00 USD": 39.0,
            "Grand Total: $1,500.00": 1500.0,
            "Amount Payable: 42.50": 42.5,
        }

        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(
                    parse_invoice_fields(text)["fields"]["totalAmount"],
                    expected
                )

    def test_item_amounts_are_not_used_as_invoice_total(self):
        text = """ITEM DESCRIPTION QUANTITY PRICE TAX AMOUNT
Widget 2 $10.00 9% $21.80
Gadget 1 $5.00 9% $5.45"""

        self.assertIsNone(
            parse_invoice_fields(text)["fields"]["totalAmount"]
        )


if __name__ == "__main__":
    unittest.main()
