import time
import re
from typing import List
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from base_scraper import BaseScraper, Card, CardPrice
from scraper_utils import safe_click, wait_and_click, remove_overlays


class FaceToFaceGamesScraper(BaseScraper):
    """Scraper for Face to Face Games website"""

    @property
    def website_name(self) -> str:
        return "Face to Face Games"

    @property
    def website_url(self) -> str:
        return "https://facetofacegames.com/pages/deck-builder"

    def _save_debug_screenshot(self, filename="f2f_debug.png"):
        """Save a screenshot for debugging"""
        try:
            self.driver.save_screenshot(filename)
            print(f"Debug screenshot saved: {filename}")
        except Exception as e:
            print(f"Could not save screenshot: {e}")

    def scrape(self, cards: List[Card]) -> List[CardPrice]:
        """Scrape prices from Face to Face Games"""
        prices = []

        try:
            self.driver.get(self.website_url)
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

            # Create a mapping of found cards
            found_cards = {}

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
                        print(f"  -> Could not expand group {idx + 1}: {e}")

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

                    best_price = float("inf")
                    best_quantity = 0

                    # Look through each card product variant
                    for wrapper_idx, wrapper in enumerate(card_wrappers):
                        try:
                            # Get all variant options (NM, PL, HP conditions)
                            variant_divs = wrapper.find_elements(
                                By.CSS_SELECTOR, "div.f2f-featured-variant"
                            )

                            for variant_idx, variant in enumerate(variant_divs):
                                try:
                                    # Extract price - need to get the span with x-text, not the $ symbol
                                    # The structure is: <span class="price-item"><span>$</span><span x-text="...">PRICE</span></span>
                                    price_text = None

                                    try:
                                        # Get the price container
                                        price_container = variant.find_element(By.CSS_SELECTOR, "span.price-item")

                                        # Get all spans inside - the second one should have the price
                                        price_spans = price_container.find_elements(By.TAG_NAME, "span")

                                        # Try to find a span with actual numeric content
                                        for span in price_spans:
                                            text = span.text.strip()
                                            # Look for spans that have numbers (not just $)
                                            if text and text != '$' and any(c.isdigit() for c in text):
                                                price_text = text
                                                break

                                            # If .text is empty, try innerHTML (for Alpine.js x-text bindings that haven't rendered yet)
                                            if not text or text == '$':
                                                inner_html = span.get_attribute('innerHTML')
                                                if inner_html and inner_html != '$' and any(c.isdigit() for c in inner_html):
                                                    price_text = inner_html.strip()
                                                    break

                                        # If still no price, try getting the full text and removing $
                                        if not price_text:
                                            full_text = price_container.text.strip()
                                            if full_text and full_text != '$':
                                                price_text = full_text.replace('$', '').strip()
                                    except Exception:
                                        continue

                                    if not price_text or price_text == '$':
                                        continue

                                    price = self._parse_price(price_text)

                                    # Extract quantity available
                                    quantity_elem = variant.find_element(
                                        By.CSS_SELECTOR, "span.f2f-fv-title-q"
                                    )
                                    quantity_text = quantity_elem.text.strip()

                                    # If .text is empty, try innerHTML (same Alpine.js issue)
                                    # Format may be: (<span x-text="...">8</span>) so extract the number from inside the span
                                    if not quantity_text:
                                        inner_html = quantity_elem.get_attribute('innerHTML').strip()
                                        # Try to extract number from nested span: (<span ...>NUMBER</span>)
                                        nested_match = re.search(r'<span[^>]*>(\d+)</span>', inner_html)
                                        if nested_match:
                                            quantity_text = f"({nested_match.group(1)})"
                                        else:
                                            quantity_text = inner_html

                                    # Format is like "(5)" so extract the number
                                    quantity_match = re.search(r'\((\d+)\)', quantity_text)
                                    quantity = int(quantity_match.group(1)) if quantity_match else 0

                                    # Keep track of best price
                                    if price < best_price and quantity > 0:
                                        best_price = price
                                        best_quantity = quantity

                                except Exception:
                                    # Variant might be out of stock or have parsing issues
                                    continue

                        except Exception:
                            continue

                    # Add the best price found for this card
                    if best_price != float("inf"):
                        found_cards[card_name.lower()] = CardPrice(
                            card_name=card_name,
                            original_query=card_name,
                            price=best_price,
                            website=self.website_name,
                            found=True,
                            quantity_available=best_quantity,
                        )

                except Exception:
                    continue

            # Match found cards with requested cards
            for card in cards:
                card_key = card.name.lower()
                if card_key in found_cards:
                    # Create a copy with correct original_query (the user's requested card name)
                    price_info = found_cards[card_key]
                    price_copy = CardPrice(
                        card_name=price_info.card_name,
                        original_query=card.name,  # Use original requested name
                        price=price_info.price,
                        website=price_info.website,
                        found=True,
                        quantity_available=price_info.quantity_available,
                    )
                    prices.append(price_copy)
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
