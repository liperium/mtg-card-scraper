"""
MTG Card Price Scraper - Main Entry Point

This script provides a command-line interface for scraping MTG card prices
from multiple websites and finding the best deals.

Usage:
    python main.py

The script will use the example card list below, or you can modify it
to use your own cards.
"""

import pandas as pd
from scraper_manager import ScraperManager
from scraper_config import create_default_config, create_custom_config
from scrapers import CryptMTGScraper, MagiCarteScraper, FaceToFaceGamesScraper


def main():
    """Main entry point for the scraper"""

    # Example Moxfield format card list
    card_list = """
1 Boompile (CMM) 371
1 Chromatic Lantern (PLG25) 1 *F*
1 Dawnsire, Sunstar Dreadnought (EOE) 238
1 Esper Sentinel (PLST) MH2-12
1 Final Showdown (OTJ) 11
1 Forensic Gadgeteer (MKM) 57
1 Magistrate's Scepter (M19) 238
1 Mendicant Core, Guidelight (DFT) 213
1 Pinnacle Emissary (EOE) 223
1 The Seriema (EOE) 35
1 Uthros, Titanic Godcore (EOE) 260
    """

    # Option 1: Use default configuration (all scrapers, default filtering)
    # config = create_default_config()

    # Option 2: Create custom configuration
    # Uncomment and modify as needed:
    config = create_custom_config(
        scrapers=[
            CryptMTGScraper,
            MagiCarteScraper,
            FaceToFaceGamesScraper
        ],
        min_cards=4,  # Require at least 4 cards per vendor
        price_override=5.0,  # Override if card is $5+ cheaper
        enable_filtering=True,  # Enable vendor filtering
        headless=True,  # Show browser window
    )

    # Option 3: Disable filtering to always get absolute best prices
    # config = create_custom_config(enable_filtering=False)

    print("=" * 60)
    print("MTG CARD PRICE SCRAPER")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  Enabled scrapers: {[s.__name__ for s in config.enabled_scrapers]}")
    print(f"  Vendor filtering: {config.vendor_filter.enable_filtering}")
    if config.vendor_filter.enable_filtering:
        print(f"    Min cards per vendor: {config.vendor_filter.min_cards_per_vendor}")
        print(
            f"    Price override threshold: ${config.vendor_filter.min_price_difference_override}"
        )
    print(f"  Headless mode: {config.headless}")
    print()

    # Initialize scraper manager
    manager = ScraperManager(config)

    try:
        # Scrape all websites
        results = manager.scrape_all(card_list)

        # Print results
        manager.print_results(results)

        # Optional: Save to CSV
        if results["best_prices"]:
            # Save best prices
            df_best = pd.DataFrame.from_dict(results["best_prices"], orient="index")
            df_best.index.name = "card_name"
            df_best.reset_index(inplace=True)
            df_best = df_best.sort_values(by=["website", "card_name"])
            df_best.to_csv("mtg_best_prices.csv", index=False, quoting=2)
            print("\n[OK] Best prices saved to mtg_best_prices.csv")

        # Save all prices for debugging
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
