"""
Agent 2: Strategic Sourcing Agent

Decision Automation, Cross-Border Compliance & Geographic Risk Assessment.
Processes multi-item requests with fuzzy product matching, fraud risk, and
KL-centred geographic risk detection.

Robust CSV handling:
  - Absolute pathing via os.path.abspath.
  - Header sanitization: utf-8-sig encoding, strip whitespace/BOM/hidden chars.
  - Ghost-column removal (empty headers from double commas).
  - Dynamic column mapping: tries name, then index fallback.

Matching strategy (in order):
  1. Case-insensitive "contains" match  (query in csv_value).
  2. Token-overlap fuzzy match (Jaccard, threshold >= 0.3).
  3. Malay alias expansion before matching.
  4. Category-keyword fallback if no product match.

Geographic risk:
  - Default user location: Kuala Lumpur, Malaysia.
  - Risk assessed by origin_country relative to KL.
"""

import csv
import json
import os
import re
from statistics import mean

# ── Absolute path to project root ─────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Try the primary CSV first, then fallbacks
_CSV_CANDIDATES = [
    "suppliers.csv",
    "supplier data - Sheet1.csv",
    "supply_chain_data.csv",
    os.path.join("data", "suppliers.csv"),
]

SUPPLIERS_PATH = None
for _candidate in _CSV_CANDIDATES:
    _path = os.path.join(BASE_DIR, _candidate)
    if os.path.isfile(_path):
        SUPPLIERS_PATH = _path
        break

if SUPPLIERS_PATH is None:
    # Last resort — will produce empty supplier list
    SUPPLIERS_PATH = os.path.join(BASE_DIR, "supplier data - Sheet1.csv")

USER_LOCATION = "Kuala Lumpur, Malaysia"

# ── Column name candidates for dynamic mapping ────────────────────────
# Each field has a list of possible header names, in priority order.
# If none match, we fall back to column index.
PRODUCT_COL_NAMES = ["Product Name", "product", "Product", "Product_Name"]
PRICE_COL_NAMES = ["Price (MYR)", "unit_price", "Price", "Unit_Price", "Price_RM"]
LEAD_TIME_COL_NAMES = ["Lead Time", "lead_time_days", "Lead_Time", "LeadTime"]
MOQ_COL_NAMES = ["Minimum Order Quantity (MOQ)", "moq", "MOQ", "Min_Order_Qty"]
EMAIL_COL_NAMES = ["Supplier Email", "email", "Email", "Supplier_Email"]
COUNTRY_COL_NAMES = ["origin_country", "Origin_Country", "Country", "country"]
SUPPLIER_NAME_COL_NAMES = ["Supplier Name", "supplier_name", "Supplier_Name", "Name"]

# Index fallbacks (0-based) when no header matches
INDEX_FALLBACKS = {
    "product": 0,
    "price": 1,
    "lead_time": 3,
    "email": 4,
    "country": -1,  # last column
}


# ── Geographic Risk Definitions (relative to KL) ───────────────────────

TYPHOON_PRONE = {
    "Philippines", "Vietnam", "Japan", "Taiwan", "South Korea",
}

LANDLOCKED = {
    "Nepal", "Mongolia", "Kazakhstan", "Afghanistan", "Laos",
}

HIGH_DISRUPTION_COASTAL = {
    "Bangladesh", "Myanmar",
}

MONSOON_SEASONAL = {
    "India", "Sri Lanka", "Thailand", "Cambodia", "Indonesia",
}

DOMESTIC = {"Malaysia"}


def _assess_geo_risk(country: str) -> tuple[str, str | None]:
    """Assess geographic risk relative to Kuala Lumpur, Malaysia."""
    if not country or country.strip() == "":
        return "LOW", None

    country = country.strip()

    if country in DOMESTIC:
        return "LOW", None

    if country in HIGH_DISRUPTION_COASTAL:
        return (
            "HIGH",
            f"{country}: Cyclone-prone coastal zone — frequent shipping disruption on route to KL",
        )

    if country in TYPHOON_PRONE:
        return (
            "HIGH",
            f"{country}: Typhoon-prone region — seasonal shipping disruption on route to KL",
        )

    if country in LANDLOCKED:
        return (
            "HIGH",
            f"{country}: Landlocked — long-haul overland route required to reach KL port",
        )

    if country in MONSOON_SEASONAL:
        return (
            "MEDIUM",
            f"{country}: Monsoon-affected region — seasonal delays possible on route to KL",
        )

    return "LOW", None


