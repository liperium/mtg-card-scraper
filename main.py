"""
MTG Card Price Scraper - Main Entry Point

Usage:
    uv run python main.py
"""

import pandas as pd
from scraper_manager import ScraperManager
from scraper_config import create_custom_config
from vendors import ImaginaireVendor


def main():
    card_list = """
1 An Offer You Can't Refuse
1 Arcane Denial
1 Ashiok, Dream Render
1 Breeding Pool
1 Cankerbloom
1 Conduit of Worlds
1 Dreamroot Cascade
1 Fabled Passage
1 Generous Patron
1 Kodama of the West Tree
1 Plaza of Heroes
1 Rejuvenating Springs
1 Soul-Guide Lantern
1 V.A.T.S.
1 Wave Goodbye
1 Yavimaya Coast
    """

    config = create_custom_config(
        scrapers=[ImaginaireVendor],
        min_cards=1,
        price_override=0.0,
        enable_filtering=False,
        headless=False,
    )

    print("=" * 60)
    print("MTG CARD PRICE SCRAPER - Imaginaire debug run")
    print("=" * 60)

    manager = ScraperManager(config)

    try:
        parsed_cards = manager.parse_moxfield_format(card_list)
        raw_results = manager.scrape_all_parallel(cards=parsed_cards)

        vendor_names = list(raw_results.keys())
        results = manager.recalculate_results_for_selected_vendors(
            all_vendor_results=raw_results,
            parsed_cards=parsed_cards,
            selected_vendors=vendor_names,
        )

        manager.print_results(results)

        if results.get("all_prices"):
            all_prices_data = []
            for price in results["all_prices"]:
                all_prices_data.append({
                    "card_name": price.card_name,
                    "original_query": price.original_query,
                    "price": price.price if price.found else None,
                    "website": price.website,
                    "found": price.found,
                    "quantity_available": price.quantity_available if price.found else None,
                })
            df_all = pd.DataFrame(all_prices_data)
            df_all = df_all.sort_values(by=["original_query", "price"])
            df_all.to_csv("mtg_all_prices.csv", index=False, quoting=2)
            print("[OK] All prices saved to mtg_all_prices.csv")

    except Exception as e:
        print(f"Error during scraping: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
