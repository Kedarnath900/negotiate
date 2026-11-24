"""Generate a Kaggle submission for the Acme supplier-negotiation task.

Expected project layout:
    project_folder/
        generate_submission.py
        data/
            threads.csv
            sample_submission.csv
            playbook.zip

Run from the project folder:
    python generate_submission.py

This is a rules-based baseline built from the supplied playbook. It is not a
trained model and its predictions should be validated against the competition
instructions before submission.
"""

from __future__ import annotations

import math
import re
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
THREADS_FILE = DATA_DIR / "threads.csv"
TEMPLATE_FILE = DATA_DIR / "sample_submission.csv"
PLAYBOOK_FILE = DATA_DIR / "playbook.zip"
OUTPUT_FILE = DATA_DIR / "submission.csv"

DEFAULT_RATES = {"USD": 84.5, "EUR": 91.0, "GBP": 106.0}


def clean_number(value: str | None) -> float | None:
    """Parse values such as '14,000', '18.5k', or '1.2 lakh'."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(k|lakh|lakhs)?", text, flags=re.I)
    if not match:
        return None
    number = float(match.group(1))
    suffix = (match.group(2) or "").lower()
    if suffix == "k":
        number *= 1_000
    elif suffix.startswith("lakh"):
        number *= 100_000
    return number


def markdown_value(text: str, label_pattern: str, default: float | None = None) -> float | None:
    """Read a labelled value from playbook Markdown, including **bold** labels."""
    match = re.search(
        rf"\*{{0,2}}{label_pattern}\*{{0,2}}\s*:\*{{0,2}}\s*(?:₹\s*)?([\d,]+(?:\.\d+)?)",
        text,
        flags=re.I,
    )
    if not match:
        return default
    return clean_number(match.group(1))


def slugify(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def read_playbook():
    if not PLAYBOOK_FILE.exists():
        raise FileNotFoundError(f"Playbook not found: {PLAYBOOK_FILE}")

    with zipfile.ZipFile(PLAYBOOK_FILE) as archive:
        docs = {
            name: archive.read(name).decode("utf-8", errors="replace")
            for name in archive.namelist()
            if name.endswith(".md")
        }

    categories: dict[str, dict[str, Any]] = {}
    suppliers: dict[str, dict[str, Any]] = {}
    amendments: list[tuple[str, str, str, float]] = []

    for path, text in docs.items():
        if "/categories/" in path:
            slug = Path(path).stem
            category = {
                "target": markdown_value(text, r"Target price"),
                "walk": markdown_value(text, r"Walk-away price"),
                "rounds": markdown_value(text, r"Negotiation rounds\s*\(R\)", 3),
                "beta": markdown_value(text, r"Concession exponent\s*\(β\)", 1),
                "approval": markdown_value(text, r"Approval limit"),
                "gst": markdown_value(text, r"GST rate", 18),
                "text": text,
            }
            category["rounds"] = int(category["rounds"] or 3)
            category["gst"] = float(category["gst"] or 18) / 100.0
            category["beta"] = float(category["beta"] if category["beta"] is not None else 1)
            categories[slug] = category

        elif "/suppliers/" in path:
            slug = Path(path).stem
            upper = text.upper()
            supplier = {
                "text": text,
                "blacklisted": "BLACKLISTED" in upper,
                "probation": "PROBATION" in upper,
                "contract_rates": {},
                "price_caps": {},
            }
            for currency, rate in re.findall(
                r"invoices in (GBP|EUR|USD) are converted at ₹\s*([\d,.]+)",
                text,
                flags=re.I,
            ):
                supplier["contract_rates"][currency.upper()] = float(rate.replace(",", ""))
            for category_name, price in re.findall(
                r"price cap for ([A-Za-z &-]+) of ₹\s*([\d,]+)",
                text,
                flags=re.I,
            ):
                supplier["price_caps"][category_name.strip().lower()] = float(price.replace(",", ""))
            suppliers[slug] = supplier

        elif "/amendments/" in path:
            effective = re.search(r"Effective from:\s*(\d{4}-\d{2}-\d{2})", text, re.I)
            change = re.search(
                r"(target price|walk-away price|approval limit) for ([A-Za-z &-]+) is now ₹\s*([\d,]+)",
                text,
                flags=re.I,
            )
            if effective and change:
                amendments.append(
                    (
                        effective.group(1),
                        slugify(change.group(2)),
                        change.group(1).lower(),
                        float(change.group(3).replace(",", "")),
                    )
                )

    # Fail early if a category file was not parsed; prevents None arithmetic.
    required = ("target", "walk", "approval")
    for slug, category in categories.items():
        missing = [key for key in required if category[key] is None]
        if missing:
            raise ValueError(
                f"Could not read {', '.join(missing)} from playbook category '{slug}'. "
                "Check the category Markdown formatting."
            )

    return docs, categories, suppliers, sorted(amendments)


def latest_supplier_message(message: str) -> str:
    """Return the supplier's latest message when the thread has explicit markers."""
    text = str(message)
    markers = list(re.finditer(r"\[Latest message[^]]*\]", text, flags=re.I))
    if markers:
        text = text[markers[-1].end():]
    else:
        # If there is no explicit latest marker, remove earlier-message blocks only.
        text = re.sub(r"\[Earlier message.*?\](.*?)(?=\[|$)", "", text, flags=re.I | re.S)
    return text.strip()