# ── Fuzzy Matching Utilities ───────────────────────────────────────────

MALAY_ALIASES = {
    "baju kurung": "kurung",
    "baju": "kurung",
    "santan": "coconut",
    "tepung": "flour",
    "gula": "sugar",
    "minyak": "oil",
    "ubat": "medicine",
    "wayar": "wire",
    "gelang": "gloves",
    "sarung tangan": "gloves",
    "baut": "bolts",
    "paip": "pump",
    "rod": "rods",
    "pelincir": "lubricant",
}

CATEGORY_KEYWORDS = {
    "Industrial Hardware": [
        "bolt", "nut", "screw", "fastener", "steel", "metal", "wire",
        "copper", "iron", "baut", "wayar",
    ],
    "Industrial Supplies": [
        "lubricant", "oil", "pump", "hydraulic", "pelincir", "paip",
    ],
    "Safety Equipment": [
        "glove", "helmet", "goggle", "protect", "safe", "shield",
        "gelang", "sarung tangan",
    ],
    "Electrical & Lighting": [
        "led", "panel", "light", "lamp", "bulb", "electrical",
    ],
    "Welding & Fabrication": [
        "weld", "rod", "electrode", "arc", "spark",
    ],
    "Fashion & Apparel": [
        "baju", "kurung", "hijab", "dress", "shirt", "blazer",
        "fashion", "apparel", "pakaian", "sarung", "chiffon", "denim",
        "batik", "cotton",
    ],
    "Food & Beverage": [
        "flour", "sugar", "oil", "milk", "rice", "spice", "jam",
        "durian", "butter", "cocoa", "coconut", "palm", "condensed",
        "mango", "bread", "strawberry", "puree", "paste",
        "tepung", "gula", "santan", "minyak",
    ],
    "Medicine & Healthcare": [
        "medicine", "drug", "tablet", "pharma", "vitamin", "healthcare",
        "pharmaniaga", "kotra", "apex", "ccm", "hovid",
        "ubat", "farmasi",
    ],
}

STOP_WORDS = frozenset([
    "i", "a", "an", "the", "need", "want", "buy", "get", "of", "for",
    "and", "or", "in", "on", "with", "to", "from", "by", "at", "under",
    "below", "within", "before", "after", "is", "are", "was", "some",
    "unit", "units", "pc", "pcs", "piece", "pieces", "item", "items",
    "pek", "kotak", "box",
])


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = re.findall(r"[a-z0-9一-鿿]+", text)
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


def _expand_aliases(tokens: list[str]) -> list[str]:
    expanded = list(tokens)
    joined = " ".join(tokens)
    for malay, english in MALAY_ALIASES.items():
        if malay in joined:
            if english not in expanded:
                expanded.append(english)
    return expanded


def _token_overlap_score(query_tokens: list[str], csv_tokens: list[str]) -> float:
    if not query_tokens or not csv_tokens:
        return 0.0
    qset = set(query_tokens)
    cset = set(csv_tokens)
    intersection = qset & cset
    union = qset | cset
    return len(intersection) / len(union) if union else 0.0


