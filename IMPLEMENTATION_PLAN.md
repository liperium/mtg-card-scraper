# MTG Card Scraper - Parallel Scraping & Dynamic Vendor Selection Implementation Plan

## Overview
This plan outlines the redesign of the MTG card scraper to support:
- Parallel scraping with per-vendor loading indicators
- Post-scraping vendor selection and dynamic recalculation
- Vendor preference ordering with price threshold logic
- Smart "not found" filtering based on selected vendors

## User Preferences (Confirmed)
1. **Preference UI**: Both places - set initial preferences in sidebar, can adjust after seeing results
2. **Default selection**: All vendors selected after scraping
3. **Not Found details**: Just card names (simple)
4. **Threshold logic**: Only apply to selected vendors

## Architecture Changes

### Current Flow
```
User Input → ScraperManager.scrape_all() (sequential) → Results → Display
```

### New Flow
```
User Input + Initial Preferences (sidebar)
    ↓
ScraperManager.scrape_all() (parallel with progress callbacks)
    ↓
Store raw results in session state
    ↓
Display vendor selection checkboxes (all selected by default)
    ↓
User adjusts: vendor selection, preferences, threshold
    ↓
ScraperManager.recalculate_results() (instant, no re-scraping)
    ↓
Display updated buy lists and "not found" cards
```

## Implementation Steps

### Phase 1: Parallel Scraping Infrastructure

#### Step 1.1: Modify ScraperManager for Parallel Execution
**File**: `scraper_manager.py`

**Add new method `_scrape_single_vendor()`**:
```python
def _scrape_single_vendor(
    self,
    scraper_class,
    cards: List[Card],
    status_callback=None
) -> Tuple[str, List[CardPrice]]:
    """
    Scrape a single vendor in a separate thread.
    Creates its own WebDriver instance.

    Returns: (vendor_name, list of CardPrice results)
    """
    try:
        if status_callback:
            status_callback(scraper_class.website_name, "loading")

        # Create fresh driver for this thread
        driver = self._initialize_driver()
        scraper = scraper_class(driver)
        results = scraper.scrape(cards)
        driver.quit()

        if status_callback:
            status_callback(scraper_class.website_name, "complete")

        return (scraper_class.website_name, results)
    except Exception as e:
        if status_callback:
            status_callback(scraper_class.website_name, "error")
        return (scraper_class.website_name, [])
```

**Modify `scrape_all()` to use ThreadPoolExecutor**:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def scrape_all(
    self,
    cards: List[Card],
    status_callback=None
) -> Dict[str, List[CardPrice]]:
    """
    Scrape all enabled vendors in parallel.

    Returns: Dict mapping vendor_name -> List[CardPrice]
    """
    all_results = {}

    with ThreadPoolExecutor(max_workers=len(self.config.enabled_scrapers)) as executor:
        # Submit all scraping tasks
        future_to_scraper = {
            executor.submit(
                self._scrape_single_vendor,
                scraper_class,
                cards,
                status_callback
            ): scraper_class
            for scraper_class in self.config.enabled_scrapers
        }

        # Collect results as they complete
        for future in as_completed(future_to_scraper):
            vendor_name, results = future.result()
            all_results[vendor_name] = results

    return all_results
```

#### Step 1.2: Update app.py for Parallel Scraping
**File**: `app.py`

**Add session state initialization** (after imports):
```python
# Initialize session state for vendor status tracking
if 'scraper_status' not in st.session_state:
    st.session_state.scraper_status = {}

if 'raw_vendor_results' not in st.session_state:
    st.session_state.raw_vendor_results = None

if 'parsed_cards' not in st.session_state:
    st.session_state.parsed_cards = None
```

**Create vendor status display** (before scraping starts):
```python
def display_vendor_status(enabled_scrapers):
    """Display loading status for each vendor."""
    st.markdown("### 🔄 Scraping Progress")
    cols = st.columns(len(enabled_scrapers))

    placeholders = {}
    for idx, scraper in enumerate(enabled_scrapers):
        with cols[idx]:
            placeholders[scraper.website_name] = st.empty()
            placeholders[scraper.website_name].info(f"⏳ {scraper.website_name}\nWaiting...")

    return placeholders