def extract_price(message: str, category: dict[str, Any], supplier: dict[str, Any]) -> float | None:
    """Extract and normalize the latest supplier offer to INR, ex-GST, per unit."""
    latest = latest_supplier_message(message)

    # Find explicit currency-prefixed amounts; choose the last one in the latest message.
    amount_pattern = re.compile(
        r"(₹|Rs\.?\s*|INR\s*|\$|USD\s*|€|EUR\s*|£|GBP\s*)"
        r"(\d[\d,]*(?:\.\d+)?\s*(?:k|lakhs?)?)",
        flags=re.I,
    )
    matches = list(amount_pattern.finditer(latest))
    if not matches:
        return None

    chosen = matches[-1]
    correction = re.search(r"(?:correction|should read|instead|correct price)[^\n]{0,140}", latest, re.I)
    if correction:
        corrected = [match for match in matches if match.start() >= correction.start()]
        if corrected:
            chosen = corrected[-1]

    currency_token = chosen.group(1).strip()
    amount = clean_number(chosen.group(2))
    if amount is None:
        return None

    token_upper = currency_token.upper().replace(".", "").strip()
    if currency_token.startswith("₹") or token_upper in {"RS", "INR"}:
        rate = 1.0
    elif currency_token == "$" or token_upper == "USD":
        rate = supplier.get("contract_rates", {}).get("USD", DEFAULT_RATES["USD"])
    elif currency_token == "€" or token_upper == "EUR":
        rate = supplier.get("contract_rates", {}).get("EUR", DEFAULT_RATES["EUR"])
    elif currency_token == "£" or token_upper == "GBP":
        rate = supplier.get("contract_rates", {}).get("GBP", DEFAULT_RATES["GBP"])
    else:
        return None

    price = amount * rate

    # If the offer explicitly says GST is included, compare ex-GST values.
    if re.search(r"(?:including|inclusive of|incl\.?\s*of)\s*GST", latest, re.I):
        price /= 1.0 + float(category["gst"])

    # Normalize monthly subscriptions to the annual unit where the category is annual.
    category_text = category["text"].lower()
    if "per seat per year" in category_text and re.search(r"per seat per month|/\s*month|monthly", latest, re.I):
        price *= 12
    elif "per seat per month" in category_text and re.search(r"per seat per year|/\s*year|annual", latest, re.I):
        price /= 12

    # Explicit total-for-all-units offers are converted to per-unit amounts.
    total_match = re.search(r"(?:total|in total)\s*(?:of)?\s*(?:₹|Rs\.?|INR)\s*[\d,]+", latest, re.I)
    if total_match:
        quantity_match = re.search(r"for all\s+(\d[\d,]*)\s+units", latest, re.I)
        if quantity_match:
            total_amount = clean_number(re.search(r"[\d,]+", total_match.group(0)).group(0))
            quantity = clean_number(quantity_match.group(1))
            if total_amount is not None and quantity:
                price = total_amount / quantity

    return price


def contains_prompt_injection(message: str) -> bool:
    """Conservative checks for text explicitly targeting an automated reviewer."""
    patterns = [
        r"(?:note|instruction|message)\s+for\s+(?:the\s+)?(?:language\s+model|AI|bot|assistant|reviewer)",
        r"(?:ignore|disregard|override)\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|rules|policies)",
        r"(?:system prompt|prompt injection|AI agent|automated system).{0,80}(?:approve|accept|ignore|override)",
        r"approval\s+(?:has\s+)?already\s+been\s+granted",
        r"tell\s+the\s+(?:AI|model|bot|reviewer)\s+to",
    ]
    return any(re.search(pattern, message, re.I | re.S) for pattern in patterns)


def contains_banned_term(message: str) -> bool:
    """Check latest supplier message for the playbook's banned contract terms."""
    text = latest_supplier_message(message)

    if re.search(r"auto[- ]?renew(?:s|al|ing)?|automatic(?:ally)? renew(?:s|al|ing)?", text, re.I):
        return True
    if re.search(r"continues? from year to year unless|renews? on its own", text, re.I):
        return True
    if re.search(r"unlimited liability", text, re.I):
        return True
    if re.search(r"exclusive(?:ly)?|exclusivity", text, re.I):
        if not re.search(r"(?:not asking for|no|without)\s+exclusiv(?:ity|e)", text, re.I):
            return True

    # Escalate only when an upfront/advance payment exceeds 30%.
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%\s*(?:upfront|in advance|advance payment)", text, re.I):
        if float(match.group(1)) > 30:
            return True
    if re.search(r"(?:upfront|advance payment)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*%", text, re.I):
        match = re.search(r"(?:upfront|advance payment)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*%", text, re.I)
        if match and float(match.group(1)) > 30:
            return True
    return False


