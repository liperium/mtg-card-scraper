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

    def _find_chrome_binary(self) -> str | None:
        """Locate Chrome/Chromium binary reliably on NixOS, Linux, Windows."""
        import os
        import shutil
        from pathlib import Path

        # 1) Explicit env var from flake shellHook (BEST on NixOS)
        env_path = os.environ.get("CHROMIUM_BIN")
        if env_path and Path(env_path).is_file():
            return env_path

        # 2) PATH lookup (Linux/macOS/Windows)
        for name in (
            "chromium",
            "chromium-browser",
            "google-chrome",
            "chrome",
        ):
            path = shutil.which(name)
            if path and Path(path).is_file():
                return path

        # 3) Common Linux paths
        linux_candidates = [
            "/run/current-system/sw/bin/chromium",
            "/run/current-system/sw/bin/google-chrome",
        ]
        for candidate in linux_candidates:
            if Path(candidate).is_file():
                return candidate

        # 4) Windows fallback
        windows_candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]
        for candidate in windows_candidates:
            if Path(candidate).is_file():
                return candidate

        return None

    def _create_uc_driver(self):
        """Create an undetected-chromedriver instance to bypass Cloudflare."""
        import os, subprocess

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

        # Use the system chromedriver if available via env var (set by flake devShell).
        # This prevents UC from downloading a version that mismatches the system Chrome.
        driver_path = os.environ.get("CHROMEDRIVER_PATH") or os.environ.get("CHROMEDRIVER")
        version_main = None
        if chrome_path:
            try:
                out = subprocess.check_output(
                    [str(chrome_path), "--version"], text=True, timeout=5
                )
                # "Chromium 145.0.7632.159" → 145
                m = __import__("re").search(r"(\d+)\.", out)
                if m:
                    version_main = int(m.group(1))
            except Exception:
                pass

        # Pass only the Chrome version — do NOT pass driver_executable_path because
        # undetected-chromedriver needs to patch the binary, which fails on NixOS's
        # immutable /nix/store. Let UC download and cache its own copy instead.
        kwargs = {"options": options, "headless": False}
        if version_main:
            kwargs["version_main"] = version_main
            self.log(f"Chrome major version: {version_main}")

        # headless=False is intentional: Cloudflare Turnstile detects headless mode
        return uc.Chrome(**kwargs)

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
        """Extract prices from Imaginaire results page.

        Returns all in-stock printings per card. Imaginaire may have limited
        set info — we capture what's available.
        """
        prices = []

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.card-listing"))
            )

            card_items = driver.find_elements(By.CSS_SELECTOR, "li.card-listing")
            found_cards: dict[str, list[CardPrice]] = {}

            for item in card_items:
                try:
                    name_elem = item.find_element(By.CSS_SELECTOR, "h3.magictitle")
                    full_title = name_elem.text.strip()
                    card_name = full_title

                    # Try to extract set/foil from title or subtitle elements
                    set_code = None
                    collector_number = None
                    foil = False
                    try:
                        set_code, collector_number, foil = self._parse_title_set_info(full_title)
                    except Exception:
                        pass

                    # Cards the site couldn't match have no qty input — skip them
                    qty_inputs = item.find_elements(
                        By.CSS_SELECTOR, "input[name^='qty']"
                    )

                    price = self._parse_price(
                        qty_inputs[0].get_attribute("price") or ""
                    )

                    header_div = item.find_element(
                        By.CSS_SELECTOR, "div.cardheaderright > div"
                    )
                    avail = self._parse_available(header_div.text)

                    cp = CardPrice(
                        card_name=card_name,
                        original_query=card_name,
                        price=price,
                        website=self.name,
                        found=True,
                        quantity_available=avail,
                        set_code=set_code,
                        collector_number=collector_number,
                        foil=foil,
                    )
                    found_cards.setdefault(card_name.lower(), []).append(cp)

                except Exception as e:
                    self.log(f"Error parsing card item: {e}")

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
