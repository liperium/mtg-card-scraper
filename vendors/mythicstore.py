import time
import re
from typing import List
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from base_vendor import BaseVendor, Card, CardPrice
from scraper_utils import wait_and_click, remove_overlays


class MythicStoreVendor(BaseVendor):
    """Vendor implementation for The Mythic Store"""

    @property
    def name(self) -> str:
        return "Mythic Store"

    @property
    def deck_builder_url(self) -> str:
        return "https://themythicstore.com/pages/multi-card-search-page"

    @property
    def supports_bulk_add(self) -> bool:
        return True

    @property
    def shipping_cost(self) -> float:
        return 10.0

    @property
    def fulfillment_label(self) -> str:
        return "Shipping +$10"

    def scrape(self, cards: List[Card]) -> List[CardPrice]:
        """Scrape prices from The Mythic Store"""
        prices = []

        try:
            self.log(f"Loading {self.deck_builder_url}...")
            self.driver.get(self.deck_builder_url)
            time.sleep(3)  # Wait for initial load

            self.log("Page loaded, looking for textarea...")
            remove_overlays(self.driver)

            card_text = "\n".join([f"{card.quantity} {card.name}" for card in cards])

            try:
                textarea = WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'textarea[data-testid="submission-textarea"]')
                    )
                )
                self.log(f"Textarea found, entering {len(cards)} cards...")
                textarea.clear()
                time.sleep(0.5)
                textarea.send_keys(card_text)
                time.sleep(1)
            except Exception as textarea_error:
                self.log(f"Error finding/filling textarea: {textarea_error}")
                raise

            self.log("Submitting decklist...")
            submit_success = wait_and_click(
                self.driver,
                'button[aria-label="submit decklist"]',
                use_js=True,
                timeout=15
            )

            if not submit_success:
                self.log("Warning: Could not click submit button, trying Enter key...")
                from selenium.webdriver.common.keys import Keys
                textarea.send_keys(Keys.RETURN)

            time.sleep(3)  # Wait for results

            self.log("Parsing results...")
            prices.extend(self._extract_prices(cards))

        except Exception as e:
            self.log(f"Error scraping: {e}")
            import traceback
            traceback.print_exc()
            prices.extend(self._create_not_found_prices(cards))

        return prices

    def _extract_prices(self, cards: List[Card]) -> List[CardPrice]:
        """Extract prices from Mythic Store results page"""
        prices = []

        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div[data-testid="addedList-list"]')
                )
            )

            card_items = self.driver.find_elements(
                By.CSS_SELECTOR, "div.addedList-item"
            )

            found_cards = {}

            for item in card_items:
                try:
                    title_elem = item.find_element(By.CSS_SELECTOR, "p.item-title")
                    price_elem = item.find_element(By.CSS_SELECTOR, "p.item-price")
                    quantity_elem = item.find_element(
                        By.CSS_SELECTOR, "div.item-quantity"
                    )

                    full_title = title_elem.get_attribute("title") or title_elem.text
                    card_name = self._extract_card_name_from_title(full_title)

                    price_text = price_elem.get_attribute("title") or price_elem.text
                    price = self._parse_price(price_text)

                    quantity_title = quantity_elem.get_attribute("title") or ""
                    available = self._parse_quantity(quantity_title)

                    found_cards[card_name.lower()] = CardPrice(
                        card_name=card_name,
                        original_query=card_name,
                        price=price,
                        website=self.name,
                        found=True,
                        quantity_available=available,
                    )

                except Exception as e:
                    self.log(f"Error parsing card item: {e}")

            for card in cards:
                card_key = card.name.lower()
                if card_key in found_cards:
                    p = found_cards[card_key]
                    prices.append(CardPrice(
                        card_name=p.card_name,
                        original_query=card.name,
                        price=p.price,
                        website=p.website,
                        found=True,
                        quantity_available=p.quantity_available,
                    ))
                else:
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
            self.log(f"Error extracting prices: {e}")

        return prices

    def _extract_card_name_from_title(self, title: str) -> str:
        """Extract card name from full title (remove set and condition)"""
        title = re.sub(
            r"\s*(Near Mint|Lightly Played|Moderately Played|Heavily Played|Damaged).*$",
            "",
            title,
        )
        title = re.sub(r"\s*\[.*?\]", "", title)
        return title.strip()

    def _parse_price(self, price_text: str) -> float:
        """Parse price from text"""
        price_text = re.sub(r"[^\d.,]", "", price_text)
        price_text = price_text.replace(",", "")
        try:
            return float(price_text)
        except Exception:
            return float("inf")

    def _parse_quantity(self, quantity_text: str) -> int:
        """Parse available quantity from text like '1 / 3'"""
        match = re.search(r"/\s*(\d+)", quantity_text)
        if match:
            return int(match.group(1))
        return 0