def _fuzzy_match_product(product: str, suppliers: list[dict]) -> list[dict]:
    """Match a product query against supplier data using multiple strategies."""
    query_clean = re.sub(r'[^a-z0-9]', '', product.lower().strip())
    if not query_clean:
        return []

    query_tokens = _tokenize(product)
    expanded_tokens = _expand_aliases(query_tokens)

    scored = []

    for s in suppliers:
        product_name = _parse_product(s)
        product_clean = re.sub(r'[^a-z0-9]', '', product_name.lower())
        product_tokens = _tokenize(product_name)

        # Strategy 1: Exact substring match on product name
        if query_clean in product_clean:
            scored.append((s, 1.0))
            continue

        # Strategy 2: Any expanded token matches in product name
        token_match = False
        for t in expanded_tokens:
            if t in product_clean:
                token_match = True
                break
        if token_match:
            scored.append((s, 0.8))
            continue

        # Strategy 3: Jaccard token overlap
        overlap = _token_overlap_score(expanded_tokens, product_tokens)
        if overlap >= 0.3:
            scored.append((s, overlap))
            continue

    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _suggest_category(product: str) -> str | None:
    product_lower = product.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in product_lower:
                return cat
    return None


# ── CSV Loading with Header Sanitization ───────────────────────────────

def _sanitize_headers(fieldnames: list[str] | None) -> list[str]:
    """
    Strip whitespace, BOM characters, zero-width chars, and remove
    empty ghost columns (from double commas in CSV).
    """
    if not fieldnames:
        return []
    cleaned = []
    for name in fieldnames:
        # Remove BOM, zero-width spaces, non-breaking spaces
        s = name.strip().strip("﻿​ ")
        # Remove any remaining invisible chars
        s = re.sub(r"[\x00-\x1f\x7f]", "", s)
        cleaned.append(s)
    return cleaned


def _resolve_column(headers: list[str], candidates: list[str]) -> str | None:
    """Find the first matching header from a list of candidates (case-insensitive)."""
    headers_lower = {h.lower(): h for h in headers if h}
    for candidate in candidates:
        if candidate.lower() in headers_lower:
            return headers_lower[candidate.lower()]
    return None


def _resolve_or_index(headers: list[str], candidates: list[str], index_key: str) -> str | int | None:
    """Resolve column by name; fall back to positional index."""
    name = _resolve_column(headers, candidates)
    if name:
        return name
    idx = INDEX_FALLBACKS.get(index_key)
    if idx is not None and len(headers) > abs(idx):
        return idx
    return None


def _load_suppliers() -> list[dict]:
    """
    Load the supplier CSV with full robustness:
      - utf-8-sig encoding (handles BOM)
      - Header sanitization (strip whitespace, remove ghost columns)
      - Dynamic column mapping
      - Normalize rows into a consistent dict with canonical keys
    """
    path = os.path.normpath(os.path.abspath(SUPPLIERS_PATH))

    if not os.path.isfile(path):
        return []

    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            raw_headers = list(reader.fieldnames or [])
            # Sanitize: strip whitespace/BOM, remove empty ghost columns
            headers = _sanitize_headers(raw_headers)

            # Map each canonical field to the actual header name (or index)
            col_product = _resolve_or_index(headers, PRODUCT_COL_NAMES, "product")
            col_price = _resolve_or_index(headers, PRICE_COL_NAMES, "price")
            col_lead = _resolve_or_index(headers, LEAD_TIME_COL_NAMES, "lead_time")
            col_moq = _resolve_or_index(headers, MOQ_COL_NAMES, "moq") or col_lead
            col_email = _resolve_or_index(headers, EMAIL_COL_NAMES, "email")
            col_country = _resolve_or_index(headers, COUNTRY_COL_NAMES, "country")
            col_name = _resolve_or_index(headers, SUPPLIER_NAME_COL_NAMES, "email")

            rows = list(reader)
            normalized = []

            for row in rows:
                # Re-sanitize keys in row dict (ghost columns may have empty keys)
                clean_row = {}
                for k, v in row.items():
                    k_clean = k.strip().strip("﻿​ ") if k else ""
                    if k_clean:
                        clean_row[k_clean] = v if v else ""

                # Extract by resolved column name or index
                header_list = headers  # for index access

                product_val = _get_val(clean_row, header_list, col_product, "")
                price_val = _get_val(clean_row, header_list, col_price, "0")
                lead_val = _get_val(clean_row, header_list, col_lead, "0")
                moq_val = _get_val(clean_row, header_list, col_moq, "1")
                email_val = _get_val(clean_row, header_list, col_email, "")
                country_val = _get_val(clean_row, header_list, col_country, "")
                name_val = _get_val(clean_row, header_list, col_name, "")

                # Country fallback: if not found, try the last column
                if not country_val.strip():
                    if header_list:
                        last_key = header_list[-1]
                        if last_key in clean_row:
                            country_val = clean_row[last_key]

                # Supplier name fallback: derive from email if missing
                if not name_val.strip() and email_val.strip():
                    local = email_val.split("@")[0]
                    name_val = re.sub(r"[._\-]", " ", local).strip().title()

                normalized.append({
                    "_product": product_val.strip(),
                    "_price": price_val.strip(),
                    "_lead_time": lead_val.strip(),
                    "_moq": moq_val.strip(),
                    "_email": email_val.strip(),
                    "_country": country_val.strip(),
                    "_name": name_val.strip(),
                })

            return normalized

    except Exception as e:
        return []


