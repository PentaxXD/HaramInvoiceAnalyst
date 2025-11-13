from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, List, Sequence

from PyPDF2 import PdfReader

ITEM_CODE_PATTERN = re.compile(r"^(\d{2}[A-Z]{2}[A-Z0-9]*)\b")

UNIT_TOKENS = {
    "CS",
    "CT",
    "DZ",
    "EA",
    "LB",
    "LBS",
    "LB.",
    "LB,",
    "KG",
    "PC",
    "PK",
    "BTL",
    "GAL",
    "MM",
    "GR",
    "G",
    "L",
    "OZ",
    "OZ.",
    "OZ,",
}


@dataclass
class RawItem:
    item_code: str
    lines: List[str]


@dataclass
class InvoiceItem:
    quantity: Decimal
    item_code: str
    description: str
    pack_size: str
    price_each: Decimal
    amount: Decimal
    price_per_product: Decimal
    store_price: Decimal
    online_price: Decimal


class InvoiceParsingError(RuntimeError):
    """Raised when the invoice cannot be parsed into structured rows."""


def extract_invoice_items(pdf_path: Path, *, all_pages: bool = False) -> List[InvoiceItem]:
    reader = PdfReader(str(pdf_path))
    pages = reader.pages
    if not pages:
        return []

    if all_pages:
        page_indices: Iterable[int] = range(len(pages))
    else:
        page_indices = range(1)

    raw_items: List[RawItem] = []
    for page_index in page_indices:
        page = pages[page_index]
        text = page.extract_text() or ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        data_lines = _strip_page_header(lines)
        raw_items.extend(_collect_raw_items(data_lines))

    items: List[InvoiceItem] = []
    for raw in raw_items:
        try:
            item = _parse_raw_item(raw)
        except InvoiceParsingError as exc:
            raise InvoiceParsingError(f"Failed to parse item {raw.item_code}: {exc}") from exc
        if item is not None:
            items.append(item)

    return items


def write_items_csv(items: Sequence[InvoiceItem], out_path: Path) -> None:
    fieldnames = [
        "Quantity",
        "Item Code",
        "Description",
        "Pack Size",
        "Price Each",
        "Amount",
        "Price per Product",
        "Store Price",
        "Online Price",
    ]
    with out_path.open("w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "Quantity": _format_quantity(item.quantity),
                    "Item Code": item.item_code,
                    "Description": item.description,
                    "Pack Size": item.pack_size,
                    "Price Each": _format_money(item.price_each),
                    "Amount": _format_money(item.amount),
                    "Price per Product": _format_price_per_product(item.price_per_product),
                    "Store Price": _format_money(item.store_price),
                    "Online Price": _format_money(item.online_price),
                }
            )


def _strip_page_header(lines: List[str]) -> List[str]:
    data_lines: List[str] = []
    in_table = False
    for line in lines:
        if not in_table:
            if "Item Code" in line and "Description" in line:
                in_table = True
            continue
        if line.startswith("Page"):
            break
        data_lines.append(line)
    return data_lines


def _collect_raw_items(lines: List[str]) -> List[RawItem]:
    items: List[RawItem] = []
    current: RawItem | None = None

    for line in lines:
        match = ITEM_CODE_PATTERN.match(line)
        if match:
            if current:
                items.append(current)
            current = RawItem(item_code=match.group(1), lines=[line])
        else:
            if current:
                current.lines.append(line)

    if current:
        items.append(current)

    return items


def _parse_raw_item(raw: RawItem) -> InvoiceItem | None:
    first_line = raw.lines[0]
    after_code = _normalize_spacing(first_line[len(raw.item_code) :].strip())
    extra_lines = [_normalize_spacing(line.strip()) for line in raw.lines[1:]]

    combined_text = " ".join([after_code, *extra_lines]).strip()
    if not combined_text:
        raise InvoiceParsingError("empty content")

    price_amount_match = re.search(r"(\d[\d,]*\.\d{2})\s*(\d[\d,]*\.\d{2})$", combined_text)
    if not price_amount_match:
        return None

    price_str, amount_str = price_amount_match.groups()
    amount = Decimal(amount_str.replace(",", ""))
    price_each = Decimal(price_str.replace(",", ""))

    before_price = combined_text[: price_amount_match.start()].rstrip()
    quantity_match = re.search(r"(\d+(?:\.\d+)?)\s*$", before_price)
    quantity_str = quantity_match.group(1) if quantity_match else None
    parsed_quantity = Decimal(quantity_str.replace(",", "")) if quantity_str else None
    desc_raw = before_price

    if price_each == 0 and parsed_quantity is None:
        quantity = Decimal("0")
    else:
        computed_quantity = (
            (amount / price_each).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if price_each != 0
            else Decimal("0")
        )
        if parsed_quantity is None:
            quantity = computed_quantity
        else:
            if abs(parsed_quantity - computed_quantity) > Decimal("0.01"):
                quantity = computed_quantity
            else:
                quantity = parsed_quantity

    desc_part = desc_raw
    quantity_text = _format_quantity(quantity) if quantity is not None else ""
    tokens = desc_part.split()
    if quantity_text and tokens:
        last_token = tokens[-1]
        prev_token = tokens[-2] if len(tokens) >= 2 else ""
        if last_token.endswith(quantity_text) and prev_token.lower() != "x":
            prefix = last_token[: len(last_token) - len(quantity_text)]
            if prefix:
                tokens[-1] = prefix
            else:
                tokens.pop()

    desc_tokens = tokens

    first_line_text = after_code
    first_line_price_match = re.search(r"(\d[\d,]*\.\d{2})\s*(\d[\d,]*\.\d{2})$", first_line_text)
    if first_line_price_match:
        first_line_text = first_line_text[: first_line_price_match.start()].rstrip()
    first_line_qty_match = re.search(r"(\d+(?:\.\d+)?)\s*$", first_line_text)
    if first_line_qty_match:
        first_line_text = first_line_text[: first_line_qty_match.start()].rstrip()

    first_desc_tokens, pack_tokens_first = _split_pack_from_first_line(first_line_text)
    pack_size = " ".join(pack_tokens_first) if pack_tokens_first else ""

    if pack_tokens_first:
        desc_tokens = _remove_first_subsequence(desc_tokens, pack_tokens_first)

    description = " ".join(desc_tokens).strip()
    description = _collapse_spacing(description)
    if not description:
        raise InvoiceParsingError("missing description text")

    if not pack_size:
        pack_size = _infer_pack_size(desc_tokens)

    pack_size = _tidy_pack_size(pack_size)

    price_per_product = _compute_price_per_product(pack_size, price_each)
    store_price = _compute_store_price(price_per_product)
    online_price = store_price + Decimal("0.50")

    return InvoiceItem(
        quantity=quantity,
        item_code=raw.item_code,
        description=description,
        pack_size=pack_size or "",
        price_each=price_each,
        amount=amount,
        price_per_product=price_per_product,
        store_price=store_price,
        online_price=online_price,
    )


