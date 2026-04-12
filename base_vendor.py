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


@dataclass
class CartItem:
    """Represents a card to add to cart"""

    card_name: str
    quantity: int
    price_per_unit: float
    total_price: float


class BaseVendor(ABC):
    """Abstract base class for all vendor scrapers and cart formatters"""

    def __init__(self, driver: webdriver.Chrome = None):
        """
        Initialize the vendor with an optional Chrome WebDriver instance.

        Args:
            driver: Selenium WebDriver instance (only needed for scraping)
        """
        self.driver = driver

    def log(self, message: str):
        """
        Log a message with the vendor name prefix.

        Args:
            message: The message to log
        """
        print(f"{self.name} - {message}")

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the display name of the vendor"""
        pass

    @property
    @abstractmethod
    def deck_builder_url(self) -> str:
        """Return the URL of the deck builder page"""
        pass

    @property
    @abstractmethod
    def supports_bulk_add(self) -> bool:
        """Return True if the store has an 'Add All to Cart' button"""
        pass

    @abstractmethod
    def scrape(self, cards: List[Card]) -> List[CardPrice]:
        """
        Scrape prices for the given cards from this vendor.

        Args:
            cards: List of Card objects to search for

        Returns:
            List of CardPrice objects with results (including not found cards)
        """
        pass

    def format_card_list(self, items: List[CartItem]) -> str:
        """
        Format items for this store's deck builder textarea.
        Default format: {quantity} {card_name}
        Override in subclasses if store requires different format.

        Args:
            items: List of CartItem objects to format

        Returns:
            Formatted string ready to paste into deck builder
        """
        lines = []
        for item in items:
            lines.append(f"{item.quantity} {item.card_name}")
        return "\n".join(lines)

    @property
    def shipping_cost(self) -> float:
        """
        Flat shipping cost for this vendor (added once per order, not per card).
        0.0 means local pickup. Override in vendors that charge shipping.
        """
        return 0.0

    @property
    def fulfillment_label(self) -> str:
        """Human-readable fulfillment method shown in the UI."""
        return "Local Pickup"

    def is_enabled(self) -> bool:
        """
        Check if this vendor should be used.
        Override this method if you want dynamic enabling/disabling.

        Returns:
            True if vendor should be used, False otherwise
        """
        return True

    def get_priority(self) -> int:
        """
        Get the priority of this vendor (lower = higher priority).
        Used for ordering vendors when multiple options exist.

        Returns:
            Priority value (default: 100)
        """
        return 100

    def _create_not_found_price(self, card: Card) -> CardPrice:
        """
        Helper method to create a CardPrice for a card that wasn't found.

        Args:
            card: Card that wasn't found

        Returns:
            CardPrice with found=False and price=inf
        """
        return CardPrice(
            card_name=card.name,
            original_query=card.name,
            price=float("inf"),
            website=self.name,
            found=False,
        )

    def _create_not_found_prices(self, cards: List[Card]) -> List[CardPrice]:
        """
        Helper method to create CardPrice list for cards that weren't found.

        Args:
            cards: List of cards that weren't found

        Returns:
            List of CardPrice objects with found=False
        """
        return [self._create_not_found_price(card) for card in cards]
