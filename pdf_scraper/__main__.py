from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .items import InvoiceParsingError, extract_invoice_items, write_items_csv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdf_scraper", description="Extract line items from invoices.")
    subparsers = parser.add_subparsers(dest="command")

    items_parser = subparsers.add_parser("items", help="Extract invoice line items into a CSV file.")
    items_parser.add_argument("pdf_path", type=Path, help="Path to the invoice PDF.")
    items_parser.add_argument("--out", type=Path, required=True, help="Where to write the CSV output.")
    items_parser.add_argument(
        "--all-pages",
        action="store_true",
        help="Process every page of the PDF (default: only the first page).",
    )

    args = parser.parse_args(argv)
    if args.command != "items":
        parser.print_help()
        return 1

    try:
        items = extract_invoice_items(args.pdf_path, all_pages=args.all_pages)
    except FileNotFoundError:
        print(f"PDF not found: {args.pdf_path}", file=sys.stderr)
        return 2
    except InvoiceParsingError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    write_items_csv(items, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
