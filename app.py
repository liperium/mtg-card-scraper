import streamlit as st
import pandas as pd
from scraper_manager import ScraperManager
from scraper_config import create_custom_config
from scrapers import CryptMTGScraper, MagiCarteScraper, FaceToFaceGamesScraper
import time

# Page configuration
st.set_page_config(
    page_title="MTG Card Price Scraper",
    page_icon="🃏",
    layout="wide"
)

# Custom CSS for better styling
st.markdown("""
    <style>
    .big-font {
        font-size:30px !important;
        font-weight: bold;
    }
    .stAlert {
        margin-top: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

# Initialize session state
if 'results' not in st.session_state:
    st.session_state.results = None
if 'df' not in st.session_state:
    st.session_state.df = None
if 'scraping' not in st.session_state:
    st.session_state.scraping = False

def reset_app():
    """Reset the application state"""
    st.session_state.results = None
    st.session_state.df = None
    st.session_state.scraping = False

def format_results_to_dataframe(results):
    """Convert results to a nicely formatted DataFrame"""
    if not results or not results.get("best_prices"):
        return None

    data = []
    for card_name, info in results["best_prices"].items():
        data.append({
            "Card Name": card_name,
            "Quantity Needed": info["quantity_needed"],
            "Best Price (per unit)": f"${info['best_price']:.2f}",
            "Website": info["website"],
            "Quantity Available": info["quantity_available"],
            "Total Cost": f"${info['best_price'] * info['quantity_needed']:.2f}"
        })

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
            data.append({
                "Card": item["card"],
                "Quantity": item["quantity"],
                "Price per Unit": f"${item['price_per_unit']:.2f}",
                "Total": f"${item['total_price']:.2f}"
            })
        buy_list_data[website] = pd.DataFrame(data)

    return buy_list_data

# App title and description
st.markdown('<p class="big-font">🃏 MTG Card Price Scraper</p>', unsafe_allow_html=True)
st.markdown("Compare prices from **CryptMTG**, **MagiCarte**, and **Face to Face Games** to find the best deals!")

# Sidebar for configuration
st.sidebar.header("⚙️ Configuration")

# Scraper selection
st.sidebar.subheader("Enabled Scrapers")
use_cryptmtg = st.sidebar.checkbox("CryptMTG", value=True)
use_magicarte = st.sidebar.checkbox("MagiCarte", value=True)
use_f2f = st.sidebar.checkbox("Face to Face Games", value=True)

# Vendor filtering options
st.sidebar.subheader("Vendor Filtering")
enable_filtering = st.sidebar.checkbox(
    "Enable vendor filtering",
    value=True,
    help="Filter out vendors with too few cards to minimize shipping costs"
)

min_cards = st.sidebar.slider(
    "Min cards per vendor",
    min_value=1,
    max_value=10,
    value=3,
    disabled=not enable_filtering,
    help="Minimum number of cards required from a vendor"
)

price_override = st.sidebar.slider(
    "Price override threshold ($)",
    min_value=0.0,
    max_value=20.0,
    value=5.0,
    step=0.5,
    disabled=not enable_filtering,
    help="Use a vendor even if below min cards if card is this much cheaper"
)

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
        help="Format: quantity card_name (set) collector_number"
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

        # Build scraper list
        enabled_scrapers = []
        if use_cryptmtg:
            enabled_scrapers.append(CryptMTGScraper)
        if use_magicarte:
            enabled_scrapers.append(MagiCarteScraper)
        if use_f2f:
            enabled_scrapers.append(FaceToFaceGamesScraper)

        # Show loading state
        progress_text = st.empty()
        progress_bar = st.progress(0)

        try:
            # Create configuration
            config = create_custom_config(
                scrapers=enabled_scrapers,
                min_cards=min_cards,
                price_override=price_override,
                enable_filtering=enable_filtering,
                headless=True  # Always use headless in Streamlit
            )

            # Initialize manager
            progress_text.text("Initializing browser...")
            progress_bar.progress(10)
            manager = ScraperManager(config)

            # Define progress callback
            def update_progress(current, total, message):
                # Calculate progress: 10% for init, 80% for scraping, 10% for processing
                progress_percent = 10 + int((current / total) * 80)
                progress_text.text(f"[{current}/{total}] {message}")
                progress_bar.progress(progress_percent)

            # Perform scraping with progress updates
            results = manager.scrape_all(card_input, progress_callback=update_progress)

            # Final processing
            progress_text.text("Processing results...")
            progress_bar.progress(95)
            time.sleep(0.3)

            progress_bar.progress(100)
            progress_text.text("Complete!")
            time.sleep(0.5)

            # Store results in session state
            st.session_state.results = results
            st.session_state.df = format_results_to_dataframe(results)
            st.session_state.scraping = False

            # Clear progress indicators
            progress_text.empty()
            progress_bar.empty()

            num_found = len(results.get("best_prices", {}))
            st.success(f"✅ Successfully found prices for {num_found} cards!")

            # Show filtering info if enabled
            if enable_filtering:
                st.info(
                    f"ℹ️ Vendor filtering enabled: Min {min_cards} cards per vendor, "
                    f"${price_override} price override threshold"
                )

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            st.error(f"❌ Error during scraping: {str(e)}")
            with st.expander("Show error details"):
                st.code(error_details)
            st.session_state.scraping = False

# Display results
if st.session_state.results and st.session_state.df is not None:
    st.markdown("---")

    # Summary statistics
    st.subheader("📊 Summary")

    if st.session_state.results.get("summary"):
        cols = st.columns(len(st.session_state.results["summary"]) + 1)

        for idx, (website, summary) in enumerate(st.session_state.results["summary"].items()):
            with cols[idx]:
                st.metric(
                    label=website,
                    value=f"${summary['total_price']:.2f}",
                    delta=f"{summary['total_cards']} cards"
                )

        # Grand total
        grand_total = sum(s["total_price"] for s in st.session_state.results["summary"].values())
        with cols[-1]:
            st.metric(
                label="🎯 Best Deal Total",
                value=f"${grand_total:.2f}",
                delta="Optimal buying"
            )

    # Best prices table
    st.markdown("---")
    st.subheader("💰 Best Prices by Card")
    st.dataframe(
        st.session_state.df,
        use_container_width=True,
        hide_index=True
    )

    # Download buttons
    col1, col2 = st.columns(2)

    with col1:
        csv_best = st.session_state.df.to_csv(index=False)
        st.download_button(
            label="📥 Download Best Prices CSV",
            data=csv_best,
            file_name="mtg_best_prices.csv",
            mime="text/csv",
            use_container_width=True
        )

    with col2:
        # Create all prices CSV if available
        if st.session_state.results.get("all_prices"):
            all_prices_data = []
            for price in st.session_state.results["all_prices"]:
                all_prices_data.append({
                    "Card Name": price.card_name,
                    "Original Query": price.original_query,
                    "Price": price.price if price.found else None,
                    "Website": price.website,
                    "Found": price.found,
                    "Quantity Available": price.quantity_available if price.found else None,
                })
            df_all = pd.DataFrame(all_prices_data)
            df_all = df_all.sort_values(by=["Original Query", "Price"])
            csv_all = df_all.to_csv(index=False)
            st.download_button(
                label="📥 Download All Prices CSV (Debug)",
                data=csv_all,
                file_name="mtg_all_prices.csv",
                mime="text/csv",
                use_container_width=True,
                help="Shows all prices from all websites for debugging"
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
        for card in st.session_state.results["not_found"]:
            st.warning(f"• {card}")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray; padding: 20px;'>
        <p>Made with Streamlit | Scraping CryptMTG, MagiCarte & Face to Face Games</p>
    </div>
    """,
    unsafe_allow_html=True
)