def update_vendor_status(placeholders, vendor_name, status):
    """Update a single vendor's status."""
    if vendor_name not in placeholders:
        return

    if status == "loading":
        placeholders[vendor_name].info(f"🔄 {vendor_name}\nScraping...")
    elif status == "complete":
        placeholders[vendor_name].success(f"✅ {vendor_name}\nComplete")
    elif status == "error":
        placeholders[vendor_name].error(f"❌ {vendor_name}\nError")
```

**Modify scraping call** to use status updates:
```python
# Create status placeholders
status_placeholders = display_vendor_status(enabled_scrapers)

# Define callback for status updates
def status_callback(vendor_name, status):
    update_vendor_status(status_placeholders, vendor_name, status)

# Call parallel scraping
manager = ScraperManager(config)
raw_results = manager.scrape_all(parsed_cards, status_callback=status_callback)

# Store raw results in session state
st.session_state.raw_vendor_results = raw_results
st.session_state.parsed_cards = parsed_cards
```

### Phase 2: Vendor Preference Configuration

#### Step 2.1: Add Preference Configuration to Sidebar
**File**: `app.py`

**Add to sidebar** (before scraping):
```python
st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Vendor Preferences")

# Get available vendor names
available_vendors = [s.website_name for s in [CryptMTGScraper, MagicarteScraper, FaceToFaceGamesScraper]]

# Preference ordering (multiselect maintains order)
vendor_preference_order = st.sidebar.multiselect(
    "Preferred Vendor Order",
    options=available_vendors,
    default=available_vendors,
    help="Select vendors in order of preference (top = most preferred). We'll try to buy from preferred vendors first."
)

# Price threshold for staying at preferred vendor
preference_threshold = st.sidebar.slider(
    "Preference Threshold ($)",
    min_value=0.0,
    max_value=10.0,
    value=1.0,
    step=0.25,
    help="If a card costs at most $X more at a preferred vendor, buy it there instead of the cheapest vendor."
)
```

#### Step 2.2: Create Vendor Preference Config
**File**: `scraper_config.py`

**Add new dataclass**:
```python
@dataclass
class VendorPreferenceConfig:
    """Configuration for vendor preference ordering."""
    preference_order: List[str]
    preference_threshold: float

    def __post_init__(self):
        if self.preference_threshold < 0:
            raise ValueError("Preference threshold must be non-negative")
```

**Update ScraperConfig**:
```python
@dataclass
class ScraperConfig:
    enabled_scrapers: List[Type[BaseScraper]]
    vendor_filter: VendorFilterConfig
    vendor_preference: VendorPreferenceConfig  # NEW
    headless: bool = False
```

### Phase 3: Post-Scraping Vendor Selection & Recalculation

#### Step 3.1: Create Recalculation Function
**File**: `scraper_manager.py`

**Add new method**:
```python
def recalculate_results_for_selected_vendors(
    self,
    all_vendor_results: Dict[str, List[CardPrice]],
    parsed_cards: List[Card],
    selected_vendors: List[str],
    vendor_preferences: List[str],
    preference_threshold: float
) -> Dict:
    """
    Recalculate best prices and buy lists based on selected vendors and preferences.

    This is called when user changes vendor selection or preference settings.
    Does NOT re-scrape - uses cached results.

    Args:
        all_vendor_results: Complete results from all scrapers
        parsed_cards: Original parsed card list
        selected_vendors: List of vendor names user wants to buy from
        vendor_preferences: Ordered list of preferred vendors (most preferred first)
        preference_threshold: Max price difference to keep card at preferred vendor

    Returns:
        Dict with best_prices, buy_lists, summary, not_found
    """
    # Filter to only selected vendors
    filtered_results = {
        vendor: results
        for vendor, results in all_vendor_results.items()
        if vendor in selected_vendors
    }

    # Flatten all prices from selected vendors
    all_prices = []
    for vendor_name, prices in filtered_results.items():
        all_prices.extend(prices)

    # Build best prices using preference logic
    best_prices = {}
    for card in parsed_cards:
        # Find all available prices for this card from selected vendors
        available_prices = [
            p for p in all_prices
            if p.original_query == card.name and p.found
        ]

        if not available_prices:
            continue

        # Apply preference-based selection
        selected_price = self._select_vendor_with_preference(
            available_prices,
            vendor_preferences,
            preference_threshold,
            selected_vendors
        )

        if selected_price:
            best_prices[card.name] = {
                "quantity_needed": card.quantity,
                "best_price": selected_price.price,
                "website": selected_price.website,
                "quantity_available": selected_price.quantity_available
            }

    # Build buy lists per vendor
    buy_lists = self._build_buy_lists(best_prices)

    # Calculate summary
    summary = self._calculate_summary(buy_lists)

    # Find cards not found in selected vendors
    not_found = [
        card.name for card in parsed_cards
        if card.name not in best_prices
    ]

    return {
        "best_prices": best_prices,
        "buy_lists": buy_lists,
        "summary": summary,
        "not_found": not_found,
        "all_prices": all_prices
    }