def _is_decimal_token(token: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(?:\.\d+)?", token.replace(",", "")))


def _extract_pack_tokens(tokens: List[str]) -> List[str]:
    pack_tokens: List[str] = []
    digits_found = False

    for token in reversed(tokens):
        cleaned = token.strip(",.;")
        has_digit = any(ch.isdigit() for ch in cleaned)
        contains_slash = "/" in token and any(ch.isdigit() for ch in token)
        contains_dash = "-" in token and token != "-"
        is_unit = cleaned.upper() in UNIT_TOKENS
        include = False

        if has_digit or contains_slash:
            include = True
            digits_found = True
        elif digits_found and (is_unit or cleaned.upper() in UNIT_TOKENS):
            include = True
        elif digits_found and token in {"-", "&"}:
            include = True
        elif digits_found and cleaned.isalpha() and cleaned.upper() == cleaned:
            include = True
        elif not digits_found and is_unit:
            include = True
        elif not digits_found and contains_dash and pack_tokens:
            include = True

        if include:
            pack_tokens.append(token)
        elif digits_found:
            break

    return list(reversed(pack_tokens))


def _remove_first_subsequence(tokens: List[str], subsequence: List[str]) -> List[str]:
    if not subsequence or len(subsequence) > len(tokens):
        return tokens[:]

    for idx in range(len(tokens) - len(subsequence) + 1):
        if tokens[idx : idx + len(subsequence)] == subsequence:
            return tokens[:idx] + tokens[idx + len(subsequence) :]

    return tokens[:]


def _split_pack_from_first_line(text: str) -> tuple[List[str], List[str]]:
    if not text:
        return [], []
    matches = list(re.finditer(r"\b\S*\d\S*\b", text))
    if not matches:
        return text.split(), []
    last = matches[-1]
    before = text[: last.start()].strip()
    pack_part = text[last.start() :].strip()
    return before.split(), pack_part.split()


def _infer_pack_size(tokens: List[str]) -> str:
    extracted = _extract_pack_tokens(tokens)
    return " ".join(extracted)


def _tidy_pack_size(pack_size: str) -> str:
    if not pack_size:
        return ""
    tokens = pack_size.split()
    merged: List[str] = []
    attach_units = {"KG", "G", "GR", "MM", "OZ", "LBS"}
    for token in tokens:
        upper = token.upper()
        if merged and _contains_digits(merged[-1]) and upper in attach_units:
            merged[-1] = f"{merged[-1]}{upper}"
        else:
            merged.append(token)
    return " ".join(merged)


def _contains_digits(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


def _compute_price_per_product(pack_size: str, price_each: Decimal) -> Decimal:
    pack_qty = _extract_pack_quantity(pack_size)
    if pack_qty is None or pack_qty == 0:
        return price_each
    result = (price_each / pack_qty).quantize(Decimal("0.000000001"), rounding=ROUND_HALF_UP)
    return result


def _extract_pack_quantity(pack_size: str) -> Decimal | None:
    if "/" not in pack_size:
        return None
    left = pack_size.split("/", 1)[0].strip()
    if not left:
        return None
    numbers = re.findall(r"\d+(?:\.\d+)?", left.upper().replace("X", " "))
    if not numbers:
        return None

    pack_qty = Decimal("1")
    for number in numbers:
        pack_qty *= Decimal(number)
    return pack_qty


def _compute_store_price(price_per_product: Decimal) -> Decimal:
    base = Decimal("1.55") * price_per_product + Decimal("0.30")
    cents = (base * 100).quantize(Decimal("1"), rounding=ROUND_CEILING)
    if Decimal(cents) / 100 < base:
        cents += 1
    remainder = cents % 10
    if remainder != 9:
        cents += (9 - remainder) % 10
    return Decimal(cents) / Decimal(100)


def _format_money(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{quantized:.2f}"


def _format_quantity(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _format_price_per_product(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _collapse_spacing(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_spacing(text: str) -> str:
    def repl_letter_digit(match: re.Match[str]) -> str:
        char = match.group(1)
        if char.upper() == "X":
            return char
        return f"{char} "

    def repl_digit_letter(match: re.Match[str]) -> str:
        digit, letter = match.group(1), match.group(2)
        if letter.upper() == "X":
            return f"{digit}{letter}"
        return f"{digit} {letter}"

    text = re.sub(r"(?<=[A-Za-z])([A-Za-z\.])(?=\d)", repl_letter_digit, text)
    text = re.sub(r"(\d)([A-Za-z])", repl_digit_letter, text)
    return text
