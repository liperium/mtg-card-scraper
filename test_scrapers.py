"""
Quick scraper test: Sol Ring + Command Tower across all vendors.
Checks that set_code, collector_number, and foil are parsed correctly.
"""
from scraper_manager import ScraperManager
from scraper_config import create_custom_config
from vendors import (
    CryptMTGVendor,
    MagiCarteVendor,
    FaceToFaceGamesVendor,
    ImaginaireVendor,
    MythicStoreVendor,
    GodsArenaVendor,
)

CARD_LIST = """\
1 Sol Ring
1 Command Tower
"""

def main():
    config = create_custom_config(
        scrapers=[
            MagiCarteVendor,
            CryptMTGVendor,
            ImaginaireVendor,
            MythicStoreVendor,
            GodsArenaVendor,
            FaceToFaceGamesVendor,
        ],
        headless=True,
    )
    manager = ScraperManager(config)
    parsed_cards = manager.parse_moxfield_format(CARD_LIST)
    print(f"Parsed cards: {[(c.name, c.set_code, c.collector_number, c.foil) for c in parsed_cards]}")
    print()

    print("Scraping all vendors in parallel...")
    raw_results = manager.scrape_all_parallel(cards=parsed_cards)

    print("\n" + "=" * 70)
    print("RESULTS BY VENDOR")
    print("=" * 70)

    for vendor, prices in sorted(raw_results.items()):
        found = [p for p in prices if p.found]
        not_found = [p for p in prices if not p.found]
        print(f"\n{vendor}  ({len(found)} found, {len(not_found)} not found)")
        print("-" * 50)
        for p in found:
            set_info = ""
            if p.set_code:
                set_info = f"  set={p.set_code}"
                if p.collector_number:
                    set_info += f" #{p.collector_number}"
            foil_info = "  FOIL" if p.foil else ""
            print(f"  ✓ {p.original_query:<20} ${p.price:.2f}  qty={p.quantity_available}{set_info}{foil_info}")
        for p in not_found:
            print(f"  ✗ {p.original_query} — not found")

    print("\n" + "=" * 70)
    print("SET CODE / COLLECTOR NUMBER PARSE CHECK")
    print("=" * 70)
    set_found = 0
    set_missing = 0
    for vendor, prices in sorted(raw_results.items()):
        for p in prices:
            if not p.found:
                continue
            if p.set_code:
                set_found += 1
            else:
                set_missing += 1
                print(f"  [NO SET] {vendor}: {p.original_query}")
    print(f"\nTotal found prices: {set_found + set_missing}")
    print(f"  With set code:    {set_found}")
    print(f"  Without set code: {set_missing}")

if __name__ == "__main__":
    main()
