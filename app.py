import streamlit as st
import pandas as pd
from scraper_manager import ScraperManager
from scraper_config import create_custom_config
from scrapers import CryptMTGScraper, MagiCarteScraper, FaceToFaceGamesScraper
import time

# Page configuration
st.set_page_config(page_title="MTG Card Price Scraper", page_icon="🛒", layout="wide")

# Custom CSS for better styling
st.markdown(
    """
    <style>
    .big-font {
        font-size:30px !important;
        font-weight: bold;
    }
    .stAlert {
        margin-top: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialize session state
if "results" not in st.session_state:
    st.session_state.results = None
if "df" not in st.session_state:
    st.session_state.df = None
if "scraping" not in st.session_state:
    st.session_state.scraping = False
if "raw_vendor_results" not in st.session_state:
    st.session_state.raw_vendor_results = None
if "parsed_cards" not in st.session_state:
    st.session_state.parsed_cards = None
if "vendor_status" not in st.session_state:
    st.session_state.vendor_status = {}


def reset_app():
    """Reset the application state"""
    st.session_state.results = None
    st.session_state.df = None
    st.session_state.scraping = False
    st.session_state.raw_vendor_results = None
    st.session_state.parsed_cards = None
    st.session_state.vendor_status = {}


def format_results_to_dataframe(results):
    """Convert results to a nicely formatted DataFrame"""
    if not results or not results.get("best_prices"):
        return None

    data = []
    for card_name, info in results["best_prices"].items():
        data.append(
            {
                "Card Name": card_name,
                "Quantity Needed": info["quantity_needed"],
                "Best Price (per unit)": f"${info['best_price']:.2f}",
                "Website": info["website"],
                "Quantity Available": info["quantity_available"],
                "Total Cost": f"${info['best_price'] * info['quantity_needed']:.2f}",
            }
        )

    df = pd.DataFrame(data)
    return df


def format_buy_lists(results):
    """Format buy lists by website"""
    if not results or not results.get("buy_lists"):
        return None

    buy_list_data = {}
    for website, cards_list in results["buy_lists"].items():
        data = []
        for item in cards_list:
            data.append(
                {
                    "Card": item["card"],
                    "Quantity": item["quantity"],
                    "Price per Unit": f"${item['price_per_unit']:.2f}",
                    "Total": f"${item['total_price']:.2f}",
                }
            )
        buy_list_data[website] = pd.DataFrame(data)

    return buy_list_data


# App title and description
st.markdown('<p class="big-font">🃏 MTG Card Price Scraper</p>', unsafe_allow_html=True)
st.markdown(
    "Compare prices from **CryptMTG**, **MagiCarte**, and **Face to Face Games** to find the best deals!"
)

# Sidebar for configuration
st.sidebar.header("⚙️ Configuration")

# Scraper selection
st.sidebar.subheader("Enabled Scrapers")
use_magicarte = st.sidebar.checkbox("MagiCarte", value=True)
use_cryptmtg = st.sidebar.checkbox("CryptMTG", value=True)
use_f2f = st.sidebar.checkbox("Face to Face Games", value=True)

# Create two columns for input and reset button
col1, col2 = st.columns([5, 1])

with col1:
    # Text area for card input
    card_input = st.text_area(
        "Enter your MTG cards (Moxfield format):",
        height=200,
        placeholder="""1 Boompile (CMM) 371
1 Chromatic Lantern (PLG25) 1
1 Esper Sentinel (PLST) MH2-12
1 Final Showdown (OTJ) 11""",
        help="Format: quantity card_name (set) collector_number",
    )

with col2:
    st.markdown("<br>", unsafe_allow_html=True)  # Add spacing
    if st.button("🔄 Reset", use_container_width=True, type="secondary"):
        reset_app()
        st.rerun()

# Scrape button
if st.button("🔍 Find Best Prices", use_container_width=True, type="primary"):
    if not card_input.strip():
        st.error("Please enter at least one card!")
    elif not (use_cryptmtg or use_magicarte or use_f2f):
        st.error("Please enable at least one scraper!")
    else:
        st.session_state.scraping = True

        # Build scraper list (in preferred order)
        enabled_scrapers = []
        if use_magicarte:
            enabled_scrapers.append(MagiCarteScraper)
        if use_cryptmtg:
            enabled_scrapers.append(CryptMTGScraper)
        if use_f2f:
            enabled_scrapers.append(FaceToFaceGamesScraper)

        try:
            # Show loading message
            with st.spinner("🔄 Scraping all vendors in parallel..."):
                # Create configuration (no filtering at this stage)
                config = create_custom_config(
                    scrapers=enabled_scrapers,
                    min_cards=1,
                    price_override=0.0,
                    enable_filtering=False,
                    headless=True,  # Always use headless in Streamlit
                )

                # Initialize manager
                manager = ScraperManager(config)

                # Parse cards first
                parsed_cards = manager.parse_moxfield_format(card_input)
                st.session_state.parsed_cards = parsed_cards

                # Perform parallel scraping (no callback - can't update UI from threads)
                raw_results = manager.scrape_all_parallel(
                    cards=parsed_cards,
                    status_callback=None
                )

            # Store raw results in session state
            st.session_state.raw_vendor_results = raw_results
            st.session_state.scraping = False

            st.success(f"✅ Successfully scraped {len(raw_results)} vendors!")

            time.sleep(1)
            st.rerun()

        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            st.error(f"❌ Error during scraping: {str(e)}")
            with st.expander("Show error details"):
                st.code(error_details)
            st.session_state.scraping = False

# Vendor selection UI (after scraping is complete)
if st.session_state.raw_vendor_results and st.session_state.parsed_cards:
    st.markdown("---")
    st.markdown("### 🎯 Configure Vendor Selection & Preferences")

    # Create vendor selection checkboxes
    st.markdown("#### Select Vendors")
    st.caption("Check the vendors you want to include in your buy list.")

    vendor_cols = st.columns(len(st.session_state.raw_vendor_results))
    selected_vendors_dict = {}

    for idx, (vendor_name, results) in enumerate(st.session_state.raw_vendor_results.items()):
        with vendor_cols[idx]:
            cards_found = len([p for p in results if p.found])
            total_cards = len(st.session_state.parsed_cards)

            selected_vendors_dict[vendor_name] = st.checkbox(
                f"**{vendor_name}**",
                value=True,  # All selected by default
                key=f"vendor_select_{vendor_name}",
            )
            st.caption(f"{cards_found}/{total_cards} cards found")

    # Filter to only checked vendors
    active_vendors = [name for name, checked in selected_vendors_dict.items() if checked]

    if active_vendors:
        # Vendor preferences section
        st.markdown("---")
        st.markdown("#### 🎯 Vendor Preferences")

        col1, col2 = st.columns(2)

        with col1:
            vendor_preference_order = st.multiselect(
                "Preferred Vendor Order",
                options=active_vendors,
                default=active_vendors,
                help="Select vendors in order of preference (top = most preferred). We'll try to buy from preferred vendors first.",
                key="vendor_preference_order"
            )

        with col2:
            preference_threshold = st.slider(
                "Preference Threshold ($)",
                min_value=0.0,
                max_value=10.0,
                value=1.0,
                step=0.25,
                help="If a card costs at most $X more at a preferred vendor, buy it there instead of the cheapest vendor.",
                key="preference_threshold"
            )

        # Use vendor preference order, or default to active vendors if empty
        final_preferences = vendor_preference_order if vendor_preference_order else active_vendors
        final_threshold = preference_threshold

        # Recalculate results based on selections
        manager = ScraperManager(create_custom_config(scrapers=[], headless=True))
        st.session_state.results = manager.recalculate_results_for_selected_vendors(
            all_vendor_results=st.session_state.raw_vendor_results,
            parsed_cards=st.session_state.parsed_cards,
            selected_vendors=active_vendors,
            vendor_preferences=final_preferences,
            preference_threshold=final_threshold
        )
        st.session_state.df = format_results_to_dataframe(st.session_state.results)
    else:
        st.warning("⚠️ Please select at least one vendor to see results.")
        st.session_state.results = None
        st.session_state.df = None

# Display results
if st.session_state.results and st.session_state.df is not None:
    st.markdown("---")

    # Summary statistics
    st.subheader("📊 Summary")

    # Show how many vendors are selected
    if st.session_state.raw_vendor_results:
        active_count = len([name for name, checked in selected_vendors_dict.items() if checked])
        total_count = len(st.session_state.raw_vendor_results)
        st.caption(f"Buying from {active_count} of {total_count} vendors")

    if st.session_state.results.get("summary"):
        cols = st.columns(len(st.session_state.results["summary"]) + 1)

        for idx, (website, summary) in enumerate(
            st.session_state.results["summary"].items()
        ):
            with cols[idx]:
                st.metric(
                    label=website,
                    value=f"${summary['total_price']:.2f}",
                    delta=f"{summary['total_cards']} cards",
                )

        # Grand total
        grand_total = sum(
            s["total_price"] for s in st.session_state.results["summary"].values()
        )
        with cols[-1]:
            st.metric(
                label="🎯 Best Deal Total",
                value=f"${grand_total:.2f}",
                delta="Optimal buying",
            )

    # Best prices table
    st.markdown("---")
    st.subheader("💰 Best Prices by Card")
    st.dataframe(st.session_state.df, use_container_width=True, hide_index=True)

    # Download buttons
    col1, col2 = st.columns(2)

    with col1:
        csv_best = st.session_state.df.to_csv(index=False)
        st.download_button(
            label="📥 Download Best Prices CSV",
            data=csv_best,
            file_name="mtg_best_prices.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col2:
        # Create all prices CSV if available
        if st.session_state.results.get("all_prices"):
            all_prices_data = []
            for price in st.session_state.results["all_prices"]:
                all_prices_data.append(
                    {
                        "Card Name": price.card_name,
                        "Original Query": price.original_query,
                        "Price": price.price if price.found else None,
                        "Website": price.website,
                        "Found": price.found,
                        "Quantity Available": (
                            price.quantity_available if price.found else None
                        ),
                    }
                )
            df_all = pd.DataFrame(all_prices_data)
            df_all = df_all.sort_values(by=["Original Query", "Price"])
            csv_all = df_all.to_csv(index=False)
            st.download_button(
                label="📥 Download All Prices CSV (Debug)",
                data=csv_all,
                file_name="mtg_all_prices.csv",
                mime="text/csv",
                use_container_width=True,
                help="Shows all prices from all websites for debugging",
            )

    # Buy lists by website
    st.markdown("---")
    st.subheader("🛒 Shopping Lists by Website")

    buy_lists = format_buy_lists(st.session_state.results)
    if buy_lists:
        tabs = st.tabs(list(buy_lists.keys()))

        for idx, (website, df) in enumerate(buy_lists.items()):
            with tabs[idx]:
                st.dataframe(df, use_container_width=True, hide_index=True)

                # Calculate and display total
                total = st.session_state.results["summary"][website]["total_price"]
                st.markdown(f"**Total for {website}: ${total:.2f}**")

    # Cards not found
    if st.session_state.results.get("not_found"):
        st.markdown("---")
        st.subheader("❌ Cards Not Found")

        # Show which vendors were searched
        if st.session_state.raw_vendor_results and 'selected_vendors_dict' in locals():
            active_vendors_list = [name for name, checked in selected_vendors_dict.items() if checked]
            st.caption(f"These cards were not found in your selected vendors: {', '.join(active_vendors_list)}")

        # Create DataFrame for not found cards
        not_found_data = []
        for card in st.session_state.results["not_found"]:
            not_found_data.append({"Card Name": card})

        df_not_found = pd.DataFrame(not_found_data)
        st.dataframe(df_not_found, use_container_width=True, hide_index=True)

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray; padding: 20px;'>
        <p>Made with Streamlit | Scraping CryptMTG, MagiCarte & Face to Face Games</p>
    </div>
    """,
    unsafe_allow_html=True,
)
