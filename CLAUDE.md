# MTG Card Price Scraper

A Python-based web scraper that compares Magic: The Gathering card prices across multiple Canadian retailers.

## Architecture

- **Backend**: Python 3.13+ with Selenium for web automation
- **Frontend**: Streamlit web UI
- **Pattern**: Plugin-based vendors with a manager orchestrating parallel scraping

## Key Files

### Entry Points
- `app.py` - Streamlit web UI (main entry point)
- `main.py` - CLI entry point

### Core Logic
- `scraper_manager.py` - Orchestrates parallel scraping, filtering, and result analysis
- `scraper_config.py` - Configuration dataclasses (VendorFilterConfig, VendorPreferenceConfig, ScraperConfig)
- `base_vendor.py` - Abstract base class for vendors, Card, CardPrice, and CartItem dataclasses
- `scraper_utils.py` - Selenium helper utilities (safe_click, wait_and_click, remove_overlays)

### Vendors (`vendors/`)
Each vendor inherits from `BaseVendor` and implements both scraping and cart formatting:
- `name` property - Display name
- `deck_builder_url` property - Deck builder page URL
- `supports_bulk_add` property - Whether store has "Add All to Cart" button
- `scrape(cards: List[Card]) -> List[CardPrice]` - Main scraping logic
- `format_card_list(items: List[CartItem]) -> str` - Format cards for deck builder textarea

Supported stores:
- `cryptmtg.py` - CryptMTG (cryptmtg.com)
- `magicarte.py` - MagiCarte (magicartestore.com)
- `facetofacegames.py` - Face to Face Games (facetofacegames.com)

### Cart Module (`cart/`)
Handles opening store pages in browser for adding cards to cart:
- `cart_handler.py` - Main CartHandler class with open_store() and open_all_stores()

## Data Models

```python
@dataclass
class Card:
    quantity: int
    name: str
    set_code: Optional[str] = None
    collector_number: Optional[str] = None

@dataclass
class CardPrice:
    card_name: str
    original_query: str
    price: float
    website: str
    found: bool
    quantity_available: int = 0

@dataclass
class CartItem:
    card_name: str
    quantity: int
    price_per_unit: float
    total_price: float
```

## Adding a New Vendor

1. Create `vendors/newstore.py`:
```python
from base_vendor import BaseVendor, Card, CardPrice

class NewStoreVendor(BaseVendor):
    @property
    def name(self) -> str:
        return "New Store"

    @property
    def deck_builder_url(self) -> str:
        return "https://newstore.com/deck-builder"

    @property
    def supports_bulk_add(self) -> bool:
        return True  # or False if manual adding required

    def scrape(self, cards: List[Card]) -> List[CardPrice]:
        # Navigate to deck builder, submit cards, parse results
        pass
```

2. Export in `vendors/__init__.py`
3. Add to `app.py` vendor selection
4. Add to `CartHandler.VENDORS` dict in `cart/cart_handler.py`

## Running

```bash
# Install dependencies
uv sync

# Run web UI
uv run streamlit run app.py

# Run CLI
uv run python main.py
```

## Card Input Format (Moxfield)

```
1 Boompile (CMM) 371
1 Chromatic Lantern (PLG25) 1
1 Esper Sentinel (PLST) MH2-12
```

Format: `quantity card_name (set_code) collector_number [*F*]`