def decide(row: pd.Series, categories, suppliers, amendments) -> str:
    category_slug = slugify(row["category"])
    category = categories.get(category_slug)
    if category is None:
        return "ESCALATE:MISSING_INFO:"

    supplier_slug = slugify(row["supplier"])
    supplier = suppliers.get(
        supplier_slug,
        {"blacklisted": False, "probation": False, "contract_rates": {}, "price_caps": {}, "text": ""},
    )
    message = str(row["supplier_message"])

    # Decision order follows the supplied decision-procedure.md.
    price = extract_price(message, category, supplier)
    if price is None:
        return "ESCALATE:MISSING_INFO:"
    if supplier.get("blacklisted"):
        return "REJECT:BLACKLISTED_SUPPLIER:"
    if contains_prompt_injection(message):
        return "ESCALATE:PROMPT_INJECTION:"
    if contains_banned_term(message):
        return "ESCALATE:BANNED_TERM:"

    target = float(category["target"])
    walkaway = float(category["walk"])
    approval_limit = float(category["approval"])
    thread_date = str(row["date"])[:10]

    # Apply all amendments effective on or before the thread date.
    for effective_date, amended_category, field, value in amendments:
        if amended_category == category_slug and effective_date <= thread_date:
            if field == "target price":
                target = value
            elif field == "walk-away price":
                walkaway = value
            elif field == "approval limit":
                approval_limit = value

    # A supplier's category-specific contract cap replaces the walk-away price.
    for cap_category, cap_value in supplier.get("price_caps", {}).items():
        if slugify(cap_category) == category_slug:
            walkaway = float(cap_value)

    rounds = max(1, int(category["rounds"]))
    current_round = max(1, int(float(row["round"])))
    beta = float(category["beta"])

    # Probation suppliers receive no concessions: every round remains at target.
    if supplier.get("probation"):
        level = target
    elif rounds <= 1:
        level = target
    else:
        progress = (current_round - 1) / (rounds - 1)
        progress = min(1.0, max(0.0, progress))
        level = target + (walkaway - target) * (progress ** beta)

    quantity = float(row["quantity"])
    if price <= level:
        if price * quantity > approval_limit:
            return "ESCALATE:OVER_APPROVAL_LIMIT:"
        return "ACCEPT:ACCEPTABLE_PRICE:"

    if current_round >= rounds:
        return "REJECT:ABOVE_WALKAWAY:"

    counter_price = math.floor(level + 0.5)
    return f"COUNTER:COUNTER_OFFER:{counter_price}"


def main() -> None:
    for required_file in (THREADS_FILE, TEMPLATE_FILE, PLAYBOOK_FILE):
        if not required_file.is_file():
            raise FileNotFoundError(
                f"Required file not found: {required_file}\n"
                "Check that threads.csv, sample_submission.csv, and playbook.zip are inside data/."
            )

    threads = pd.read_csv(THREADS_FILE).fillna("")
    template = pd.read_csv(TEMPLATE_FILE)

    required_columns = {
        "thread_id", "date", "supplier", "category", "quantity", "round", "supplier_message"
    }
    missing_columns = required_columns - set(threads.columns)
    if missing_columns:
        raise ValueError(f"threads.csv is missing columns: {sorted(missing_columns)}")
    if not {"thread_id", "label"}.issubset(template.columns):
        raise ValueError("sample_submission.csv must contain thread_id and label columns.")

    _, categories, suppliers, amendments = read_playbook()
    predictions = [decide(row, categories, suppliers, amendments) for _, row in threads.iterrows()]
    prediction_frame = pd.DataFrame({"thread_id": threads["thread_id"], "label": predictions})

    if prediction_frame["thread_id"].duplicated().any():
        raise ValueError("threads.csv contains duplicate thread_id values.")
    if template["thread_id"].duplicated().any():
        raise ValueError("sample_submission.csv contains duplicate thread_id values.")

    # Keep the exact ID order from Kaggle's sample submission file.
    result = template[["thread_id"]].merge(
        prediction_frame, on="thread_id", how="left", validate="one_to_one"
    )
    if result["label"].isna().any():
        missing_ids = result.loc[result["label"].isna(), "thread_id"].head(10).tolist()
        raise ValueError(f"No prediction found for some template IDs, e.g. {missing_ids}")
    if len(result) != len(template):
        raise ValueError(f"Output row count {len(result)} does not match template {len(template)}")

    result.to_csv(OUTPUT_FILE, index=False)
    print(f"Created submission file: {OUTPUT_FILE}")
    print(f"Rows: {len(result)} (expected {len(template)})")
    print("\nDecision counts:")
    print(result["label"].str.split(":").str[0].value_counts().to_string())
    print("\nPreview:")
    print(result.head(10).to_string(index=False))
    print("\nNote: This is a rules-based baseline. Validate the competition rules and predictions before submitting.")


if __name__ == "__main__":
    main()
