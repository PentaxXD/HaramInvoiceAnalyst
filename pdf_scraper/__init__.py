"""
Utilities for extracting structured data from Haram-Christensen invoices.

The module exposes a command-line interface when invoked as
``python -m pdf_scraper``.
"""

from .items import (
    InvoiceItem,
    InvoiceParsingError,
    extract_invoice_items,
    write_items_csv,
)

__all__ = [
    "InvoiceItem",
    "InvoiceParsingError",
    "extract_invoice_items",
    "write_items_csv",
]
