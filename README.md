## Haram Invoice Analyst

This branch now includes a lightweight PDF parser that turns Haram‑Christensen invoice PDFs into the item CSV produced earlier in this session.

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Usage

```bash
python -m pdf_scraper items \
  Inv_260282_from_HaramChristensen_Corp._67816.pdf \
  --all-pages \
  --out invoice_items.csv
```

The command reads every page of the invoice, extracts line items, derives pack size and pricing metadata, and writes the normalized CSV:

- `Pack Size` is lifted from the product description and normalized (e.g. multi-line notes are collapsed, hanging barcodes are preserved).
- `Price per Product`, `Store Price`, and `Online Price` follow the formulas agreed earlier:
  - `Price per Product` divides the case price by pack quantity when available.
  - `Store Price = ceil_to_.09(1.55 * price_per_product + 0.30)`.
  - `Online Price = Store Price + 0.50`.

If a line item omits the quantity column in the PDF (common on out-of-table notes), the scraper back-calculates quantity from `Amount / Price Each` and leaves the descriptive text intact.

### Result

Running the command above against `Inv_260282_from_HaramChristensen_Corp._67816.pdf` generates `invoice_items.csv`, matching the curated output you reviewed:

```
Quantity,Item Code,Description,Pack Size,Price Each,Amount,Price per Product,Store Price,Online Price
10,04SW09B,SWEDE MATJES FILL RED PAIL,2.2KG PC,14.00,140.00,14,22.09,22.59
...
```

Feel free to adjust pack-size heuristics or pricing formulas inside `pdf_scraper/items.py` if future invoices diverge.
