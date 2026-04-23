import re
import os
from typing import List, Dict, Optional, Callable, Tuple
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from concurrent.futures import ThreadPoolExecutor, as_completed
from base_vendor import Card, CardPrice
from scraper_config import ScraperConfig


class ScraperManager:
    """Manages multiple scrapers and applies vendor filtering logic"""

    def __init__(self, config: ScraperConfig):
        """
        Initialize the scraper manager

        Args:
            config: ScraperConfig with enabled scrapers and filtering rules
        """
        self.config = config

    def _initialize_driver(self) -> webdriver.Chrome:
        """Create a fresh ChromeDriver instance with standard options"""
        options = webdriver.ChromeOptions()
        if self.config.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        #options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        #options.add_experimental_option('excludeSwitches', ['enable-logging'])

        # Use Nix-provided chromedriver if available (for NixOS compatibility)
        chromedriver_path = os.environ.get('CHROMEDRIVER_PATH')
        chrome_bin = os.environ.get('CHROME_BIN')

        if chrome_bin and os.path.isfile(chrome_bin):
            options.binary_location = chrome_bin

        if chromedriver_path and os.path.isfile(chromedriver_path):
            service = Service(executable_path=chromedriver_path)
            driver = webdriver.Chrome(service=service, options=options)
        else:
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
            vendor_name = scraper.name

            # Notify starting
            if status_callback:
                status_callback(vendor_name, "loading")

            # Only scrape if enabled
            if not scraper.is_enabled():
                print(f"{vendor_name} - Disabled, skipping...")
                if status_callback:
                    status_callback(vendor_name, "error")
                return (vendor_name, [])

            # Perform scraping
            print(f"{vendor_name} - Scraping...")
            results = scraper.scrape(cards)
            print(f"{vendor_name} - Successfully scraped {len([p for p in results if p.found])} cards")

            # Notify completion
            if status_callback:
                status_callback(vendor_name, "complete")

            return (vendor_name, results)

        except Exception as e:
            print(f"{vendor_name} - Error scraping: {e}")
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
            pattern_with_qty = r"^(\d+)\s+(.+?)\s*(?:\(([A-Z0-9]+)\)\s*(\S+))?(\s+\*F\*)?\s*$"
            # Pattern without quantity (defaults to 1)
            # Example: Lightning Bolt (2XM) 141
            pattern_no_qty = r"^([A-Za-z].+?)\s*(?:\(([A-Z0-9]+)\)\s*(\S+))?(\s+\*F\*)?\s*$"

            match = re.match(pattern_with_qty, line.strip())
            if match:
                quantity = int(match.group(1))
                name = match.group(2).strip()
                set_code = match.group(3) if match.group(3) else None
                collector_number = match.group(4) if match.group(4) else None
                foil = bool(match.group(5))
                cards.append(
                    Card(
                        quantity=quantity,
                        name=name,
                        set_code=set_code,
                        collector_number=collector_number,
                        foil=foil,
                    )
                )
            else:
                # Try pattern without quantity (default to 1)
                match = re.match(pattern_no_qty, line.strip())
                if match:
                    quantity = 1
                    name = match.group(1).strip()
                    set_code = match.group(2) if match.group(2) else None
                    collector_number = match.group(3) if match.group(3) else None
                    foil = bool(match.group(4))
                    cards.append(
                        Card(
                            quantity=quantity,
                            name=name,
                            set_code=set_code,
                            collector_number=collector_number,
                            foil=foil,
                        )
                    )

        return cards

    @staticmethod
    def _matches_pin(price: CardPrice, pin: Optional[Dict]) -> bool:
        """Return True if price matches the pinned printing (or no pin set)."""
        if not pin:
            return True
        return (
            price.set_code == pin["set_code"]
            and price.collector_number == pin["collector_number"]
            and price.foil == pin["foil"]
        )

    @staticmethod
    def _make_best_price_entry(card_price: CardPrice, quantity_needed: int) -> Dict:
        """Build a best_prices dict entry from a CardPrice and quantity."""
        return {
            "quantity_needed": quantity_needed,
            "best_price": card_price.price,
            "website": card_price.website,
            "quantity_available": card_price.quantity_available,
            "set_code": card_price.set_code,
            "collector_number": card_price.collector_number,
            "foil": card_price.foil,
        }

    def _apply_shipping_costs(
        self,
        best_prices: Dict,
        vendor_shipping_costs: Dict[str, float],
        card_prices: Dict[str, List[CardPrice]],
        selected_vendors: List[str],
        vendor_weights: Dict[str, float] = None,
        pinned_printings: Optional[Dict[str, Dict]] = None,
    ) -> Dict:
        """
        Post-process assignments: if a shipping vendor's total effective savings across
        all its assigned cards don't justify its flat shipping cost, reassign those cards
        to their cheapest weighted alternatives.

        Uses weighted effective prices (raw * weight) so that a preferred store's
        savings are valued appropriately — consistent with Step 1 selection.
        The shipping fee itself is always a real dollar cost.
        """
        weights = vendor_weights or {}

        # Group current assignments by vendor
        vendor_assignments: Dict[str, List[str]] = {}
        for card_name, info in best_prices.items():
            v = info["website"]
            vendor_assignments.setdefault(v, []).append(card_name)

        for vendor, assigned_cards in list(vendor_assignments.items()):
            shipping_cost = vendor_shipping_costs.get(vendor, 0.0)
            if shipping_cost <= 0:
                continue  # Local pickup — no check needed

            vendor_weight = weights.get(vendor, 1.0)
            total_savings = 0.0
            card_alternatives: Dict[str, CardPrice] = {}

            for card_name in assigned_cards:
                current_price = best_prices[card_name]["best_price"]
                pin = (pinned_printings or {}).get(card_name)
                alternatives = [
                    p for p in card_prices.get(card_name, [])
                    if p.found and p.website != vendor and p.website in selected_vendors
                    and self._matches_pin(p, pin)
                ]
                if alternatives:
                    # Best alternative by weighted effective price (same as Step 1)
                    best_alt = min(alternatives, key=lambda p: p.price * weights.get(p.website, 1.0))
                    # Savings in real dollars: how much more we'd pay at the alternative
                    total_savings += best_alt.price - current_price
                    card_alternatives[card_name] = best_alt
                # No alternative → card stays at shipping vendor regardless

            # If real-dollar savings don't cover the flat shipping fee, reassign
            if total_savings < shipping_cost:
                print(
                    f"Shipping gate: {vendor} effective savings ${total_savings:.2f} "
                    f"< ${shipping_cost:.2f} shipping — reassigning {len(card_alternatives)} card(s)"
                )
                for card_name, alt in card_alternatives.items():
                    best_prices[card_name] = self._make_best_price_entry(
                        alt, best_prices[card_name]["quantity_needed"]
                    )

        return best_prices

    def recalculate_results_for_selected_vendors(
        self,
        all_vendor_results: Dict[str, List[CardPrice]],
        parsed_cards: List[Card],
        selected_vendors: List[str],
        vendor_shipping_costs: Dict[str, float] = None,
        vendor_weights: Dict[str, float] = None,
        min_cards_per_vendor: int = 1,
        consolidation_budget: float = 0.0,
        pinned_printings: Optional[Dict[str, Dict]] = None,
    ) -> Dict:
        """
        Recalculate best prices and buy lists based on selected vendors.
        Does NOT re-scrape - uses cached results.

        Selection logic (in order):
          1. Pick cheapest weighted price per card (weights only affect this step)
          2. Shipping gate: if a shipping vendor's total savings < its flat fee, reassign
          3. Vendor elimination: greedily remove the cheapest-to-eliminate vendor (each card
             moves to its cheapest remaining alternative) until elimination cost exceeds budget
          4. Min-cards hard filter: vendors below the threshold are eliminated (no budget check)

        Returns:
            Dict with best_prices, buy_lists, summary, not_found
        """
        weights = vendor_weights or {}

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

        best_prices: Dict = {}
        card_prices: Dict[str, List[CardPrice]] = {}

        # Group prices by card
        for price in all_prices:
            card_prices.setdefault(price.original_query, []).append(price)

        # Step 1: pick cheapest weighted price per card
        # Weight biases the selection; actual (unweighted) price is stored.
        # Pinned printings restrict candidates to matching set+CN+foil.
        for card in parsed_cards:
            card_name = card.name
            if card_name in card_prices:
                found_prices = [p for p in card_prices[card_name] if p.found]
                pin = (pinned_printings or {}).get(card_name)
                if pin and found_prices:
                    pinned = [p for p in found_prices if self._matches_pin(p, pin)]
                    if pinned:
                        found_prices = pinned
                if found_prices:
                    best = min(found_prices, key=lambda p: p.price * weights.get(p.website, 1.0))
                    best_prices[card_name] = self._make_best_price_entry(best, card.quantity)

        # Step 2: shipping gate — reassign if total effective savings < flat shipping fee
        if vendor_shipping_costs:
            best_prices = self._apply_shipping_costs(
                best_prices, vendor_shipping_costs, card_prices, selected_vendors, weights,
                pinned_printings,
            )

        # Step 3: vendor elimination — greedily drop cheapest-to-eliminate vendor within budget
        if consolidation_budget and consolidation_budget > 0:
            best_prices = self._apply_vendor_elimination(
                best_prices, card_prices, consolidation_budget, weights,
                pinned_printings,
            )

        # Step 4: min-cards hard filter
        if min_cards_per_vendor and min_cards_per_vendor > 1:
            best_prices = self._apply_min_cards_filter(
                best_prices, card_prices, selected_vendors, min_cards_per_vendor, weights,
                pinned_printings,
            )

        # Build buy lists per vendor
        buy_lists = self._build_buy_lists(best_prices)

        # Calculate summary (with shipping costs added to totals)
        summary = self._calculate_summary(buy_lists, vendor_shipping_costs)

        # Find cards not found in selected vendors
        not_found = [
            card.name for card in parsed_cards
            if card.name not in best_prices
        ]

        # Warnings
        warnings = []

        # Warn when quantity_available < quantity_needed
        for card_name, info in best_prices.items():
            qty_needed = info["quantity_needed"]
            qty_available = info["quantity_available"]
            if qty_available > 0 and qty_available < qty_needed:
                warnings.append(
                    f"{card_name}: need {qty_needed} but {info['website']} only has {qty_available} in stock"
                )

        # Warn when a card is only available at a shipping vendor
        for vendor in summary:
            shipping = (vendor_shipping_costs or {}).get(vendor, 0.0)
            if shipping > 0:
                cards_at_vendor = buy_lists.get(vendor, [])
                card_total = sum(i["price_per_unit"] * i["quantity"] for i in cards_at_vendor)
                if card_total < shipping:
                    card_names = ", ".join(i["card"] for i in cards_at_vendor)
                    warnings.append(
                        f"{card_names} only found at {vendor} (${shipping:.0f} shipping on ${card_total:.2f} of cards)"
                    )

        # Build card_vendor_prices: {card_name: {vendor: [CardPrice, ...]}}
        # for the printing picker UI
        card_vendor_prices: Dict[str, Dict[str, List[CardPrice]]] = {}
        for card_name, prices_list in card_prices.items():
            vendor_map: Dict[str, List[CardPrice]] = {}
            for p in prices_list:
                if p.found:
                    vendor_map.setdefault(p.website, []).append(p)
            if vendor_map:
                card_vendor_prices[card_name] = vendor_map

        return {
            "best_prices": best_prices,
            "buy_lists": buy_lists,
            "summary": summary,
            "not_found": not_found,
            "all_prices": all_prices,
            "warnings": warnings,
            "card_vendor_prices": card_vendor_prices,
        }

    def _apply_vendor_elimination(
        self,
        best_prices: Dict,
        card_prices: Dict[str, List[CardPrice]],
        budget: float,
        vendor_weights: Dict[str, float] = None,
        pinned_printings: Optional[Dict[str, Dict]] = None,
    ) -> Dict:
        """
        Greedy vendor elimination: repeatedly remove the cheapest-to-eliminate vendor
        (measured by total extra *effective* cost when each of its cards moves to its
        cheapest remaining alternative). Each card can land at a different vendor.

        Uses weighted effective prices (raw_price * weight) consistently so that a
        preferred store is harder to eliminate and its alternatives are chosen the
        same way as Step 1. Raw prices are stored for display; weights only affect
        which vendor wins comparisons.

        Convergent: only removes vendors, never adds. At most M−1 iterations.
        """
        weights = vendor_weights or {}

        # Track which vendors are still active (have at least one card assigned)
        active_vendors: set = {info["website"] for info in best_prices.values()}

        while True:
            # Rebuild current vendor → [card_name] assignments
            vendor_cards: Dict[str, List[str]] = {}
            for card_name, info in best_prices.items():
                vendor_cards.setdefault(info["website"], []).append(card_name)

            # Compute elimination cost for each active vendor
            elimination_costs: Dict[str, float] = {}
            card_alts_cache: Dict[str, Dict[str, CardPrice]] = {}  # vendor → {card → best_alt}

            for vendor in list(active_vendors):
                assigned = vendor_cards.get(vendor, [])
                if not assigned:
                    active_vendors.discard(vendor)
                    continue

                remaining = active_vendors - {vendor}
                total_extra = 0.0
                all_have_alt = True
                alts_for_vendor: Dict[str, CardPrice] = {}

                for card_name in assigned:
                    pin = (pinned_printings or {}).get(card_name)
                    alts = [
                        p for p in card_prices.get(card_name, [])
                        if p.found and p.website in remaining
                        and self._matches_pin(p, pin)
                    ]
                    if not alts:
                        all_have_alt = False
                        break
                    # Pick best alternative by weighted effective price
                    best_alt = min(alts, key=lambda p: p.price * weights.get(p.website, 1.0))
                    # Extra cost in weighted terms: moving away from current (weighted) price
                    current_eff = best_prices[card_name]["best_price"] * weights.get(vendor, 1.0)
                    alt_eff = best_alt.price * weights.get(best_alt.website, 1.0)
                    total_extra += alt_eff - current_eff
                    alts_for_vendor[card_name] = best_alt

                if all_have_alt:
                    elimination_costs[vendor] = total_extra
                    card_alts_cache[vendor] = alts_for_vendor

            if not elimination_costs:
                break  # no vendor is eliminable (cards with no alternative)

            # Pick the cheapest vendor to eliminate
            cheapest = min(elimination_costs, key=lambda v: elimination_costs[v])

            if elimination_costs[cheapest] > budget:
                break  # cheapest elimination still exceeds budget → done

            # Eliminate: reassign each card to its cheapest weighted alternative
            print(
                f"Elimination: removing {cheapest} "
                f"({len(vendor_cards[cheapest])} card(s), weighted extra: ${elimination_costs[cheapest]:.2f})"
            )
            for card_name, alt in card_alts_cache[cheapest].items():
                best_prices[card_name] = self._make_best_price_entry(
                    alt, best_prices[card_name]["quantity_needed"]
                )
            active_vendors.discard(cheapest)

        return best_prices

    def _apply_min_cards_filter(
        self,
        best_prices: Dict,
        card_prices: Dict[str, List[CardPrice]],
        selected_vendors: List[str],
        min_cards: int,
        vendor_weights: Dict[str, float] = None,
        pinned_printings: Optional[Dict[str, Dict]] = None,
    ) -> Dict:
        """
        Hard filter: vendors below min_cards have their cards moved to the cheapest
        available alternative. No budget check.

        Loops until no vendor is below threshold (handles cascading redistributions
        where eliminating vendor A causes vendor B to fall below min_cards).
        Capped at 20 iterations to prevent infinite loops.
        """
        w = vendor_weights or {}
        max_iterations = 20

        for iteration in range(max_iterations):
            # Rebuild assignments from current best_prices
            vendor_cards: Dict[str, List[str]] = {}
            for card_name, info in best_prices.items():
                vendor_cards.setdefault(info["website"], []).append(card_name)

            # Find smallest vendor below threshold
            violators = [
                (vendor, cards_list)
                for vendor, cards_list in vendor_cards.items()
                if len(cards_list) < min_cards
            ]
            if not violators:
                break  # all vendors at or above threshold

            # Eliminate smallest violator first
            violators.sort(key=lambda vc: len(vc[1]))
            vendor, current_cards = violators[0]

            active_vendors = set(vendor_cards.keys()) - {vendor}
            print(
                f"Min-cards: {vendor} has {len(current_cards)} card(s) "
                f"(min {min_cards}) — eliminating"
            )

            all_moved = True
            for card_name in current_cards:
                pin = (pinned_printings or {}).get(card_name)
                alts = [
                    p for p in card_prices.get(card_name, [])
                    if p.found and p.website in active_vendors
                    and self._matches_pin(p, pin)
                ]
                if alts:
                    best_alt = min(alts, key=lambda p: p.price * w.get(p.website, 1.0))
                    best_prices[card_name] = self._make_best_price_entry(
                        best_alt, best_prices[card_name]["quantity_needed"]
                    )
                else:
                    # No alternative — card stays, vendor can't be fully eliminated
                    all_moved = False

            if not all_moved:
                break  # can't eliminate this vendor, stop to avoid infinite loop

        return best_prices

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
                "total_price": details["best_price"] * details["quantity_needed"],
                "set_code": details.get("set_code"),
                "collector_number": details.get("collector_number"),
                "foil": details.get("foil", False),
            })

        return buy_lists

    def _calculate_summary(self, buy_lists: Dict, vendor_shipping_costs: Dict[str, float] = None) -> Dict:
        """Calculate summary statistics per vendor, including flat shipping costs."""
        summary = {}

        for vendor, items in buy_lists.items():
            total_cards = sum(item["quantity"] for item in items)
            total_price = sum(item["total_price"] for item in items)
            shipping = (vendor_shipping_costs or {}).get(vendor, 0.0)

            summary[vendor] = {
                "total_cards": total_cards,
                "total_price": round(total_price, 2),
                "shipping_cost": shipping,
                "effective_total": round(total_price + shipping, 2),
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
