import time
import re
from typing import List
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from base_vendor import BaseVendor, Card, CardPrice
from scraper_utils import wait_and_click, remove_overlays


class MagiCarteVendor(BaseVendor):
    """Vendor implementation for MagiCarte Store"""

    @property
    def name(self) -> str:
        return "MagiCarte"

    @property
    def deck_builder_url(self) -> str:
        return "https://magicartestore.com/pages/test-deck-list"

    @property
    def supports_bulk_add(self) -> bool:
        return True

    @property
    def supports_set_info(self) -> bool:
        return True

    @property
    def supports_foil(self) -> bool:
        return True

    def scrape(self, cards: List[Card]) -> List[CardPrice]:
        """Scrape prices from MagiCarte"""
        prices = []

        try:
            self.driver.get(self.deck_builder_url)
            time.sleep(2)  # Wait for initial load

            # Remove any overlays that might block clicks
            remove_overlays(self.driver)

            # Prepare card list for submission
            card_text = "\n".join([f"{card.quantity} {card.name}" for card in cards])

            # Find and fill textarea
            textarea = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'textarea[data-testid="submission-textarea"]')
                )
            )
            # Set value via JS + fire React synthetic events
            self.driver.execute_script("""
                var ta = arguments[0];
                var setter = Object.getOwnPropertyDescriptor(
                    window.HTMLTextAreaElement.prototype, 'value'
                ).set;
                setter.call(ta, arguments[1]);
                ta.dispatchEvent(new Event('input',  { bubbles: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true }));
            """, textarea, card_text)
            time.sleep(1)

            # Submit — prefer normal click; fall back to JS click, then Enter.
            submit_success = wait_and_click(
                self.driver,
                'button[aria-label="submit decklist"]',
                use_js=False,
                timeout=15
            )

            if not submit_success:
                submit_success = wait_and_click(
                    self.driver,
                    'button[aria-label="submit decklist"]',
                    use_js=True,
                    timeout=5
                )

            if not submit_success:
                self.log("Warning: Could not click submit button")
                from selenium.webdriver.common.keys import Keys
                textarea.send_keys(Keys.RETURN)

            time.sleep(2)  # Wait for results

            # Parse results
            prices.extend(self._extract_prices(cards))

        except Exception as e:
            self.log(f"Error scraping: {e}")
            # Add not found entries for all cards
            prices.extend(self._create_not_found_prices(cards))

        return prices

    def _extract_prices(self, cards: List[Card]) -> List[CardPrice]:
        """Extract all variant printings from MagiCarte results.

        For each card result, clicks the variant switcher to reveal all
        available printings, then reads every div.variant-switch-add-option.
        """
        prices = []

        try:
            WebDriverWait(self.driver, 25).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div[data-testid="addedList-list"]')
                )
            )

            found_cards: dict[str, list[CardPrice]] = {}

            # One wrapper per queried card in the results section
            wrappers = self.driver.find_elements(
                By.CSS_SELECTOR, "div.result-found-wrapper"
            )

            for wrapper in wrappers:
                try:
                    card_name_elem = wrapper.find_element(
                        By.CSS_SELECTOR, ".result-card-title"
                    )
                    card_name = card_name_elem.text.strip()
                    if not card_name:
                        continue

                    # Open the variant list for this card
                    try:
                        switch_btn = wrapper.find_element(
                            By.CSS_SELECTOR, '[data-testid="open-switch-variant-list"]'
                        )
                        self.driver.execute_script("arguments[0].click();", switch_btn)
                        time.sleep(0.5)
                    except Exception:
                        pass

                    # Read all variant options (may be in wrapper or adjacent sibling)
                    variant_elems = self.driver.find_elements(
                        By.CSS_SELECTOR, "div.variant-switch-add-option"
                    )

                    for variant in variant_elems:
                        try:
                            paras = variant.find_elements(By.TAG_NAME, "p")
                            if len(paras) < 3:
                                continue
                            full_title = paras[0].get_attribute("title") or paras[0].text
                            qty_text   = paras[1].get_attribute("title") or paras[1].text
                            price_text = paras[2].get_attribute("title") or paras[2].text

                            set_code, collector_number, foil = self._parse_title_set_info(full_title)
                            price = self._parse_price(price_text)
                            qty_match = re.search(r"(\d+)", qty_text)
                            available = int(qty_match.group(1)) if qty_match else 0

                            if available > 0:
                                found_cards.setdefault(card_name.lower(), []).append(
                                    CardPrice(
                                        card_name=card_name,
                                        original_query=card_name,
                                        price=price,
                                        website=self.name,
                                        found=True,
                                        quantity_available=available,
                                        set_code=set_code,
                                        collector_number=collector_number,
                                        foil=foil,
                                    )
                                )
                        except Exception as e:
                            self.log(f"Error parsing variant: {e}")

                except Exception as e:
                    self.log(f"Error parsing wrapper: {e}")

            # Match to requested cards
            for card in cards:
                card_key = card.name.lower()
                matched = found_cards.get(card_key)
                if not matched:
                    for key, card_prices in found_cards.items():
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