def _get_val(row: dict, headers: list[str], col: str | int | None, default: str) -> str:
    """Get value from a row by column name or index."""
    if col is None:
        return default
    if isinstance(col, int):
        if col < 0:
            col = len(headers) + col
        # Try to find the key at that index
        if 0 <= col < len(headers):
            key = headers[col]
            return row.get(key, default)
        return default
    # String key
    return row.get(col, default)


# ── CSV Value Parsers (all operate on normalized _keys) ───────────────

def _parse_product(row: dict) -> str:
    return row.get("_product", "").strip()


def _parse_price(row: dict) -> float:
    raw = row.get("_price", "0").strip()
    clean = re.sub(r"[^\d.]", "", raw)
    return float(clean) if clean else 0.0


def _parse_lead_time(row: dict) -> int:
    raw = row.get("_lead_time", "0").strip()
    match = re.search(r"(\d+)", raw)
    return int(match.group(1)) if match else 0


def _parse_moq(row: dict) -> int:
    raw = row.get("_moq", "1").strip()
    match = re.search(r"(\d+)", raw)
    return int(match.group(1)) if match else 1


def _parse_email(row: dict) -> str:
    return row.get("_email", "").strip()


def _parse_country(row: dict) -> str:
    return row.get("_country", "").strip()


def _extract_supplier_name(row: dict) -> str:
    """Extract supplier name — uses _name field, falls back to email-derived name."""
    name = row.get("_name", "").strip()
    if name:
        return name
    email = _parse_email(row)
    local = email.split("@")[0] if "@" in email else email
    name = re.sub(r"[._\-]", " ", local).strip()
    return name.title() if name else "Unknown Supplier"


# ── Main Sourcing Function ─────────────────────────────────────────────

def source_all_items(requirements_json: str) -> str:
    """
    Accept the full Agent 1 output JSON (with intent_type, original_language,
    items array). Process each item and return a results array.
    """
    try:
        req = json.loads(requirements_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "invalid JSON from extractor"}, separators=(",", ":"))

    if "error" in req:
        return json.dumps({"error": f"upstream error: {req['error']}"}, separators=(",", ":"))

    items = req.get("items", [])
    language = req.get("original_language", "en")
    intent_type = req.get("intent_type", "NEW_ORDER")

    if not items:
        return json.dumps({"error": "no items in request"}, separators=(",", ":"))

    suppliers = _load_suppliers()
    if not suppliers:
        return json.dumps({"error": "no supplier data available"}, separators=(",", ":"))

    results = []
    for item in items:
        result = _source_single_item(item, suppliers)
        results.append(result)

    return json.dumps(
        {
            "intent_type": intent_type,
            "original_language": language,
            "user_location": USER_LOCATION,
            "results": results,
        },
        separators=(",", ":"),
    )


