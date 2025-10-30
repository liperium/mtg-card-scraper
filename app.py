import streamlit as st
import pandas as pd
from main import MTGPriceScraper
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
st.markdown("Compare prices from **CryptMTG** and **MagiCarte** to find the best deals!")

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
    else:
        st.session_state.scraping = True

        # Show loading state
        with st.spinner("🔄 Scraping prices from websites..."):
            progress_text = st.empty()
            progress_bar = st.progress(0)

            try:
                # Initialize scraper (headless mode for Streamlit)
                scraper = MTGPriceScraper(headless=False)

                # Parse cards
                progress_text.text("Parsing cards...")
                progress_bar.progress(10)
                cards = scraper.parse_moxfield_format(card_input)

                # Scrape CryptMTG
                progress_text.text(f"Scraping CryptMTG for {len(cards)} cards...")
                progress_bar.progress(30)

                # Perform scraping
                results = scraper.scrape_all(card_input)

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

                st.success(f"✅ Successfully scraped prices for {len(cards)} cards!")

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

    # Download CSV button
    csv = st.session_state.df.to_csv(index=False)
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name="mtg_best_prices.csv",
        mime="text/csv",
        use_container_width=True
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
        <p>Made with Streamlit | Scraping CryptMTG & MagiCarte</p>
    </div>
    """,
    unsafe_allow_html=True
)
