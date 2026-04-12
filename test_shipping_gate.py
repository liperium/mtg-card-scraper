"""Test the shipping gate logic in recalculate_results_for_selected_vendors."""
import sys
sys.path.insert(0, '.')

from base_vendor import Card, CardPrice
from scraper_manager import ScraperManager
from scraper_config import ScraperConfig, VendorFilterConfig


def make_manager():
    config = ScraperConfig(
        enabled_scrapers=[],
        vendor_filter=VendorFilterConfig(enable_filtering=False),
        headless=True,
    )
    return ScraperManager(config)


def run(label, all_vendor_results, cards, vendor_shipping, budget=0.0):
    manager = make_manager()
    results = manager.recalculate_results_for_selected_vendors(
        all_vendor_results=all_vendor_results,
        parsed_cards=cards,
        selected_vendors=list(all_vendor_results.keys()),
        vendor_shipping_costs=vendor_shipping,
        vendor_weights={},
        min_cards_per_vendor=1,
        consolidation_budget=budget,
    )
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"{'='*60}")
    for vendor, items in results["buy_lists"].items():
        s = results["summary"][vendor]
        total_cards = sum(i["quantity"] for i in items)
        cards_str = ", ".join(f"{i['card']} ${i['price_per_unit']:.2f}" for i in items)
        print(f"  {vendor}: {total_cards} card(s) [{cards_str}]")
        print(f"    subtotal=${s['total_price']:.2f}  shipping=${s['shipping_cost']:.2f}  total=${s['effective_total']:.2f}")
    if results["not_found"]:
        print(f"  NOT FOUND: {results['not_found']}")
    if results.get("warnings"):
        for w in results["warnings"]:
            print(f"  WARNING: {w}")
    grand = sum(s["effective_total"] for s in results["summary"].values())
    print(f"  GRAND TOTAL: ${grand:.2f}")


# -----------------------------------------------------------------------
# CASE 1: Both cards at local store, one cheaper at shipping store
# Expected: gate fires → both at MagiCarte (total ~$2.30, no shipping)
# -----------------------------------------------------------------------
run(
    "Case 1: local has both, shipping store has both but cheaper per-card",
    all_vendor_results={
        "MagiCarte": [
            CardPrice("Arcane Signet", "Arcane Signet", 1.10, "MagiCarte", True, 4),
            CardPrice("Boompile",      "Boompile",      1.20, "MagiCarte", True, 2),
        ],
        "Arène des Dieux": [
            CardPrice("Arcane Signet", "Arcane Signet", 1.05, "Arène des Dieux", True, 3),
            CardPrice("Boompile",      "Boompile",      0.99, "Arène des Dieux", True, 5),
        ],
    },
    cards=[Card(1, "Arcane Signet"), Card(1, "Boompile")],
    vendor_shipping={"MagiCarte": 0.0, "Arène des Dieux": 10.0},
)

# -----------------------------------------------------------------------
# CASE 2: Boompile ONLY at shipping store (no local alternative)
# Expected: Arcane at MagiCarte, Boompile stuck at Arène (unavoidable)
# -----------------------------------------------------------------------
run(
    "Case 2: Boompile only at shipping store",
    all_vendor_results={
        "MagiCarte": [
            CardPrice("Arcane Signet", "Arcane Signet", 1.10, "MagiCarte", True, 4),
            CardPrice("Boompile",      "Boompile",      0.0,  "MagiCarte", False, 0),
        ],
        "Arène des Dieux": [
            CardPrice("Arcane Signet", "Arcane Signet", 1.05, "Arène des Dieux", True, 3),
            CardPrice("Boompile",      "Boompile",      0.99, "Arène des Dieux", True, 5),
        ],
    },
    cards=[Card(1, "Arcane Signet"), Card(1, "Boompile")],
    vendor_shipping={"MagiCarte": 0.0, "Arène des Dieux": 10.0},
)

# -----------------------------------------------------------------------
# CASE 3: Case 1 but with consolidation budget=$1 — what happens?
# Expected: same as case 1 (both at MagiCarte)
# -----------------------------------------------------------------------
run(
    "Case 3: same as Case 1 but consolidation_budget=1.0",
    all_vendor_results={
        "MagiCarte": [
            CardPrice("Arcane Signet", "Arcane Signet", 1.10, "MagiCarte", True, 4),
            CardPrice("Boompile",      "Boompile",      1.20, "MagiCarte", True, 2),
        ],
        "Arène des Dieux": [
            CardPrice("Arcane Signet", "Arcane Signet", 1.05, "Arène des Dieux", True, 3),
            CardPrice("Boompile",      "Boompile",      0.99, "Arène des Dieux", True, 5),
        ],
    },
    cards=[Card(1, "Arcane Signet"), Card(1, "Boompile")],
    vendor_shipping={"MagiCarte": 0.0, "Arène des Dieux": 10.0},
    budget=1.0,
)
