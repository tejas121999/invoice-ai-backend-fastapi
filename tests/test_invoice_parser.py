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

PAGE_LOADED_DIGITAL_INVOICE_TEXT = """[Page 1]
INVOICE NUMBER

INV-2026-1001INVOICE
Acme Office Supplies Ltd.

INVOICE DATE            DUE DATE              CURRENCY
15 November 2026        30 November 2026      INR

BILL TO
ABC Technologies Pvt Ltd.

Description             Amount (INR)
Office Supplies         5,000.00
Printing Materials      2,000.00

Subtotal                7,000.00
Tax Amount              1,260.00
Total Amount            8,260.00"""

TWO_PAGE_INVOICE_TEXT = """[Page 1]
TWO-PAGE TEST INVOICE
NovaTech Solutions Pvt. Ltd.
Invoice Number: NT-2026-2045
Invoice Date: 18 November 2026
Due Date: 03 December 2026
Bill To: Global Retail Technologies Pvt. Ltd.
Currency: INR
Enterprise Software Development 45,000.00
Cloud Infrastructure Setup 15,000.00
Technical Support Services 10,000.00

[Page 2]
Subtotal 70,000.00
Tax Amount (18%) 12,600.00
Total Amount 82,600.00"""


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

    def test_adjacent_invoice_label_is_not_part_of_invoice_number(self):
        fields = parse_invoice_fields(
            "Invoice Number\nINV-2026-1001INVOICE"
        )["fields"]

        self.assertEqual(fields["invoiceNumber"], "INV-2026-1001")

    def test_digital_pdf_text_with_column_dates_and_vendor_after_number(self):
        fields = parse_invoice_fields(
            PAGE_LOADED_DIGITAL_INVOICE_TEXT
        )["fields"]

        self.assertEqual(fields["invoiceNumber"], "INV-2026-1001")
        self.assertEqual(fields["vendorName"], "Acme Office Supplies Ltd.")
        self.assertEqual(fields["invoiceDate"], "2026-11-15")
        self.assertEqual(fields["dueDate"], "2026-11-30")
        self.assertEqual(fields["subtotal"], 7000.0)
        self.assertEqual(fields["taxAmount"], 1260.0)
        self.assertEqual(fields["totalAmount"], 8260.0)
        self.assertEqual(fields["currency"], "INR")

    def test_two_page_invoice_extracts_header_and_page_two_tax(self):
        result = parse_invoice_fields(TWO_PAGE_INVOICE_TEXT)
        fields = result["fields"]

        self.assertEqual(fields["invoiceNumber"], "NT-2026-2045")
        self.assertEqual(fields["vendorName"], "NovaTech Solutions Pvt. Ltd.")
        self.assertEqual(fields["invoiceDate"], "2026-11-18")
        self.assertEqual(fields["dueDate"], "2026-12-03")
        self.assertEqual(fields["subtotal"], 70000.0)
        self.assertEqual(fields["taxAmount"], 12600.0)
        self.assertEqual(fields["totalAmount"], 82600.0)
        self.assertEqual(fields["currency"], "INR")
        self.assertFalse(result["errors"])
        self.assertGreater(result["confidence"]["taxAmount"], 0.9)
        self.assertGreater(result["confidence"]["vendorName"], 0.7)

    def test_customer_section_does_not_supply_vendor_name(self):
        text = """[Page 1]
TWO-PAGE TEST INVOICE
Invoice Number: NT-2026-2045
Customer Name: Global Retail Technologies Pvt. Ltd.
[Page 2]
Total Amount: 82,600.00"""

        self.assertIsNone(
            parse_invoice_fields(text)["fields"]["vendorName"]
        )

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
        for title in (
            "INVOICE",
            "FREELANCE INVOICE",
            "TAX INVOICE",
            "TWO-PAGE TEST INVOICE",
            "BILL"
        ):
            with self.subTest(title=title):
                self.assertIsNone(
                    parse_invoice_fields(title)["fields"]["vendorName"]
                )

    def test_tax_labels_with_percentages_are_extracted(self):
        cases = (
            "Tax Amount (18%) 12,600.00",
            "Tax Amount (18%)\n12,600.00",
            "Tax (18%): INR 12,600.00",
            "Total Tax: 12,600.00",
            "GST (18%) 12,600.00",
            "VAT Amount: 12,600.00"
        )

        for line in cases:
            with self.subTest(line=line):
                result = parse_invoice_fields(line)
                self.assertEqual(result["fields"]["taxAmount"], 12600.0)
                self.assertGreater(result["confidence"]["taxAmount"], 0.0)

    def test_all_dynamic_fields_are_extracted_with_matching_confidence(self):
        text = """Invoice Number: NT-2026-2045
Vendor GSTIN: 27ABCDE1234F1Z5
Purchase Order Number: PO-2026-102
Payment Terms: Net 30 days
Shipping Charges: INR 1,250.00
Discount (10%): INR 500.00
Vendor Address:
12 Market Street
Suite 400
Springfield
Payment Reference: PAY-REF-2026-88"""

        result = parse_invoice_fields(text)

        self.assertEqual(
            {
                name: result["fields"][name]
                for name in (
                    "poNumber",
                    "vendorGst",
                    "paymentTerms",
                    "shippingCharges",
                    "discount",
                    "vendorAddress",
                    "paymentReference"
                )
            },
            {
                "poNumber": "PO-2026-102",
                "vendorGst": "27ABCDE1234F1Z5",
                "paymentTerms": "Net 30 days",
                "shippingCharges": 1250.0,
                "discount": 500.0,
                "vendorAddress": (
                    "12 Market Street Suite 400 Springfield"
                ),
                "paymentReference": "PAY-REF-2026-88"
            }
        )
        for field_name in (
            "poNumber",
            "vendorGst",
            "paymentTerms",
            "shippingCharges",
            "discount",
            "vendorAddress",
            "paymentReference"
        ):
            with self.subTest(field=field_name):
                self.assertGreater(result["confidence"][field_name], 0.0)

    def test_dynamic_field_label_variations(self):
        cases = (
            ("PO No.: PO-88", "poNumber", "PO-88"),
            ("P.O. Number: PO-89", "poNumber", "PO-89"),
            ("Terms of Payment: Due on receipt",
             "paymentTerms", "Due on receipt"),
            ("Delivery Charges: 45.50", "shippingCharges", 45.5),
            ("Freight Charges: USD 60.00", "shippingCharges", 60.0),
            ("Less Discount: 15.00", "discount", 15.0),
            ("Supplier Address: 8 River Road",
             "vendorAddress", "8 River Road"),
            ("Transaction ID: TX-789", "paymentReference", "TX-789"),
            ("UTR No.: UTR-2026-42",
             "paymentReference", "UTR-2026-42")
        )

        for line, field_name, expected in cases:
            with self.subTest(line=line):
                result = parse_invoice_fields(line)
                self.assertEqual(result["fields"][field_name], expected)
                self.assertGreater(result["confidence"][field_name], 0.0)

    def test_gst_label_variations_are_extracted(self):
        gst_number = "27ABCDE1234F1Z5"

        for label in ("GSTIN", "GST Number", "GST No.", "Vendor GST"):
            with self.subTest(label=label):
                result = parse_invoice_fields(f"{label}: {gst_number}")
                self.assertEqual(result["fields"]["vendorGst"], gst_number)
                self.assertGreater(result["confidence"]["vendorGst"], 0.0)

    def test_dynamic_amounts_support_next_line_values_and_reject_rates(self):
        result = parse_invoice_fields(
            "Shipping Charges\nINR 1,200.00\n"
            "Discount: 10%"
        )

        self.assertEqual(result["fields"]["shippingCharges"], 1200.0)
        self.assertIsNone(result["fields"]["discount"])
        self.assertNotIn("discount", result["confidence"])

    def test_missing_dynamic_fields_have_no_confidence_entries(self):
        result = parse_invoice_fields(
            "Invoice Number: INV-2026-1001\n"
            "Total Amount: 100.00"
        )
        dynamic_fields = (
            "poNumber",
            "vendorGst",
            "paymentTerms",
            "shippingCharges",
            "discount",
            "vendorAddress",
            "paymentReference"
        )

        for field_name in dynamic_fields:
            with self.subTest(field=field_name):
                self.assertIsNone(result["fields"][field_name])
                self.assertNotIn(field_name, result["confidence"])

    def test_tax_components_are_summed_when_no_tax_total_is_labeled(self):
        text = """[Page 1]
Subtotal: 70,000.00
[Page 2]
CGST @9% 6,300.00
SGST @9% 6,300.00
Total Amount: 82,600.00"""

        fields = parse_invoice_fields(text)["fields"]

        self.assertEqual(fields["taxAmount"], 12600.0)
        self.assertEqual(fields["totalAmount"], 82600.0)

    def test_missing_tax_is_not_calculated_from_subtotal_and_total(self):
        result = parse_invoice_fields(
            "Subtotal: 70,000.00\nTotal Amount: 82,600.00"
        )

        self.assertIsNone(result["fields"]["taxAmount"])
        self.assertEqual(result["confidence"]["taxAmount"], 0.0)

    def test_subtotal_and_total_are_not_mistaken_for_tax(self):
        fields = parse_invoice_fields(
            "Subtotal: 70,000.00\nTotal Amount: 82,600.00"
        )["fields"]

        self.assertIsNone(fields["taxAmount"])

    def test_tax_rate_without_tax_amount_is_not_used_as_tax(self):
        fields = parse_invoice_fields(
            "Tax Rate (18%)\nSubtotal: 70,000.00\n"
            "Total Amount: 82,600.00"
        )["fields"]

        self.assertIsNone(fields["taxAmount"])

    def test_financial_mismatch_reduces_confidence(self):
        result = parse_invoice_fields(
            "Subtotal: 100.00\n"
            "Tax Amount: 20.00\n"
            "Total Amount: 125.00"
        )

        self.assertTrue(result["errors"])
        self.assertTrue(any(
            "does not match" in error["message"]
            for error in result["errors"]
        ))
        self.assertLessEqual(result["confidence"]["subtotal"], 0.60)
        self.assertLessEqual(result["confidence"]["taxAmount"], 0.60)
        self.assertLessEqual(result["confidence"]["totalAmount"], 0.60)

    def test_page_markers_are_not_extracted_as_vendor_names(self):
        markers = (
            "[Page 1]",
            "[Page 2]",
            "[Page 3: processing failed]",
            "[Page 4: no text detected]",
            "[no text detected]",
        )

        for marker in markers:
            with self.subTest(marker=marker):
                fields = parse_invoice_fields(
                    f"{marker}\nINVOICE\n"
                    "Invoice Number: INV-2026-1001"
                )["fields"]

                self.assertIsNone(fields["vendorName"])

    def test_invoice_fields_are_not_used_as_fallback_vendor_name(self):
        text = """[Page 1]
INVOICE
Invoice Number: INV-2026-1001
Total Amount: 100.00"""

        self.assertIsNone(
            parse_invoice_fields(text)["fields"]["vendorName"]
        )

    def test_page_markers_do_not_hide_an_actual_vendor_name(self):
        text = """[Page 1]
[no text detected]
[Page 2]
Vendor Name: Example Supplies Ltd.
Invoice Number: INV-2026-1001
Total Amount: 100.00
[Page 3: processing failed]"""

        fields = parse_invoice_fields(text)["fields"]

        self.assertEqual(fields["vendorName"], "Example Supplies Ltd.")
        self.assertEqual(fields["invoiceNumber"], "INV-2026-1001")

    def test_page_markers_between_pages_do_not_affect_vendor_extraction(self):
        text = """[Page 1]
INVOICE
Invoice Number: INV-2026-1001
[Page 2]
BrightWave Technologies
Invoice Date: 10-Aug-2026
[Page 3: processing failed]
Total Amount: 100.00"""

        fields = parse_invoice_fields(text)["fields"]

        self.assertEqual(fields["vendorName"], "BrightWave Technologies")
        self.assertEqual(fields["invoiceNumber"], "INV-2026-1001")
        self.assertEqual(fields["invoiceDate"], "2026-08-10")
        self.assertEqual(fields["totalAmount"], 100.0)

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
