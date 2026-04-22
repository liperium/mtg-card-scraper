import time
import re
from typing import List
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from base_vendor import BaseVendor, Card, CardPrice
from scraper_utils import wait_and_click, remove_overlays


class FaceToFaceGamesVendor(BaseVendor):
    """Vendor implementation for Face to Face Games"""

    @property
    def name(self) -> str:
        return "Face to Face Games"

    @property
    def deck_builder_url(self) -> str:
        return "https://facetofacegames.com/pages/deck-builder"

    @property
    def supports_bulk_add(self) -> bool:
        return False

    @property
    def supports_set_info(self) -> bool:
        return True

    @property
    def supports_foil(self) -> bool:
        return True

    @property
    def shipping_cost(self) -> float:
        return 10.0

    @property
    def fulfillment_label(self) -> str:
        return "Shipping +$10"

    def _save_debug_screenshot(self, filename="f2f_debug.png"):
        """Save a screenshot for debugging"""
        try:
            self.driver.save_screenshot(filename)
            self.log(f"Debug screenshot saved: {filename}")
        except Exception as e:
            self.log(f"Could not save screenshot: {e}")

    def scrape(self, cards: List[Card]) -> List[CardPrice]:
        """Scrape prices from Face to Face Games"""
        prices = []

        try:
            self.driver.get(self.deck_builder_url)
            time.sleep(2)  # Wait for initial load and Alpine.js to initialize

            # Remove any overlays that might block clicks
            remove_overlays(self.driver)

            # Prepare card list for submission (simple format)
            card_text = "\n".join([f"{card.quantity} {card.name}" for card in cards])

            # F2F uses specific textarea with class and x-model
            textarea_selectors = [
                'textarea.db-decklist-input',  # Primary selector
                'textarea#textarea_input',  # ID selector
                'textarea[x-model="qb"]',  # Alpine.js model binding
            ]

            textarea = None
            for selector in textarea_selectors:
                try:
                    textarea = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    break
                except:
                    continue

            if not textarea:
                self._save_debug_screenshot("f2f_no_textarea.png")
                raise Exception("Textarea not found")

            # Clear and enter card list
            # Use JavaScript to set the value and trigger Alpine.js reactivity
            self.driver.execute_script("""
                arguments[0].value = arguments[1];
                arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
            """, textarea, card_text)
            time.sleep(0.5)

            # Click the "GET MY DECK" button
            button_selectors = [
                'button.db-decklist-get',  # Primary selector
                'button.button[onclick*="getMyDeck"]',  # With onclick
                'button:contains("GET MY DECK")',  # Text content
            ]

            submit_success = False
            for selector in button_selectors:
                try:
                    if wait_and_click(self.driver, selector, timeout=5, use_js=True):
                        submit_success = True
                        break
                except:
                    continue

            if not submit_success:
                # Try to call the Alpine.js function directly
                try:
                    self.driver.execute_script("""
                        const textarea = document.querySelector('textarea.db-decklist-input');
                        const component = Alpine.$data(textarea.closest('[x-data]'));
                        if (component && component.getMyDeck) {
                            component.getMyDeck(component.qb || textarea.value);
                        }
                    """)
                    submit_success = True
                except Exception:
                    pass

            # Wait for results to actually populate
            result_loaded = False
            for wait_attempt in range(10):  # Try for up to 10 seconds
                time.sleep(1)
                try:
                    # Check if any card titles have loaded
                    title_elements = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        "div.hits-wrap-data-title span"
                    )
                    if title_elements and any(elem.text.strip() for elem in title_elements):
                        result_loaded = True
                        break
                except:
                    pass

            if not result_loaded:
                self._save_debug_screenshot("f2f_no_card_results.png")

            time.sleep(1)  # Extra time for all variants to load

            # Parse results
            prices.extend(self._extract_prices(cards))

        except Exception:
            # Add not found entries for all cards
            prices.extend(self._create_not_found_prices(cards))

        return prices

    def _parse_f2f_url(self, url: str, card_name: str) -> tuple:
        """Parse (set_code, collector_number, foil) from a F2F Shopify product URL.

        URL format: /products/{card-slug}-{collector}-{set-slug}-(non-)foil
        Example: /products/sol-ring-129-bloomburrow-commander-non-foil
        """
        path = url.rstrip('/').split('/')[-1]

        # Determine foil from suffix
        if path.endswith('-non-foil'):
            foil = False
            path = path[:-9]
        elif path.endswith('-foil'):
            foil = True
            path = path[:-5]
        else:
            foil = False

        # Strip card name slug from start
        card_slug = re.sub(r'[^a-z0-9]+', '-', card_name.lower()).strip('-')
        if path.startswith(card_slug + '-'):
            remainder = path[len(card_slug) + 1:]
        else:
            remainder = path

        # remainder: "{collector_number}-{set-slug}"
        m = re.match(r'^(\d+)-(.+)$', remainder)
        if m:
            collector_number = m.group(1)
            set_slug = m.group(2)
            set_name = ' '.join(word.capitalize() for word in set_slug.split('-'))
            return set_name, collector_number, foil

        return None, None, foil

    def _extract_prices(self, cards: List[Card]) -> List[CardPrice]:
        """Extract prices from Face to Face Games results page"""
        prices = []

        try:
            # Wait for results to appear - F2F uses Alpine.js so wait for card containers
            result_selectors = [
                'div.hits-wrap',
                'div.bb-card-wrapper',
                'div.bb-products-wraper',
                'div[x-data]',  # Alpine.js components
                '.product-list',
                '.search-results'
            ]

            results_found = False
            for selector in result_selectors:
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    results_found = True
                    break
                except:
                    continue

            if not results_found:
                self._save_debug_screenshot("f2f_no_results.png")
                page_text = self.driver.find_element(By.TAG_NAME, "body").text[:500]
                if "no results" in page_text.lower() or "not found" in page_text.lower():
                    return prices
                raise Exception("Could not find any result containers")

            time.sleep(1.5)  # Additional wait for Alpine.js to fully render

            # Get all card wrapper groups (each card can have multiple variants)
            card_groups = self.driver.find_elements(
                By.CSS_SELECTOR, "div.hits-wrap"
            )

            # Create a mapping of found cards: name → list of all printings
            found_cards: dict[str, list[CardPrice]] = {}

            for idx, group in enumerate(card_groups):
                try:
                    # First, click to expand this group (products are hidden by default)
                    try:
                        expand_button = group.find_element(
                            By.CSS_SELECTOR, "div.hits-wrap-data"
                        )
                        # Use JavaScript click to avoid interception
                        self.driver.execute_script("arguments[0].click();", expand_button)

                        # The first card needs extra time for Alpine.js to populate prices via x-text bindings
                        # Subsequent cards load faster since Alpine is already initialized
                        if idx == 0:
                            time.sleep(1.0)  # Extended wait for first card
                        else:
                            time.sleep(0.3)  # Normal wait for others
                    except Exception as e:
                        self.log(f"Could not expand group {idx + 1}: {e}")

                    # Get card name from the group title
                    title_elem = group.find_element(
                        By.CSS_SELECTOR, "div.hits-wrap-data-title span"
                    )
                    card_name = title_elem.text.strip()

                    if not card_name:
                        continue

                    # Find all card variants within this group
                    card_wrappers = group.find_elements(
                        By.CSS_SELECTOR, "div.bb-card-wrapper"
                    )

                    # Collect all in-stock variants for this card
                    card_variants: list[CardPrice] = []

                    # Look through each card product variant (each wrapper = different printing)
                    for wrapper_idx, wrapper in enumerate(card_wrappers):
                        try:
                            # Extract set/foil info from Alpine.js product URL
                            wrapper_set_code = None
                            wrapper_collector = None
                            wrapper_foil = False
                            try:
                                product_url = self.driver.execute_script("""
                                    try {
                                        var d = Alpine.$data(arguments[0]);
                                        return d.url || null;
                                    } catch(e) { return null; }
                                """, wrapper)
                                if product_url:
                                    wrapper_set_code, wrapper_collector, wrapper_foil = \
                                        self._parse_f2f_url(product_url, card_name)
                            except Exception:
                                pass

                            # Get all variant options (NM, PL, HP conditions)
                            variant_divs = wrapper.find_elements(
                                By.CSS_SELECTOR, "div.f2f-featured-variant"
                            )

                            for variant_idx, variant in enumerate(variant_divs):
                                try:
                                    price_text = None

                                    try:
                                        price_container = variant.find_element(By.CSS_SELECTOR, "span.price-item")
                                        price_spans = price_container.find_elements(By.TAG_NAME, "span")

                                        for span in price_spans:
                                            text = span.text.strip()
                                            if text and text != '$' and any(c.isdigit() for c in text):
                                                price_text = text
                                                break
                                            if not text or text == '$':
                                                inner_html = span.get_attribute('innerHTML')
                                                if inner_html and inner_html != '$' and any(c.isdigit() for c in inner_html):
                                                    price_text = inner_html.strip()
                                                    break

                                        if not price_text:
                                            full_text = price_container.text.strip()
                                            if full_text and full_text != '$':
                                                price_text = full_text.replace('$', '').strip()
                                    except Exception:
                                        continue

                                    if not price_text or price_text == '$':
                                        continue

                                    price = self._parse_price(price_text)

                                    quantity_elem = variant.find_element(
                                        By.CSS_SELECTOR, "span.f2f-fv-title-q"
                                    )
                                    quantity_text = quantity_elem.text.strip()

                                    if not quantity_text:
                                        inner_html = quantity_elem.get_attribute('innerHTML').strip()
                                        nested_match = re.search(r'<span[^>]*>(\d+)</span>', inner_html)
                                        if nested_match:
                                            quantity_text = f"({nested_match.group(1)})"
                                        else:
                                            quantity_text = inner_html

                                    quantity_match = re.search(r'\((\d+)\)', quantity_text)
                                    quantity = int(quantity_match.group(1)) if quantity_match else 0

                                    if quantity > 0:
                                        card_variants.append(CardPrice(
                                            card_name=card_name,
                                            original_query=card_name,
                                            price=price,
                                            website=self.name,
                                            found=True,
                                            quantity_available=quantity,
                                            set_code=wrapper_set_code,
                                            collector_number=wrapper_collector,
                                            foil=wrapper_foil,
                                        ))

                                except Exception:
                                    continue

                        except Exception:
                            continue

                    if card_variants:
                        found_cards[card_name.lower()] = card_variants

                except Exception:
                    continue

            # Match found cards with requested cards
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

        except Exception:
            pass

        return prices

    def _parse_price(self, price_text: str) -> float:
        """Parse price from text"""
        # Remove currency symbols and text
        price_text = re.sub(r"[^\d.,]", "", price_text)
        price_text = price_text.replace(",", "")
        try:
            return float(price_text)
        except:
            return float("inf")
