import webbrowser
import time
from typing import Dict, List, Optional
from dataclasses import dataclass

try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

from base_vendor import CartItem
from vendors import (
    CryptMTGVendor,
    MagiCarteVendor,
    FaceToFaceGamesVendor,
    ImaginaireVendor,
    MythicStoreVendor,
    GodsArenaVendor,
)


@dataclass
class CartOpenResult:
    """Result of opening a store's cart page"""
    store_name: str
    success: bool
    url: str
    card_list: str
    supports_bulk_add: bool
    error: Optional[str] = None


class CartHandler:
    """Handles opening deck builder pages for all stores"""

    # Registry mapping store display names to vendors
    VENDORS = {
        "MagiCarte": MagiCarteVendor(),
        "CryptMTG": CryptMTGVendor(),
        "Imaginaire": ImaginaireVendor(),
        "Mythic Store": MythicStoreVendor(),
        "Arène des Dieux": GodsArenaVendor(),
        "Face to Face Games": FaceToFaceGamesVendor(),
    }

    def __init__(self):
        self.last_clipboard_content: Optional[str] = None

    @staticmethod
    def buy_list_to_cart_items(buy_list: List[Dict]) -> List[CartItem]:
        """
        Convert buy_list format from scraper_manager to CartItems.

        Args:
            buy_list: List of dicts with keys: card, quantity, price_per_unit, total_price

        Returns:
            List of CartItem objects
        """
        return [
            CartItem(
                card_name=item["card"],
                quantity=item["quantity"],
                price_per_unit=item["price_per_unit"],
                total_price=item["total_price"]
            )
            for item in buy_list
        ]

    def open_store(
        self,
        store_name: str,
        buy_list: List[Dict],
        copy_to_clipboard: bool = True
    ) -> CartOpenResult:
        """
        Open a single store's deck builder page.

        Args:
            store_name: The store name (must match VENDORS keys)
            buy_list: The buy list for this store from results["buy_lists"]
            copy_to_clipboard: Whether to copy card list to clipboard

        Returns:
            CartOpenResult with success status and details
        """
        vendor = self.VENDORS.get(store_name)
        if not vendor:
            return CartOpenResult(
                store_name=store_name,
                success=False,
                url="",
                card_list="",
                supports_bulk_add=False,
                error=f"Unknown store: {store_name}"
            )

        items = self.buy_list_to_cart_items(buy_list)
        card_list = vendor.format_card_list(items)
        url = vendor.deck_builder_url

        try:
            # Copy to clipboard if requested and available
            if copy_to_clipboard and CLIPBOARD_AVAILABLE:
                pyperclip.copy(card_list)
                self.last_clipboard_content = card_list

            # Open browser tab
            webbrowser.open_new_tab(url)

            return CartOpenResult(
                store_name=store_name,
                success=True,
                url=url,
                card_list=card_list,
                supports_bulk_add=vendor.supports_bulk_add
            )
        except Exception as e:
            return CartOpenResult(
                store_name=store_name,
                success=False,
                url=url,
                card_list=card_list,
                supports_bulk_add=vendor.supports_bulk_add,
                error=str(e)
            )

    def open_all_stores(
        self,
        buy_lists: Dict[str, List[Dict]],
        delay_seconds: float = 0.5
    ) -> List[CartOpenResult]:
        """
        Open deck builder pages for ALL stores that have cards.

        Args:
            buy_lists: Dict from results["buy_lists"], keyed by store name
            delay_seconds: Delay between opening tabs to avoid browser issues

        Returns:
            List of CartOpenResult for each store attempted
        """
        results = []
        stores_with_cards = [
            name for name in buy_lists.keys()
            if buy_lists[name]  # Only stores with actual cards
        ]

        for i, store_name in enumerate(stores_with_cards):
            # Copy to clipboard for each store (user can paste before next tab opens)
            result = self.open_store(
                store_name=store_name,
                buy_list=buy_lists[store_name],
                copy_to_clipboard=True
            )
            results.append(result)

            # Small delay between tabs
            if i < len(stores_with_cards) - 1:
                time.sleep(delay_seconds)

        return results

    def get_card_list_for_store(self, store_name: str, buy_list: List[Dict]) -> str:
        """
        Get formatted card list for a specific store.

        Returns:
            Formatted string ready to paste into deck builder, or empty string if store unknown
        """
        vendor = self.VENDORS.get(store_name)
        if not vendor:
            return ""

        items = self.buy_list_to_cart_items(buy_list)
        return vendor.format_card_list(items)

    def copy_to_clipboard(self, text: str) -> bool:
        """
        Copy text to clipboard.

        Returns:
            True if successful, False if clipboard not available
        """
        if not CLIPBOARD_AVAILABLE:
            return False

        try:
            pyperclip.copy(text)
            self.last_clipboard_content = text
            return True
        except Exception:
            return False

    @staticmethod
    def is_clipboard_available() -> bool:
        """Check if clipboard functionality is available."""
        return CLIPBOARD_AVAILABLE