def _select_vendor_with_preference(
    self,
    available_prices: List[CardPrice],
    vendor_preferences: List[str],
    threshold: float,
    selected_vendors: List[str]
) -> CardPrice:
    """
    Select vendor for a card based on preference order and threshold.

    Logic:
    1. Find the absolute cheapest price among selected vendors
    2. For each vendor in preference order:
       - If vendor is in selected_vendors AND has this card:
         - If price <= (cheapest + threshold): select this vendor
    3. If no preferred vendor within threshold, select absolute cheapest
    """
    if not available_prices:
        return None

    # Sort by price (ascending)
    sorted_prices = sorted(available_prices, key=lambda p: p.price)
    cheapest_price = sorted_prices[0].price

    # Try to find a preferred vendor within threshold
    for preferred_vendor in vendor_preferences:
        if preferred_vendor not in selected_vendors:
            continue  # Skip unselected vendors

        for price in available_prices:
            if price.website == preferred_vendor:
                if price.price <= (cheapest_price + threshold):
                    return price
                break  # This vendor's price is too high

    # Fall back to absolute cheapest
    return sorted_prices[0]

def _build_buy_lists(self, best_prices: Dict) -> Dict:
    """Build per-vendor shopping lists."""
    buy_lists = {}

    for card_name, details in best_prices.items():
        vendor = details["website"]
        if vendor not in buy_lists:
            buy_lists[vendor] = []

        buy_lists[vendor].append({
            "card": card_name,
            "quantity": details["quantity_needed"],
            "price_per_unit": details["best_price"],
            "total_price": details["best_price"] * details["quantity_needed"]
        })

    return buy_lists

def _calculate_summary(self, buy_lists: Dict) -> Dict:
    """Calculate summary statistics per vendor."""
    summary = {}

    for vendor, items in buy_lists.items():
        total_cards = sum(item["quantity"] for item in items)
        total_price = sum(item["total_price"] for item in items)

        summary[vendor] = {
            "total_cards": total_cards,
            "total_price": total_price
        }

    return summary
