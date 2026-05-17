from pricer.items import Item
import json
import re

# business decisions to make
MIN_CHARS = (
    600  # ignore products with descriptions that are too short - not enough to train on
)
MIN_PRICE = 0.5
MAX_PRICE = 999.49  # rounds to 999, we are limiting the range of the price that we are predicting, we don't want to be confused by outliers
MAX_TEXT_EACH = 3000
MAX_TEXT_TOTAL = 4000

REMOVALS = [
    "Part Number",
    "Best Sellers Rank",
    "Batteries Included?",
    "Batteries Required?",
    "Item model number",
]

# The purpose of this file is to take data from huggingface and turn it into an item pydantic object


def simplify(text_list) -> str:
    """
    Return a simplified string without too much whitespace and limited to MAX_TEXT characters
    """
    return (
        str(text_list)
        .replace("\n", " ")
        .replace("\r", "")
        .replace("\t", "")
        .replace("  ", " ")
        .strip()[:MAX_TEXT_EACH]
    )


def scrub(title, description, features, details) -> str:
    """
    Return a cleansed full string with product numbers and unimportant details removed
    """
    for remove in REMOVALS:
        details.pop(remove, None)
    result = title + "\n"
    if description:
        result += simplify(description) + "\n"
    if features:
        result += simplify(features) + "\n"
    if details:
        result += json.dumps(details) + "\n"
    pattern = r"\b(?=[A-Z0-9]{7,}\b)(?=.*[A-Z])(?=.*\d)[A-Z0-9]+\b"
    return re.sub(pattern, "", result).strip()[:MAX_TEXT_TOTAL]


def get_weight(details):
    weight_str = details.get("Item Weight")
    if weight_str:
        parts = weight_str.split(" ")
        amount = float(parts[0])
        unit = parts[1].lower()
        if unit == "pounds":
            return amount
        elif unit == "ounces":
            return amount / 16
        elif unit == "grams":
            return amount / 453.592
        elif unit == "milligrams":
            return amount / 453592
        elif unit == "kilograms":
            return amount / 0.453592
        elif unit == "hundredths" and parts[2].lower() == "pounds":
            return amount / 100
    return 0


def parse(datapoint, category):
    """Takes a hugging face datapoint and returns an item pydantic object after populating the right fields"""
    try:
        price = float(datapoint["price"])
    except ValueError:
        return None
    if MIN_PRICE <= price <= MAX_PRICE:
        title = datapoint["title"]
        description = datapoint["description"]
        features = datapoint["features"]
        details = json.loads(datapoint["details"])
        weight = get_weight(details)
        full = scrub(title, description, features, details)
        if len(full) >= MIN_CHARS:
            return Item(
                title=title,
                category=category,
                price=price,
                full=full,
                weight=weight,
            )
