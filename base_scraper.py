from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from selenium import webdriver


@dataclass
class Card:
    """Represents a MTG card"""

    quantity: int
    name: str
    set_code: Optional[str] = None
    collector_number: Optional[str] = None


@dataclass
class CardPrice:
    """Represents a card price from a website"""

    card_name: str
    original_query: str
    price: float
    website: str
    found: bool
    quantity_available: int = 0


class BaseScraper(ABC):
    """Abstract base class for all website scrapers"""

    def __init__(self, driver: webdriver.Chrome):
        """
        Initialize the scraper with a shared Chrome WebDriver instance

        Args:
            driver: Selenium WebDriver instance to use for scraping
        """
        self.driver = driver

    @property
    @abstractmethod
    def website_name(self) -> str:
        """Return the display name of the website"""
        pass

    @property
    @abstractmethod
    def website_url(self) -> str:
        """Return the URL of the deck builder/search page"""
        pass

    @abstractmethod
    def scrape(self, cards: List[Card]) -> List[CardPrice]:
        """
        Scrape prices for the given cards from this website

        Args:
            cards: List of Card objects to search for

        Returns:
            List of CardPrice objects with results (including not found cards)
        """
        pass

    def is_enabled(self) -> bool:
        """
        Check if this scraper should be used
        Override this method if you want dynamic enabling/disabling

        Returns:
            True if scraper should be used, False otherwise
        """
        return True

    def get_priority(self) -> int:
        """
        Get the priority of this scraper (lower = higher priority)
        Used for ordering scrapers when multiple options exist

        Returns:
            Priority value (default: 100)
        """
        return 100

    def _create_not_found_price(self, card: Card) -> CardPrice:
        """
        Helper method to create a CardPrice for a card that wasn't found

        Args:
            card: Card that wasn't found

        Returns:
            CardPrice with found=False and price=inf
        """
        return CardPrice(
            card_name=card.name,
            original_query=card.name,
            price=float("inf"),
            website=self.website_name,
            found=False,
        )

    def _create_not_found_prices(self, cards: List[Card]) -> List[CardPrice]:
        """
        Helper method to create CardPrice list for cards that weren't found

        Args:
            cards: List of cards that weren't found

        Returns:
            List of CardPrice objects with found=False
        """
        return [self._create_not_found_price(card) for card in cards]
