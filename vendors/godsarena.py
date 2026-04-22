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
        Returns all in-stock variants so the optimizer and printing picker can
        work with the full set.
        """
        prices = []

        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.product"))
            )

            # Collect all in-stock printings per card name
            all_printings: Dict[str, list[CardPrice]] = {}
            # Crystal Commerce HTML duplicates the same variant-row across multiple DOM containers
            seen_variants: set = set()

            in_stock_rows = self.driver.find_elements(
                By.CSS_SELECTOR, "div.variant-row.in-stock"
            )
            for row in in_stock_rows:
                try:
                    forms = row.find_elements(By.CSS_SELECTOR, "form.add-to-cart-form")
                    if not forms:
                        continue
                    form = forms[0]
                    full_name = (form.get_attribute("data-name") or "").strip()
                    price_str = form.get_attribute("data-price") or ""

                    # Skip duplicates (same DOM variant appears multiple times on the page)
                    dedup_key = (full_name, price_str)
                    if dedup_key in seen_variants:
                        continue
                    seen_variants.add(dedup_key)

                    price = self._parse_price(price_str)

                    qty_inputs = row.find_elements(By.CSS_SELECTOR, "input.qty")
                    qty = int(qty_inputs[0].get_attribute("max") or 0) if qty_inputs else 0

                    # Extract set/foil from the variant name
                    # Crystal Commerce data-name often includes set info
                    card_name = self._extract_card_name(full_name)
                    set_code, collector_number, foil = self._parse_title_set_info(full_name)

                    key = card_name.lower()
                    if key:
                        cp = CardPrice(
                            card_name=card_name,
                            original_query=card_name,
                            price=price,
                            website=self.name,
                            found=True,
                            quantity_available=qty,
                            set_code=set_code,
                            collector_number=collector_number,
                            foil=foil,
                        )
                        all_printings.setdefault(key, []).append(cp)
                except Exception as e:
                    self.log(f"Error parsing variant row: {e}")

            total_variants = sum(len(v) for v in all_printings.values())
            self.log(f"Found {len(all_printings)} unique cards ({total_variants} printings) in stock")

            # Match queried cards to found results
            for card in cards:
                card_key = card.name.lower()
                matched = all_printings.get(card_key)

                if not matched:
                    for key, card_prices in all_printings.items():
                        if card_key in key or key in card_key:
                            matched = card_prices
                            break

                if matched:
                    for p in matched:
                        prices.append(CardPrice(
                            card_name=p.card_name,
                            original_query=card.name,
                            price=p.price,
                            website=p.website,
                            found=True,
                            quantity_available=p.quantity_available,
                            set_code=p.set_code,
                            collector_number=p.collector_number,
                            foil=p.foil,
                        ))
                else:
                    prices.append(self._create_not_found_price(card))

        except Exception as e:
            self.log(f"Error extracting prices: {e}")
            prices.extend(self._create_not_found_prices(cards))

        return prices

    def _extract_card_name(self, full_name: str) -> str:
        """Extract card name from Crystal Commerce data-name, removing condition/set info."""
        # Remove condition suffixes
        name = re.sub(
            r"\s*[-–]\s*(Near Mint|Lightly Played|Moderately Played|Heavily Played|Damaged).*$",
            "", full_name, flags=re.IGNORECASE
        )
        # Remove set info in brackets/parens
        name = re.sub(r"\s*[\[\(].*?[\]\)]", "", name)
        return name.strip()

    def _parse_price(self, price_text: str) -> float:
        """Parse price from text like 'CAD$ 33.24' → 33.24"""
        price_text = re.sub(r"[^\d.]", "", price_text)
        try:
            return float(price_text)
        except Exception:
            return float("inf")
