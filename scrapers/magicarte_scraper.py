import time
import re
from typing import List
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from base_scraper import BaseScraper, Card, CardPrice
from scraper_utils import safe_click, wait_and_click, remove_overlays


class MagiCarteScraper(BaseScraper):
    """Scraper for MagiCarte Store website"""

    @property
    def website_name(self) -> str:
        return "MagiCarte"

    @property
    def website_url(self) -> str:
        return "https://magicartestore.com/pages/test-deck-list"

    def scrape(self, cards: List[Card]) -> List[CardPrice]:
        """Scrape prices from MagiCarte"""
        prices = []

        try:
            self.driver.get(self.website_url)
            time.sleep(2)  # Wait for initial load

            # Remove any overlays that might block clicks
            remove_overlays(self.driver)

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

            # Submit decklist using safe click
            submit_success = wait_and_click(
                self.driver,
                'button[aria-label="submit decklist"]',
                use_js=True  # Use JS click to avoid interception
            )

            if not submit_success:
                print(f"Warning: Could not click submit button for {self.website_name}")
                # Try alternative: press Enter on textarea
                from selenium.webdriver.common.keys import Keys
                textarea.send_keys(Keys.RETURN)

            time.sleep(2)  # Wait for results

            # Parse results
            prices.extend(self._extract_prices(cards))

        except Exception as e:
            print(f"Error scraping {self.website_name}: {e}")
            # Add not found entries for all cards
            prices.extend(self._create_not_found_prices(cards))

        return prices

    def _extract_prices(self, cards: List[Card]) -> List[CardPrice]:
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
                        website=self.website_name,
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
                        prices.append(self._create_not_found_price(card))

        except Exception as e:
            print(f"Error extracting prices from {self.website_name}: {e}")

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
