from dataclasses import dataclass
from typing import List, Type
from base_scraper import BaseScraper


@dataclass
class VendorFilterConfig:
    """Configuration for vendor filtering logic"""

    # Minimum number of cards required from a vendor to include them
    min_cards_per_vendor: int = 3

    # Minimum price difference (in $) to override the min_cards_per_vendor rule
    # If a card is this much cheaper, use it even if vendor has fewer cards
    min_price_difference_override: float = 5.0

    # Whether to enable vendor filtering at all
    enable_filtering: bool = True


@dataclass
class ScraperConfig:
    """Main configuration for the scraper system"""

    # List of scraper classes to use
    enabled_scrapers: List[Type[BaseScraper]]

    # Vendor filtering configuration
    vendor_filter: VendorFilterConfig

    # Whether to run scrapers in headless mode
    headless: bool = False


# Default configuration
DEFAULT_CONFIG = ScraperConfig(
    enabled_scrapers=[
        # Import here to avoid circular imports
        # These will be populated when the config is loaded
    ],
    vendor_filter=VendorFilterConfig(
        min_cards_per_vendor=3,
        min_price_difference_override=5.0,
        enable_filtering=True,
    ),
    headless=False,
)


def create_default_config() -> ScraperConfig:
    """
    Create a default configuration with all available scrapers

    Returns:
        ScraperConfig with all scrapers enabled
    """
    from scrapers import CryptMTGScraper, MagiCarteScraper, FaceToFaceGamesScraper

    return ScraperConfig(
        enabled_scrapers=[
            CryptMTGScraper,
            MagiCarteScraper,
            FaceToFaceGamesScraper,
        ],
        vendor_filter=VendorFilterConfig(
            min_cards_per_vendor=3,
            min_price_difference_override=5.0,
            enable_filtering=True,
        ),
        headless=False,
    )


def create_custom_config(
    scrapers: List[Type[BaseScraper]] = None,
    min_cards: int = 3,
    price_override: float = 5.0,
    enable_filtering: bool = True,
    headless: bool = False,
) -> ScraperConfig:
    """
    Create a custom configuration

    Args:
        scrapers: List of scraper classes to use (None = all)
        min_cards: Minimum cards per vendor
        price_override: Price difference to override min_cards rule
        enable_filtering: Enable vendor filtering
        headless: Run in headless mode

    Returns:
        Custom ScraperConfig
    """
    if scrapers is None:
        from scrapers import CryptMTGScraper, MagiCarteScraper, FaceToFaceGamesScraper

        scrapers = [CryptMTGScraper, MagiCarteScraper, FaceToFaceGamesScraper]

    return ScraperConfig(
        enabled_scrapers=scrapers,
        vendor_filter=VendorFilterConfig(
            min_cards_per_vendor=min_cards,
            min_price_difference_override=price_override,
            enable_filtering=enable_filtering,
        ),
        headless=headless,
    )
