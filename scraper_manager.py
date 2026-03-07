import re
from typing import List, Dict, Optional, Callable, Tuple
from selenium import webdriver
from concurrent.futures import ThreadPoolExecutor, as_completed
from base_scraper import Card, CardPrice, BaseScraper
from scraper_config import ScraperConfig, VendorFilterConfig


class ScraperManager:
    """Manages multiple scrapers and applies vendor filtering logic"""

    def __init__(self, config: ScraperConfig):
        """
        Initialize the scraper manager

        Args:
            config: ScraperConfig with enabled scrapers and filtering rules
        """
        self.config = config
        self.driver = None
        self.scrapers: List[BaseScraper] = []

    def _initialize_driver(self) -> webdriver.Chrome:
        """Create a fresh ChromeDriver instance with standard options"""
        options = webdriver.ChromeOptions()
        if self.config.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        return driver

    def _scrape_single_vendor(
        self,
        scraper_class,
        cards: List[Card],
        status_callback: Optional[Callable[[str, str], None]] = None
    ) -> Tuple[str, List[CardPrice]]:
        """
        Scrape a single vendor in a thread-safe manner.
        Creates its own WebDriver instance.

        Args:
            scraper_class: The scraper class to instantiate
            cards: List of cards to search for
            status_callback: Optional callback(vendor_name, status) for progress updates

        Returns:
            Tuple of (vendor_name, list of CardPrice results)
        """
        driver = None
        vendor_name = "Unknown"

        try:
            # Create fresh driver for this thread
            driver = self._initialize_driver()
            scraper = scraper_class(driver)

            # Get vendor name from instance
            vendor_name = scraper.website_name

            # Notify starting
            if status_callback:
                status_callback(vendor_name, "loading")

            # Only scrape if enabled
            if not scraper.is_enabled():
                print(f"{vendor_name} is disabled, skipping...")
                if status_callback:
                    status_callback(vendor_name, "error")
                return (vendor_name, [])

            # Perform scraping
            print(f"Scraping {vendor_name}...")
            results = scraper.scrape(cards)
            print(f"  Successfully scraped {len([p for p in results if p.found])} cards from {vendor_name}")

            # Notify completion
            if status_callback:
                status_callback(vendor_name, "complete")

            return (vendor_name, results)

        except Exception as e:
            print(f"  Error scraping {vendor_name}: {e}")
            import traceback
            traceback.print_exc()

            # Notify error
            if status_callback:
                status_callback(vendor_name, "error")

            # Return empty results on error
            return (vendor_name, [])

        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

    def scrape_all_parallel(
        self,
        cards: List[Card],
        status_callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, List[CardPrice]]:
        """
        Scrape all enabled vendors in parallel.

        Args:
            cards: List of Card objects to search for
            status_callback: Optional callback(vendor_name, status) for progress updates

        Returns:
            Dict mapping vendor_name -> List[CardPrice]
        """
        all_results = {}

        # Use ThreadPoolExecutor for parallel scraping
        max_workers = min(len(self.config.enabled_scrapers), 5)  # Limit to 5 concurrent scrapers
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all scraping tasks
            future_to_scraper = {
                executor.submit(
                    self._scrape_single_vendor,
                    scraper_class,
                    cards,
                    status_callback
                ): scraper_class
                for scraper_class in self.config.enabled_scrapers
            }

            # Collect results as they complete
            for future in as_completed(future_to_scraper):
                vendor_name, results = future.result()
                all_results[vendor_name] = results

        return all_results

    def parse_moxfield_format(self, card_list: str) -> List[Card]:
        """Parse Moxfield format card list"""
        cards = []
        lines = card_list.strip().split("\n")
        for line in lines:
            if not line.strip():
                continue
            # Match pattern: quantity name (set) number [*F*]
            # Example: 1 Adagia, Windswept Bastion (EOE) 250
            # Example: Liberty Prime, Recharged (PIP) 5 *F*
            pattern = r"^(\d+)\s+(.+?)\s*(?:\(([A-Z0-9]+)\)\s*(\S+)(?:\s+\*F\*)?)?$"
            match = re.match(pattern, line.strip())
            if match:
                quantity = int(match.group(1))
                name = match.group(2).strip()
                set_code = match.group(3) if match.group(3) else None
                collector_number = match.group(4) if match.group(4) else None
                cards.append(
                    Card(
                        quantity=quantity,
                        name=name,
                        set_code=set_code,
                        collector_number=collector_number,
                    )
                )

        return cards

    def scrape_all(self, card_list: str, progress_callback=None) -> Dict:
        """
        Main method to scrape all websites and apply filtering logic

        Args:
            card_list: Card list in Moxfield format
            progress_callback: Optional callback function(current, total, message) for progress updates

        Returns:
            Dictionary with results including best prices, buy lists, and summary
        """
        try:
            # Initialize driver with improved options
            options = webdriver.ChromeOptions()
            if self.config.headless:
                options.add_argument("--headless=new")  # Use new headless mode
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")  # Disable GPU acceleration
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-software-rasterizer")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--window-size=1920,1080")

            # Add user agent to avoid detection
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

            # Suppress logging
            options.add_experimental_option('excludeSwitches', ['enable-logging'])

            try:
                self.driver = webdriver.Chrome(options=options)
                self.driver.set_page_load_timeout(30)
                print(f"ChromeDriver initialized successfully")
            except Exception as driver_error:
                print(f"Error initializing ChromeDriver: {driver_error}")
                print("\nTroubleshooting:")
                print("1. Make sure ChromeDriver is installed and matches your Chrome browser version")
                print("   Download from: https://chromedriver.chromium.org/downloads")
                print("2. Run the diagnostic script:")
                print("   python check_chromedriver.py")
                raise

            # Parse cards
            cards = self.parse_moxfield_format(card_list)
            print(f"Parsed {len(cards)} cards from input")

            # Initialize scrapers
            self.scrapers = [
                scraper_class(self.driver)
                for scraper_class in self.config.enabled_scrapers
                if scraper_class(self.driver).is_enabled()
            ]

            all_prices = []

            # Scrape each website
            total_scrapers = len(self.scrapers)
            for idx, scraper in enumerate(self.scrapers, 1):
                print(f"Scraping {scraper.website_name}...")

                # Call progress callback if provided
                if progress_callback:
                    progress_callback(idx, total_scrapers, f"Scraping {scraper.website_name}...")

                try:
                    prices = scraper.scrape(cards)
                    all_prices.extend(prices)
                    print(f"  Successfully scraped {len([p for p in prices if p.found])} cards from {scraper.website_name}")
                except Exception as scraper_error:
                    print(f"  Error scraping {scraper.website_name}: {scraper_error}")
                    import traceback
                    traceback.print_exc()
                    # Add not found entries for all cards for this scraper
                    not_found_prices = scraper._create_not_found_prices(cards)
                    all_prices.extend(not_found_prices)
                    print(f"  Continuing with other scrapers...")

            # Analyze results with vendor filtering
            if self.config.vendor_filter.enable_filtering:
                results = self._analyze_with_filtering(all_prices, cards)
            else:
                results = self._analyze_without_filtering(all_prices, cards)

            # Add all prices to results for debugging
            results["all_prices"] = all_prices

            return results

        finally:
            if self.driver:
                self.driver.quit()

    def _analyze_without_filtering(
        self, all_prices: List[CardPrice], cards: List[Card]
    ) -> Dict:
        """Analyze results without vendor filtering (original logic)"""
        results = {"best_prices": {}, "buy_lists": {}, "not_found": [], "summary": {}}

        # Group prices by card
        card_prices = {}
        for price in all_prices:
            if price.original_query not in card_prices:
                card_prices[price.original_query] = []
            card_prices[price.original_query].append(price)

        # Find best price for each card
        for card in cards:
            card_name = card.name
            if card_name in card_prices:
                found_prices = [p for p in card_prices[card_name] if p.found]

                if found_prices:
                    best_price = min(found_prices, key=lambda x: x.price)
                    results["best_prices"][card_name] = {
                        "quantity_needed": card.quantity,
                        "best_price": best_price.price,
                        "website": best_price.website,
                        "quantity_available": best_price.quantity_available,
                    }

                    # Add to buy list
                    if best_price.website not in results["buy_lists"]:
                        results["buy_lists"][best_price.website] = []
                    results["buy_lists"][best_price.website].append(
                        {
                            "card": card_name,
                            "quantity": card.quantity,
                            "price_per_unit": best_price.price,
                            "total_price": best_price.price * card.quantity,
                        }
                    )
                else:
                    results["not_found"].append(card_name)
            else:
                results["not_found"].append(card_name)

        # Calculate summary
        for website, cards_list in results["buy_lists"].items():
            total = sum(c["total_price"] for c in cards_list)
            results["summary"][website] = {
                "total_cards": len(cards_list),
                "total_price": round(total, 2),
            }

        return results

    def _analyze_with_filtering(
        self, all_prices: List[CardPrice], cards: List[Card]
    ) -> Dict:
        """
        Analyze results WITH vendor filtering logic

        Logic:
        1. Find best price for each card across all vendors
        2. Build initial buy list with best prices
        3. Apply filtering:
           - If a vendor has < min_cards_per_vendor cards, redistribute those cards
           - Exception: Keep the card if it's min_price_difference_override cheaper
        4. Redistribute filtered cards to next best vendor
        """
        config = self.config.vendor_filter
        results = {"best_prices": {}, "buy_lists": {}, "not_found": [], "summary": {}}

        # Group prices by card
        card_prices = {}
        for price in all_prices:
            if price.original_query not in card_prices:
                card_prices[price.original_query] = []
            card_prices[price.original_query].append(price)

        # Find all available prices for each card (sorted by price)
        card_price_options = {}
        for card in cards:
            card_name = card.name
            if card_name in card_prices:
                found_prices = [p for p in card_prices[card_name] if p.found]
                if found_prices:
                    # Sort by price
                    found_prices.sort(key=lambda x: x.price)
                    card_price_options[card_name] = {
                        "card": card,
                        "prices": found_prices,
                    }
                else:
                    results["not_found"].append(card_name)
            else:
                results["not_found"].append(card_name)

        # Build initial assignment (best price for each card)
        initial_assignment = {}
        for card_name, data in card_price_options.items():
            best_price = data["prices"][0]
            initial_assignment[card_name] = {
                "card": data["card"],
                "price_info": best_price,
                "all_prices": data["prices"],
            }

        # Group by vendor
        vendor_cards = {}
        for card_name, assignment in initial_assignment.items():
            website = assignment["price_info"].website
            if website not in vendor_cards:
                vendor_cards[website] = []
            vendor_cards[website].append(card_name)

        # Apply filtering logic
        # Step 1: Identify vendors with < min_cards
        vendors_to_filter = set()
        for website, cards_list in vendor_cards.items():
            if len(cards_list) < config.min_cards_per_vendor:
                vendors_to_filter.add(website)
                print(f"  Vendor '{website}' has only {len(cards_list)} cards (min: {config.min_cards_per_vendor}) - filtering...")

        # Step 2: For each vendor being filtered, check which cards qualify for price override
        cards_with_price_override = set()
        for card_name, assignment in initial_assignment.items():
            website = assignment["price_info"].website

            if website in vendors_to_filter:
                # This vendor is being filtered, check if card qualifies for price override
                all_prices = assignment["all_prices"]

                if len(all_prices) > 1:
                    best_price = all_prices[0].price
                    second_best_price = all_prices[1].price
                    price_diff = second_best_price - best_price

                    if price_diff >= config.min_price_difference_override:
                        # Price difference is significant, keep this card from filtered vendor
                        cards_with_price_override.add(card_name)
                        print(
                            f"  [OVERRIDE] Keeping {card_name} from {website} "
                            f"(${price_diff:.2f} cheaper than {all_prices[1].website}, override: ${config.min_price_difference_override})"
                        )

        # Step 3: Build final assignment
        final_assignment = {}
        for card_name, assignment in initial_assignment.items():
            card = assignment["card"]
            best_price_info = assignment["price_info"]
            all_prices = assignment["all_prices"]
            website = best_price_info.website

            # Keep card if:
            # - Vendor is NOT being filtered, OR
            # - Card qualifies for price override
            if website not in vendors_to_filter or card_name in cards_with_price_override:
                final_assignment[card_name] = assignment
            else:
                # Vendor is filtered and card doesn't qualify for override
                # Move to next best vendor
                if len(all_prices) > 1:
                    print(
                        f"  [MOVE] {card_name}: {website} (${best_price_info.price:.2f}) -> {all_prices[1].website} (${all_prices[1].price:.2f})"
                    )
                    final_assignment[card_name] = {
                        "card": card,
                        "price_info": all_prices[1],
                        "all_prices": all_prices,
                    }
                else:
                    # Only one vendor has this card, keep it even though vendor is filtered
                    print(f"  [WARN] Keeping {card_name} from {website} (only vendor with this card)")
                    final_assignment[card_name] = assignment

        # Build final results
        for card_name, assignment in final_assignment.items():
            card = assignment["card"]
            price_info = assignment["price_info"]

            results["best_prices"][card_name] = {
                "quantity_needed": card.quantity,
                "best_price": price_info.price,
                "website": price_info.website,
                "quantity_available": price_info.quantity_available,
            }

            # Add to buy list
            if price_info.website not in results["buy_lists"]:
                results["buy_lists"][price_info.website] = []
            results["buy_lists"][price_info.website].append(
                {
                    "card": card_name,
                    "quantity": card.quantity,
                    "price_per_unit": price_info.price,
                    "total_price": price_info.price * card.quantity,
                }
            )

        # Calculate summary
        for website, cards_list in results["buy_lists"].items():
            total = sum(c["total_price"] for c in cards_list)
            results["summary"][website] = {
                "total_cards": len(cards_list),
                "total_price": round(total, 2),
            }

        return results

    def recalculate_results_for_selected_vendors(
        self,
        all_vendor_results: Dict[str, List[CardPrice]],
        parsed_cards: List[Card],
        selected_vendors: List[str],
        vendor_preferences: List[str],
        preference_threshold: float
    ) -> Dict:
        """
        Recalculate best prices and buy lists based on selected vendors and preferences.
        Does NOT re-scrape - uses cached results.

        Args:
            all_vendor_results: Complete results from all scrapers
            parsed_cards: Original parsed card list
            selected_vendors: List of vendor names user wants to buy from
            vendor_preferences: Ordered list of preferred vendors (most preferred first)
            preference_threshold: Max price difference to keep card at preferred vendor

        Returns:
            Dict with best_prices, buy_lists, summary, not_found
        """
        # Filter to only selected vendors
        filtered_results = {
            vendor: results
            for vendor, results in all_vendor_results.items()
            if vendor in selected_vendors
        }

        # Flatten all prices from selected vendors
        all_prices = []
        for vendor_name, prices in filtered_results.items():
            all_prices.extend(prices)

        # Build best prices using preference logic
        best_prices = {}
        card_prices = {}

        # Group prices by card
        for price in all_prices:
            if price.original_query not in card_prices:
                card_prices[price.original_query] = []
            card_prices[price.original_query].append(price)

        # Find best price for each card using preference logic
        for card in parsed_cards:
            card_name = card.name
            if card_name in card_prices:
                found_prices = [p for p in card_prices[card_name] if p.found]

                if found_prices:
                    # Apply preference-based selection
                    selected_price = self._select_vendor_with_preference(
                        found_prices,
                        vendor_preferences,
                        preference_threshold,
                        selected_vendors
                    )

                    if selected_price:
                        best_prices[card_name] = {
                            "quantity_needed": card.quantity,
                            "best_price": selected_price.price,
                            "website": selected_price.website,
                            "quantity_available": selected_price.quantity_available
                        }

        # Build buy lists per vendor
        buy_lists = self._build_buy_lists(best_prices)

        # Calculate summary
        summary = self._calculate_summary(buy_lists)

        # Find cards not found in selected vendors
        not_found = [
            card.name for card in parsed_cards
            if card.name not in best_prices
        ]

        return {
            "best_prices": best_prices,
            "buy_lists": buy_lists,
            "summary": summary,
            "not_found": not_found,
            "all_prices": all_prices
        }

    def _select_vendor_with_preference(
        self,
        available_prices: List[CardPrice],
        vendor_preferences: List[str],
        threshold: float,
        selected_vendors: List[str]
    ) -> Optional[CardPrice]:
        """
        Select vendor for a card based on preference order and threshold.

        Logic:
        1. Find the absolute cheapest price among selected vendors
        2. For each vendor in preference order:
           - If vendor is in selected_vendors AND has this card:
             - If price <= (cheapest + threshold): select this vendor
        3. If no preferred vendor within threshold, select absolute cheapest
        """
        if not available_prices:
            return None

        # Sort by price (ascending)
        sorted_prices = sorted(available_prices, key=lambda p: p.price)
        cheapest_price = sorted_prices[0].price

        # Try to find a preferred vendor within threshold
        for preferred_vendor in vendor_preferences:
            if preferred_vendor not in selected_vendors:
                continue  # Skip unselected vendors

            for price in available_prices:
                if price.website == preferred_vendor:
                    if price.price <= (cheapest_price + threshold):
                        return price
                    break  # This vendor's price is too high

        # Fall back to absolute cheapest
        return sorted_prices[0]

    def _build_buy_lists(self, best_prices: Dict) -> Dict:
        """Build per-vendor shopping lists from best prices."""
        buy_lists = {}

        for card_name, details in best_prices.items():
            vendor = details["website"]
            if vendor not in buy_lists:
                buy_lists[vendor] = []

            buy_lists[vendor].append({
                "card": card_name,
                "quantity": details["quantity_needed"],
                "price_per_unit": details["best_price"],
                "total_price": details["best_price"] * details["quantity_needed"]
            })

        return buy_lists

    def _calculate_summary(self, buy_lists: Dict) -> Dict:
        """Calculate summary statistics per vendor."""
        summary = {}

        for vendor, items in buy_lists.items():
            total_cards = sum(item["quantity"] for item in items)
            total_price = sum(item["total_price"] for item in items)

            summary[vendor] = {
                "total_cards": total_cards,
                "total_price": round(total_price, 2)
            }

        return summary

    def print_results(self, results: Dict):
        """Print formatted results"""
        print("\n" + "=" * 60)
        print("MTG CARD PRICE COMPARISON RESULTS")
        print("=" * 60)

        print("\n== BEST PRICES BY CARD:")
        print("-" * 40)
        for card, info in results["best_prices"].items():
            print(f"* {card}")
            print(f"  Quantity needed: {info['quantity_needed']}")
            print(f"  Best price: ${info['best_price']:.2f} @ {info['website']}")
            print(f"  Available: {info['quantity_available']}")

        print("\n== RECOMMENDED BUY LISTS:")
        print("-" * 40)
        for website, cards_list in results["buy_lists"].items():
            print(f"\n{website}:")
            total = 0
            for item in cards_list:
                item_total = item["total_price"]
                total += item_total
                print(
                    f"  * {item['quantity']}x {item['card']} @ ${item['price_per_unit']:.2f} = ${item_total:.2f}"
                )
            print(f"  TOTAL: ${total:.2f}")

        if results["not_found"]:
            print("\n== CARDS NOT FOUND:")
            print("-" * 40)
            for card in results["not_found"]:
                print(f"  * {card}")

        print("\n== SUMMARY:")
        print("-" * 40)
        for website, summary in results["summary"].items():
            print(
                f"{website}: {summary['total_cards']} cards = ${summary['total_price']:.2f}"
            )

        if results["summary"]:
            grand_total = sum(s["total_price"] for s in results["summary"].values())
            print(f"\nGRAND TOTAL (if buying optimally): ${grand_total:.2f}")
