"""Quick scrape to capture raw data for debug mock."""
import json
from scraper_manager import ScraperManager
from scraper_config import create_custom_config
from vendors.cryptmtg import CryptMTGVendor
from vendors.magicarte import MagiCarteVendor


def main():
    card_list = "1 Sol Ring\n1 Command Tower"

    config = create_custom_config(
        scrapers=[CryptMTGVendor, MagiCarteVendor],
        min_cards=1,
        price_override=0.0,
        enable_filtering=False,
        headless=True,
    )

    manager = ScraperManager(config)
    parsed_cards = manager.parse_moxfield_format(card_list)
    raw_results = manager.scrape_all_parallel(cards=parsed_cards)

    # Serialize to JSON
    out = {}
    for vendor, prices in raw_results.items():
        out[vendor] = [
            {
                "card_name": p.card_name,
                "original_query": p.original_query,
                "price": p.price if p.price != float("inf") else None,
                "website": p.website,
                "found": p.found,
                "quantity_available": p.quantity_available,
                "set_code": p.set_code,
                "collector_number": p.collector_number,
                "foil": p.foil,
            }
            for p in prices
        ]

    with open("debug_raw.json", "w") as f:
        json.dump(out, f, indent=2)

    # Print summary
    for vendor, prices in out.items():
        found = [p for p in prices if p["found"]]
        print(f"\n{vendor}: {len(found)} found entries")
        for p in found[:5]:
            print(f"  {p['card_name']} | {p['set_code']}#{p['collector_number']} | ${p['price']} | foil={p['foil']} | qty={p['quantity_available']}")
        if len(found) > 5:
            print(f"  ... and {len(found) - 5} more")

    print(f"\nFull data saved to debug_raw.json")


if __name__ == "__main__":
    main()