```

#### Step 3.2: Add Vendor Selection UI
**File**: `app.py`

**Add after scraping completes**:
```python
if st.session_state.raw_vendor_results:
    st.markdown("---")
    st.markdown("### 🎯 Select Vendors to Buy From")
    st.caption("Check the vendors you want to include in your buy list. Uncheck vendors to exclude them.")

    # Create vendor selection checkboxes
    cols = st.columns(len(st.session_state.raw_vendor_results))
    selected_vendors = {}

    for idx, (vendor_name, results) in enumerate(st.session_state.raw_vendor_results.items()):
        with cols[idx]:
            cards_found = len([p for p in results if p.found])
            total_cards = len(st.session_state.parsed_cards)

            selected_vendors[vendor_name] = st.checkbox(
                f"{vendor_name}",
                value=True,  # All selected by default
                key=f"vendor_select_{vendor_name}",
                help=f"{cards_found}/{total_cards} cards found"
            )
            st.caption(f"{cards_found}/{total_cards} cards")

    # Filter to only checked vendors
    active_vendors = [name for name, checked in selected_vendors.items() if checked]

    # Show preference adjustment (user can reorder after seeing results)
    st.markdown("#### 📊 Adjust Preferences (Optional)")
    with st.expander("Reorder vendor preferences"):
        # Filter preferences to only include selected vendors
        available_for_preference = [v for v in vendor_preference_order if v in active_vendors]

        adjusted_preferences = st.multiselect(
            "Reorder Preferred Vendors",
            options=active_vendors,
            default=available_for_preference,
            help="Reorder if needed. Top vendors are most preferred."
        )

        # If user adjusted, use that; otherwise use sidebar preferences
        final_preferences = adjusted_preferences if adjusted_preferences else vendor_preference_order

    # Recalculate results based on selections
    if active_vendors:
        st.session_state.results = manager.recalculate_results_for_selected_vendors(
            all_vendor_results=st.session_state.raw_vendor_results,
            parsed_cards=st.session_state.parsed_cards,
            selected_vendors=active_vendors,
            vendor_preferences=final_preferences,
            preference_threshold=preference_threshold
        )
```

### Phase 4: Update Results Display

#### Step 4.1: Modify Results Display
**File**: `app.py`

**Update "Not Found" section**:
```python
# Display cards not found in SELECTED vendors
if st.session_state.results.get("not_found"):
    st.markdown("---")
    st.subheader("❌ Cards Not Found")
    st.caption(f"These cards were not found in your selected vendors: {', '.join(active_vendors)}")

    for card in st.session_state.results["not_found"]:
        st.warning(f"• {card}")
```

**Add vendor summary metrics** (show selected vs total):
```python
st.markdown("### 📊 Summary")
st.caption(f"Buying from {len(active_vendors)} of {len(st.session_state.raw_vendor_results)} vendors")

# Existing summary display code...
```

### Phase 5: Testing & Edge Cases

#### Key Test Scenarios
1. **All vendors selected**: Should match old behavior (with preference logic applied)
2. **Single vendor selected**: Should only show cards from that vendor
3. **No vendors selected**: Should show warning and empty results
4. **Preference threshold = 0**: Should always pick absolute cheapest
5. **Preference threshold = 10**: Should strongly prefer top vendors
6. **Scraper failure**: Should handle gracefully (show error status, exclude from results)
7. **Changing selections**: Should recalculate instantly without re-scraping

#### Error Handling Additions
- Handle empty vendor selection (show warning)
- Handle scraper exceptions (don't crash entire scraping process)
- Handle network timeouts (mark vendor as errored)
- Validate preference threshold range

### Files to Modify

#### Core Files
1. **scraper_manager.py** - Add parallel scraping, recalculation logic, preference algorithm
2. **app.py** - Add vendor selection UI, preference controls, status display
3. **scraper_config.py** - Add VendorPreferenceConfig dataclass

#### Files to Reference (No Changes)
- **base_scraper.py** - Reference for Card and CardPrice structures
- **scrapers/*.py** - No changes needed (compatible with parallel execution)

## Timeline Considerations
- This is a complete architectural redesign
- Backward compatibility: Keep old functions initially, test thoroughly before removing
- Gradual rollout: Implement phases sequentially, test each phase before moving forward

## Success Criteria
✅ All 3 scrapers run in parallel with individual loading indicators
✅ User can select/deselect vendors after scraping
✅ Buy lists update instantly when selection changes
✅ Vendor preferences with threshold work correctly
✅ "Not Found" tab only shows cards missing from selected vendors
✅ No re-scraping needed when changing preferences/selections
✅ Error handling prevents single scraper failure from blocking others

## Additional Notes
- Session state persistence allows fast experimentation with vendor combinations
- Preference threshold gives users control over consolidation vs. absolute best price
- Parallel scraping significantly improves UX (3x faster with 3 vendors)
