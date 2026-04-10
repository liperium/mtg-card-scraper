import time
import re
from typing import List, Dict
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from base_vendor import BaseVendor, Card, CardPrice
from scraper_utils import remove_overlays


class GodsArenaVendor(BaseVendor):
    """Vendor implementation for L'Arène des Dieux (Gods Arena) - Crystal Commerce platform"""

    @property
    def name(self) -> str:
        return "Arène des Dieux"

    @property
    def deck_builder_url(self) -> str:
        return "https://www.godsarena.com/products/multi_search"

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
        """Scrape prices from L'Arène des Dieux"""
        prices = []

        try:
            self.log(f"Loading {self.deck_builder_url}...")
            self.driver.get(self.deck_builder_url)
            time.sleep(2)
            remove_overlays(self.driver)

            card_text = "\n".join([f"{card.quantity} {card.name}" for card in cards])

            try:
                textarea = WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "textarea#multisearch_query")
                    )
                )
                self.log(f"Textarea found, entering {len(cards)} cards...")
                textarea.clear()
                textarea.send_keys(card_text)
                time.sleep(0.5)
            except Exception as textarea_error:
                self.log(f"Error finding/filling textarea: {textarea_error}")
                raise

            self.log("Submitting decklist...")
            submit_btn = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "input[name='submit']")
                )
            )
            self.driver.execute_script("arguments[0].click();", submit_btn)

            time.sleep(3)  # Wait for server-rendered results

            self.log("Parsing results...")
            prices.extend(self._extract_prices(cards))

        except Exception as e:
            self.log(f"Error scraping: {e}")
            import traceback
            traceback.print_exc()
            prices.extend(self._create_not_found_prices(cards))

        return prices

    def _extract_prices(self, cards: List[Card]) -> List[CardPrice]:
        """Extract prices from Gods Arena results page.

        The site returns multiple li.product per card (one per set printing).
        We collect all in-stock variants, group by card name, and keep the cheapest.
        """
        prices = []

        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.product"))
            )

            # Collect cheapest in-stock price per card name
            best: Dict[str, dict] = {}  # lowercased name → {price, qty, display_name}

            in_stock_rows = self.driver.find_elements(
                By.CSS_SELECTOR, "div.variant-row.in-stock"
            )
            for row in in_stock_rows:
                try:
                    forms = row.find_elements(By.CSS_SELECTOR, "form.add-to-cart-form")
                    if not forms:
                        continue
                    form = forms[0]
                    card_name = (form.get_attribute("data-name") or "").strip()
                    price_str = form.get_attribute("data-price") or ""
                    price = self._parse_price(price_str)

                    qty_inputs = row.find_elements(By.CSS_SELECTOR, "input.qty")
                    qty = int(qty_inputs[0].get_attribute("max") or 0) if qty_inputs else 0

                    key = card_name.lower()
                    if key and (key not in best or price < best[key]["price"]):
                        best[key] = {"price": price, "qty": qty, "display_name": card_name}
                except Exception as e:
                    self.log(f"Error parsing variant row: {e}")

            self.log(f"Found {len(best)} unique cards in stock")

            # Match queried cards to found results
            for card in cards:
                card_key = card.name.lower()
                if card_key in best:
                    b = best[card_key]
                    prices.append(CardPrice(
                        card_name=b["display_name"],
                        original_query=card.name,
                        price=b["price"],
                        website=self.name,
                        found=True,
                        quantity_available=b["qty"],
                    ))
                else:
                    # Fallback: partial match
                    found = False
                    for key, b in best.items():
                        if card_key in key or key in card_key:
                            prices.append(CardPrice(
                                card_name=b["display_name"],
                                original_query=card.name,
                                price=b["price"],
                                website=self.name,
                                found=True,
                                quantity_available=b["qty"],
                            ))
                            found = True
                            break
                    if not found:
                        prices.append(self._create_not_found_price(card))

        except Exception as e:
            self.log(f"Error extracting prices: {e}")
            prices.extend(self._create_not_found_prices(cards))

        return prices

    def _parse_price(self, price_text: str) -> float:
        """Parse price from text like 'CAD$ 33.24' → 33.24"""
        price_text = re.sub(r"[^\d.]", "", price_text)
        try:
            return float(price_text)
        except Exception:
            return float("inf")