def _source_single_item(item: dict, suppliers: list[dict]) -> dict:
    product = item.get("product", "").strip()
    max_price = item.get("max_price")
    max_lead_time = item.get("lead_time_days")
    quantity = item.get("quantity")
    halal_required = item.get("halal_required")

    scored = _fuzzy_match_product(product, suppliers)

    # Fallback: if no match found, try category keyword fallback
    if not scored:
        category = _suggest_category(product)
        if category and category in CATEGORY_KEYWORDS:
            keywords = CATEGORY_KEYWORDS[category]
            for s in suppliers:
                prod_lower = _parse_product(s).lower()
                if any(kw in prod_lower for kw in keywords):
                    scored.append((s, 0.3))

    if not scored:
        return {
            "product_name": product,
            "status": "no_match",
            "winner": None,
            "alternatives": [],
            "avg_price": 0,
            "risk_alerts": [],
            "category_suggestion": _suggest_category(product),
            "fuzzy_match_info": None,
        }

    candidates = [s for s, _ in scored]
    best_score = scored[0][1]
    fuzzy_info = None
    if best_score < 1.0:
        fuzzy_info = f"Fuzzy match: '{product}' -> '{_parse_product(candidates[0])}' (score {best_score:.2f})"

    # Compute average price for fraud detection
    all_prices = [_parse_price(s) for s in candidates]
    avg_price = round(mean(all_prices), 2)

    # ── Step 2: filter by constraints ────────────────────────────────
    valid = [
        s for s in candidates
        if (max_price is None or _parse_price(s) <= float(max_price))
        and (max_lead_time is None or _parse_lead_time(s) <= int(max_lead_time))
        and (quantity is None or int(quantity) >= _parse_moq(s))
    ]

    # ── Step 3: fraud threshold (< 50% of average) ──────────────────
    fraud_threshold = avg_price * 0.5

    risk_alerts = []

    def _build_supplier(s, is_valid, is_winner=False):
        price = _parse_price(s)
        warning = None
        if price < fraud_threshold:
            warning = "Abnormally low price - Potential Fraud/Quality Risk"

        country = _parse_country(s)
        geo_risk, geo_reason = _assess_geo_risk(country)

        if geo_risk in ("HIGH", "MEDIUM") and geo_reason:
            risk_alerts.append({
                "supplier": _extract_supplier_name(s),
                "risk_level": geo_risk,
                "risk_reason": geo_reason,
            })

        return {
            "name": _extract_supplier_name(s),
            "price_rm": price,
            "lead_time_days": _parse_lead_time(s),
            "moq": _parse_moq(s),
            "email": _parse_email(s),
            "product_name": _parse_product(s),
            "origin_country": country,
            "risk_level": geo_risk,
            "risk_reason": geo_reason,
            "meets_constraints": is_valid,
            "is_winner": is_winner,
            "warning": warning,
        }

    alternatives = [_build_supplier(s, s in valid) for s in candidates]

    if not valid:
        return {
            "product_name": product,
            "status": "no_match",
            "winner": None,
            "alternatives": alternatives,
            "avg_price": avg_price,
            "risk_alerts": risk_alerts,
            "category_suggestion": None,
            "fuzzy_match_info": fuzzy_info,
        }

    # Exclude fraud-risk suppliers from winning
    safe_valid = [s for s in valid if _parse_price(s) >= fraud_threshold]
    pool = safe_valid if safe_valid else valid

    # Select lowest price winner
    winner = min(pool, key=lambda s: _parse_price(s))
    winner_price = _parse_price(winner)
    has_warning = winner_price < fraud_threshold

    winner_record = _build_supplier(winner, True, True)
    qty = int(quantity) if quantity is not None else _parse_moq(winner)
    winner_record["quantity"] = qty
    winner_record["total_price"] = round(winner_price * qty, 2)
    winner_record["halal_required"] = halal_required
    winner_record["product_name"] = _parse_product(winner)

    return {
        "product_name": _parse_product(winner),
        "status": "warning" if has_warning else "success",
        "winner": winner_record,
        "alternatives": alternatives,
        "avg_price": avg_price,
        "risk_alerts": risk_alerts,
        "category_suggestion": None,
        "fuzzy_match_info": fuzzy_info,
    }