import time
import re
from typing import List
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from base_vendor import BaseVendor, Card, CardPrice
from scraper_utils import remove_overlays

try:
    import undetected_chromedriver as uc

    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False


class ImaginaireVendor(BaseVendor):
    """Vendor implementation for Imaginaire"""

    @property
    def name(self) -> str:
        return "Imaginaire"

    @property
    def deck_builder_url(self) -> str:
        return "https://imaginaire.com/en/magic/deck-builder.html"

    @property
    def supports_bulk_add(self) -> bool:
        return True

    @property
    def shipping_cost(self) -> float:
        return 10.0

    @property
    def fulfillment_label(self) -> str:
        return "Shipping +$10"

    def _find_chrome_binary(self) -> str:
        """Locate Chrome executable, including Selenium Manager's cached Chrome for Testing."""
        import shutil, os, glob

        # System-installed Chrome
        for name in ("chrome", "chromium", "google-chrome", "chromium-browser"):
            path = shutil.which(name)
            if path:
                return str(path)

        # Common Windows install paths
        for candidate in [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]:
            if os.path.exists(candidate):
                return candidate

        # Selenium Manager cache: ~/.cache/selenium/chrome/**/chrome.exe
        selenium_cache = os.path.expanduser(r"~\.cache\selenium\chrome")
        if os.path.exists(selenium_cache):
            matches = glob.glob(
                os.path.join(selenium_cache, "**", "chrome.exe"), recursive=True
            )
            if matches:
                return str(sorted(matches)[-1])  # pick latest version

        return None

    def _create_uc_driver(self):
        """Create an undetected-chromedriver instance to bypass Cloudflare."""
        options = uc.ChromeOptions()
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        # UC's SeleniumFinder returns a pathlib.Path, but Selenium's binary_location
        # setter requires a plain str. Find Chrome ourselves to avoid the TypeError.
        chrome_path = self._find_chrome_binary()
        if chrome_path:
            options.binary_location = str(chrome_path)
            self.log(f"Chrome found at: {chrome_path}")
        else:
            self.log(
                "Warning: could not locate Chrome binary, UC will attempt auto-detect"
            )

        # headless=False is intentional: Cloudflare Turnstile detects headless mode
        return uc.Chrome(options=options, headless=False)

    def scrape(self, cards: List[Card]) -> List[CardPrice]:
        """Scrape prices from Imaginaire using undetected-chromedriver."""
        prices = []

        if not UC_AVAILABLE:
            self.log(
                "undetected-chromedriver not installed, cannot bypass Cloudflare. Skipping."
            )
            return self._create_not_found_prices(cards)

        uc_driver = None
        try:
            self.log("Creating undetected-chromedriver instance...")
            uc_driver = self._create_uc_driver()

            self.log(f"Loading {self.deck_builder_url}...")
            uc_driver.get(self.deck_builder_url)
            time.sleep(5)

            self.log(f"Page title: {uc_driver.title} | URL: {uc_driver.current_url}")

            card_text = "\n".join([f"{card.quantity} {card.name}" for card in cards])

            self.log("Waiting for textarea...")
            textarea = WebDriverWait(uc_driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "textarea#deck"))
            )
            self.log(f"Textarea found, entering {len(cards)} cards...")
            uc_driver.execute_script(
                "document.getElementById('deck').value = arguments[0];", card_text
            )
            time.sleep(1)

            self.log("Submitting decklist via JS (formatItems)...")
            uc_driver.execute_script("formatItems();")
            time.sleep(5)

            self.log(f"After submit — URL: {uc_driver.current_url}")
            self.log("Parsing results...")
            prices.extend(self._extract_prices(cards, uc_driver))

        except Exception as e:
            self.log(f"Error scraping: {e}")
            import traceback

            traceback.print_exc()
            prices.extend(self._create_not_found_prices(cards))
        finally:
            if uc_driver:
                try:
                    uc_driver.quit()
                except Exception:
                    pass
                # Prevent UC's __del__ from trying to quit a second time at GC
                try:
                    uc_driver.__del__ = lambda *a, **kw: None
                except Exception:
                    pass

        return prices

    def _extract_prices(self, cards: List[Card], driver) -> List[CardPrice]:
        """Extract prices from Imaginaire results page"""
        prices = []

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.card-listing"))
            )

            card_items = driver.find_elements(By.CSS_SELECTOR, "li.card-listing")
            found_cards = {}

            for item in card_items:
                try:
                    name_elem = item.find_element(By.CSS_SELECTOR, "h3.magictitle")
                    card_name = name_elem.text.strip()

                    # Cards the site couldn't match have no qty input — skip them
                    qty_inputs = item.find_elements(
                        By.CSS_SELECTOR, "input[name^='qty']"
                    )

                    price = self._parse_price(
                        qty_inputs[0].get_attribute("price") or ""
                    )

                    # Available quantity from cardheaderright text e.g. "1/3"
                    header_div = item.find_element(
                        By.CSS_SELECTOR, "div.cardheaderright > div"
                    )
                    avail = self._parse_available(header_div.text)

                    found_cards[card_name.lower()] = CardPrice(
                        card_name=card_name,
                        original_query=card_name,
                        price=price,
                        website=self.name,
                        found=True,
                        quantity_available=avail,
                    )

                except Exception as e:
                    self.log(f"Error parsing card item: {e}")

            for card in cards:
                card_key = card.name.lower()
                if card_key in found_cards:
                    prices.append(found_cards[card_key])
                else:
                    found = False
                    for key, price_info in found_cards.items():
                        if card_key in key or key in card_key:
                            prices.append(
                                CardPrice(
                                    card_name=price_info.card_name,
                                    original_query=card.name,
                                    price=price_info.price,
                                    website=price_info.website,
                                    found=True,
                                    quantity_available=price_info.quantity_available,
                                )
                            )
                            found = True
                            break
                    if not found:
                        prices.append(self._create_not_found_price(card))

        except Exception as e:
            self.log(f"Error extracting prices: {e}")

        return prices

    def _parse_price(self, price_text: str) -> float:
        """Parse price from text"""
        price_text = re.sub(r"[^\d.]", "", price_text)
        try:
            return float(price_text)
        except Exception:
            return float("inf")

    def _parse_available(self, text: str) -> int:
        """Parse available quantity from text like '1/3' or '1 / 3'"""
        match = re.search(r"/\s*(\d+)", text)
        if match:
            return int(match.group(1))
        return 0
