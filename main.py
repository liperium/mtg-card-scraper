import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from dataclasses import dataclass
from typing import List, Dict, Optional
import pandas as pd


@dataclass
class Card:
    """Represents a MTG card"""

    quantity: int
    name: str
    set_code: Optional[str] = None
    collector_number: Optional[str] = None


@dataclass
class CardPrice:
    """Represents a card price from a website"""

    card_name: str
    original_query: str
    price: float
    website: str
    found: bool
    quantity_available: int = 0


class MTGPriceScraper:
    def __init__(self, headless: bool = False):
        """Initialize the scraper with Chrome options"""
        self.options = webdriver.ChromeOptions()
        if headless:
            self.options.add_argument("--headless")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.driver = None

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

    def scrape_cryptmtg(self, cards: List[Card]) -> List[CardPrice]:
        """Scrape prices from CryptMTG"""
        url = "https://cryptmtg.com/pages/deck-building"
        prices = []

        try:
            self.driver.get(url)
            time.sleep(1)  # Wait for initial load

            # Prepare card list for submission (without set info)
            card_text = "\n".join([f"{card.quantity} {card.name}" for card in cards])

            # Find and fill textarea
            textarea = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'textarea[data-testid="submission-textarea"]')
                )
            )
            textarea.clear()
            textarea.send_keys(card_text)

            # Submit decklist
            submit_button = self.driver.find_element(
                By.CSS_SELECTOR, 'button[aria-label="submit decklist"]'
            )
            submit_button.click()

            time.sleep(1)  # Wait for results

            # Parse results
            prices.extend(self._extract_prices_from_cryptmtg(cards))

        except Exception as e:
            print(f"Error scraping CryptMTG: {e}")
            # Add not found entries for all cards
            for card in cards:
                prices.append(
                    CardPrice(
                        card_name=card.name,
                        original_query=card.name,
                        price=float("inf"),
                        website="CryptMTG",
                        found=False,
                    )
                )

        return prices

    def scrape_magicartestore(self, cards: List[Card]) -> List[CardPrice]:
        """Scrape prices from MagiCarte"""
        url = "https://magicartestore.com/pages/test-deck-list"
        prices = []

        try:
            self.driver.get(url)
            time.sleep(1)  # Wait for initial load

            # Prepare card list for submission
            card_text = "\n".join([f"{card.quantity} {card.name}" for card in cards])

            # Find and fill textarea
            textarea = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'textarea[data-testid="submission-textarea"]')
                )
            )
            textarea.clear()
            textarea.send_keys(card_text)

            # Submit decklist
            submit_button = self.driver.find_element(
                By.CSS_SELECTOR, 'button[aria-label="submit decklist"]'
            )
            submit_button.click()

            time.sleep(1)  # Wait for results

            # Parse results
            prices.extend(self._extract_prices_from_magicartestore(cards))

        except Exception as e:
            print(f"Error scraping MagiCarte: {e}")
            # Add not found entries for all cards
            for card in cards:
                prices.append(
                    CardPrice(
                        card_name=card.name,
                        original_query=card.name,
                        price=float("inf"),
                        website="MagiCarte",
                        found=False,
                    )
                )

        return prices

    def _extract_prices_from_cryptmtg(self, cards: List[Card]) -> List[CardPrice]:
        """Extract prices from CryptMTG results page"""
        prices = []

        try:
            # Wait for results container
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div[data-testid="addedList-list"]')
                )
            )

            # Get all card items
            card_items = self.driver.find_elements(
                By.CSS_SELECTOR, "div.addedList-item"
            )

            # Create a mapping of found cards
            found_cards = {}

            for item in card_items:
                try:
                    title_elem = item.find_element(By.CSS_SELECTOR, "p.item-title")
                    price_elem = item.find_element(By.CSS_SELECTOR, "p.item-price")
                    quantity_elem = item.find_element(
                        By.CSS_SELECTOR, "div.item-quantity"
                    )

                    # Extract card name from title (remove set and condition info)
                    full_title = title_elem.get_attribute("title") or title_elem.text
                    card_name = self._extract_card_name_from_title(full_title)

                    # Extract price (remove currency)
                    price_text = price_elem.get_attribute("title") or price_elem.text
                    price = self._parse_price(price_text)

                    # Extract available quantity
                    quantity_title = quantity_elem.get_attribute("title") or ""
                    available = self._parse_quantity(quantity_title)

                    found_cards[card_name.lower()] = CardPrice(
                        card_name=card_name,
                        original_query=card_name,
                        price=price,
                        website="CryptMTG",
                        found=True,
                        quantity_available=available,
                    )

                except Exception as e:
                    print(f"Error parsing card item: {e}")

            # Match found cards with requested cards
            for card in cards:
                card_key = card.name.lower()
                if card_key in found_cards:
                    prices.append(found_cards[card_key])
                else:
                    # Check partial matches
                    found = False
                    for key, price_info in found_cards.items():
                        if card_key in key or key in card_key:
                            price_copy = CardPrice(
                                card_name=price_info.card_name,
                                original_query=card.name,
                                price=price_info.price,
                                website=price_info.website,
                                found=True,
                                quantity_available=price_info.quantity_available,
                            )
                            prices.append(price_copy)
                            found = True
                            break

                    if not found:
                        prices.append(
                            CardPrice(
                                card_name=card.name,
                                original_query=card.name,
                                price=float("inf"),
                                website="CryptMTG",
                                found=False,
                            )
                        )

        except Exception as e:
            print(f"Error extracting prices from CryptMTG: {e}")

        return prices

    def _extract_prices_from_magicartestore(self, cards: List[Card]) -> List[CardPrice]:
        """Extract prices from MagiCarte results page"""
        prices = []

        try:
            # Wait for results container
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div[data-testid="addedList-list"]')
                )
            )

            # Get all card items
            card_items = self.driver.find_elements(
                By.CSS_SELECTOR, "div.addedList-item"
            )

            # Create a mapping of found cards
            found_cards = {}

            for item in card_items:
                try:
                    title_elem = item.find_element(By.CSS_SELECTOR, "p.item-title")
                    price_elem = item.find_element(By.CSS_SELECTOR, "p.item-price")
                    quantity_elem = item.find_element(
                        By.CSS_SELECTOR, "div.item-quantity"
                    )

                    # Extract card name from title
                    full_title = title_elem.get_attribute("title") or title_elem.text
                    card_name = self._extract_card_name_from_title(full_title)

                    # Extract price
                    price_text = price_elem.get_attribute("title") or price_elem.text
                    price = self._parse_price(price_text)

                    # Extract available quantity
                    quantity_title = quantity_elem.get_attribute("title") or ""
                    available = self._parse_quantity(quantity_title)

                    found_cards[card_name.lower()] = CardPrice(
                        card_name=card_name,
                        original_query=card_name,
                        price=price,
                        website="MagiCarte",
                        found=True,
                        quantity_available=available,
                    )

                except Exception as e:
                    print(f"Error parsing card item: {e}")

            # Match found cards with requested cards
            for card in cards:
                card_key = card.name.lower()
                if card_key in found_cards:
                    prices.append(found_cards[card_key])
                else:
                    # Check partial matches
                    found = False
                    for key, price_info in found_cards.items():
                        if card_key in key or key in card_key:
                            price_copy = CardPrice(
                                card_name=price_info.card_name,
                                original_query=card.name,
                                price=price_info.price,
                                website=price_info.website,
                                found=True,
                                quantity_available=price_info.quantity_available,
                            )
                            prices.append(price_copy)
                            found = True
                            break

                    if not found:
                        prices.append(
                            CardPrice(
                                card_name=card.name,
                                original_query=card.name,
                                price=float("inf"),
                                website="MagiCarte",
                                found=False,
                            )
                        )

        except Exception as e:
            print(f"Error extracting prices from MagiCarte: {e}")

        return prices

    def _extract_card_name_from_title(self, title: str) -> str:
        """Extract card name from full title (remove set and condition)"""
        # Remove condition (Near Mint, etc.)
        title = re.sub(
            r"\s*(Near Mint|Lightly Played|Moderately Played|Heavily Played|Damaged).*$",
            "",
            title,
        )
        # Remove set info in brackets
        title = re.sub(r"\s*\[.*?\]", "", title)
        return title.strip()

    def _parse_price(self, price_text: str) -> float:
        """Parse price from text"""
        # Remove currency symbols and text
        price_text = re.sub(r"[^\d.,]", "", price_text)
        price_text = price_text.replace(",", "")
        try:
            return float(price_text)
        except:
            return float("inf")

    def _parse_quantity(self, quantity_text: str) -> int:
        """Parse available quantity from text like '1 / 3'"""
        match = re.search(r"/\s*(\d+)", quantity_text)
        if match:
            return int(match.group(1))
        return 0

    def analyze_results(self, all_prices: List[CardPrice], cards: List[Card]) -> Dict:
        """Analyze results and create buy lists"""
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

    def scrape_all(self, card_list: str) -> Dict:
        """Main method to scrape all websites"""
        try:
            # Initialize driver
            self.driver = webdriver.Chrome(options=self.options)

            # Parse cards
            cards = self.parse_moxfield_format(card_list)
            print(f"Parsed {len(cards)} cards from input")

            all_prices = []

            # Scrape each website
            print("Scraping CryptMTG...")
            cryptmtg_prices = self.scrape_cryptmtg(cards)
            all_prices.extend(cryptmtg_prices)

            print("Scraping MagiCarte...")
            magicartestore_prices = self.scrape_magicartestore(cards)
            all_prices.extend(magicartestore_prices)

            # Analyze results
            results = self.analyze_results(all_prices, cards)

            return results

        finally:
            if self.driver:
                self.driver.quit()

    def print_results(self, results: Dict):
        """Print formatted results"""
        print("\n" + "=" * 60)
        print("MTG CARD PRICE COMPARISON RESULTS")
        print("=" * 60)

        print("\n📊 BEST PRICES BY CARD:")
        print("-" * 40)
        for card, info in results["best_prices"].items():
            print(f"• {card}")
            print(f"  Quantity needed: {info['quantity_needed']}")
            print(f"  Best price: ${info['best_price']:.2f} @ {info['website']}")
            print(f"  Available: {info['quantity_available']}")

        print("\n🛒 RECOMMENDED BUY LISTS:")
        print("-" * 40)
        for website, cards_list in results["buy_lists"].items():
            print(f"\n{website}:")
            total = 0
            for item in cards_list:
                item_total = item["total_price"]
                total += item_total
                print(
                    f"  • {item['quantity']}x {item['card']} @ ${item['price_per_unit']:.2f} = ${item_total:.2f}"
                )
            print(f"  TOTAL: ${total:.2f}")

        if results["not_found"]:
            print("\n❌ CARDS NOT FOUND:")
            print("-" * 40)
            for card in results["not_found"]:
                print(f"  • {card}")

        print("\n💰 SUMMARY:")
        print("-" * 40)
        for website, summary in results["summary"].items():
            print(
                f"{website}: {summary['total_cards']} cards = ${summary['total_price']:.2f}"
            )

        if results["summary"]:
            grand_total = sum(s["total_price"] for s in results["summary"].values())
            print(f"\nGRAND TOTAL (if buying optimally): ${grand_total:.2f}")


# Example usage
if __name__ == "__main__":
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

    # Initialize scraper
    scraper = MTGPriceScraper(headless=False)  # Set to True for headless mode

    try:
        # Scrape all websites
        results = scraper.scrape_all(card_list)

        # Print results
        scraper.print_results(results)

        # Optional: Save to CSV
        if results["best_prices"]:
            df = pd.DataFrame.from_dict(results["best_prices"], orient="index")
            df.index.name = "card_name"
            df.reset_index(inplace=True)
            df = df.sort_values(by=["website", "card_name"])
            df.to_csv("mtg_best_prices.csv", index=False, quoting=2)
            print("\n✅ Results saved to mtg_best_prices.csv")

    except Exception as e:
        print(f"Error during scraping: {e}")
