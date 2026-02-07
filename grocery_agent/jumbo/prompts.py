"""Build task prompts for the Jumbo browser agent."""

NON_PERISHABLE_CATEGORIES = frozenset({"pantry", "spice", "condiment"})


def build_login_task(site: str, email: str, password: str) -> str:
    """Build the initial login task."""
    return f"""Go to {site}.
If the site shows you are logged out or asks you to sign in, log in first: use email "{email}" and password "{password}". Then continue.
After logging in, stay on the site and wait for further instructions."""


def build_item_task(
    item: dict,
    item_num: int,
    total_items: int,
    non_perishable_categories: frozenset[str] | None = None,
) -> str:
    """Build a focused task for a single grocery item."""
    non_perishable_categories = non_perishable_categories or NON_PERISHABLE_CATEGORIES

    name = item.get("name", "").strip()
    amount_str = item.get("amount_str", "").strip()
    form = item.get("form", "fresh").strip().lower()
    optional = item.get("optional", False)
    pantry_item = item.get("pantry_item", False)
    category = (item.get("category") or "").strip().lower()
    search_query = name

    task_parts = [
        f"ITEM {item_num} of {total_items}: {name.upper()}",
        "",
        "IMPORTANT: The website is in Spanish. All searches and product interactions must be done in Spanish.",
        "",
    ]

    if amount_str:
        task_parts.append(f"Amount needed: {amount_str}")
    task_parts.append(f"Required form: {form} (translate to Spanish when searching)")
    if optional:
        task_parts.append("[OPTIONAL - you can skip if you don't find a good option]")

    if pantry_item and category in non_perishable_categories:
        task_parts.append("")
        task_parts.append("This is a pantry staple (non-perishable). Prefer buying a larger package size when it has a better price per kg to optimize for cost (e.g. 1 kg flour instead of 500 g if cheaper per kg).")

    task_parts.extend([
        "",
        f"1. Search in Spanish: '{search_query}'",
        "2. Review ALL search results carefully",
        f"3. Choose an option that matches the form '{form}' (ALWAYS take into account the form of the ingredient)",
        "4. When comparing multiple options that fit the form requirement, prefer the one with the better price per kg (or per unit if kg is not available)",
        "5. Check if this item is already in your cart. If it is, verify the quantity matches what is required; if not, update quantity or add more units.",
        "6. If not in cart, add the selected item to the cart. Before confirming: set the quantity (or number of units) so the TOTAL matches the QUANTITY REQUIRED above (e.g. 20 cloves = add enough for 20 cloves, not just 1 or 2).",
    ])

    if not optional:
        task_parts.extend([
            "",
            "7. If you cannot find a good match for the exact item with the required form:",
            "   - Try searching for a similar/reasonable replacement (e.g., different brand, slightly different form, or a close substitute)",
            "   - The replacement should serve the same purpose in cooking (e.g., if you can't find 'fresh tomatoes', 'canned tomatoes' might work)",
            "   - Only use a replacement if absolutely necessary - prefer the exact item when possible",
            "   - Add the replacement to the cart if it's reasonable",
        ])

    task_parts.extend([
        "",
        "After completing this item, stop and wait for the next instruction.",
    ])

    return "\n".join(task_parts)


def build_fallback_task(site: str, email: str, password: str) -> str:
    """Build fallback task when no grocery list is present."""
    return f"""Go to {site}.
If the site shows you are logged out or asks you to sign in, log in first: use email "{email}" and password "{password}". Then continue.
Search for papas (in Spanish) and add them to the cart. Then stop."""
