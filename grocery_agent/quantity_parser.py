"""
Deterministic parsing of quantity strings to float.
Handles simple fractions and decimals; returns None for "to taste", "pinch", etc.
"""
import re
from fractions import Fraction
from typing import Optional

# Strings that mean "no numeric quantity" - store as unit only, quantity_per_portion = None
QUALITATIVE_UNITS = frozenset(
    {"to taste", "pinch", "pinches", "some", "a little", "a bit", "dash", "optional"}
)


def parse_quantity(value: Optional[str]) -> Optional[float]:
    """
    Parse a quantity string to a float. Returns None for qualitative amounts.

    Handles: "2", "0.5", "1/2", "1 1/2", "½", "1.5".
    Returns None for: None, "", "to taste", "pinch", etc.
    """
    if value is None or not value.strip():
        return None
    s = value.strip().lower()
    if s in QUALITATIVE_UNITS:
        return None
    # Mixed number: "1 1/2" or "1 ½"
    parts = s.split()
    if len(parts) == 2 and parts[0].isdigit():
        try:
            whole = int(parts[0])
            frac_val = parse_quantity(parts[1])
            if frac_val is not None and 0 < frac_val < 1:
                return whole + frac_val
        except (ValueError, TypeError):
            pass
    # Simple fraction: "1/2", "½"
    if s in ("½", "1/2"):
        return 0.5
    if s in ("⅓", "1/3"):
        return 1 / 3
    if s in ("⅔", "2/3"):
        return 2 / 3
    if s in ("¼", "1/4"):
        return 0.25
    if s in ("¾", "3/4"):
        return 0.75
    if re.match(r"^\d+/\d+$", s):
        try:
            return float(Fraction(s))
        except (ValueError, ZeroDivisionError):
            return None
    # Decimal or integer: "2", "1.5"
    try:
        return float(s)
    except ValueError:
        pass
    # Strip trailing unit words and try again: "2 cups" -> we only parse "2" here; caller passes "2 cups", we might get "2" or "2 cups". For now we expect LLM to give quantity and unit separately. If we get "2 cups" in quantity we could try to parse "2" - strip non-numeric suffix.
    num_part = re.match(r"^([\d./\s½⅓⅔¼¾]+)", s)
    if num_part:
        try:
            return float(Fraction(num_part.group(1).strip()))
        except (ValueError, ZeroDivisionError):
            pass
    return None
