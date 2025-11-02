"""
Utility functions for web scraping
"""
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
    StaleElementReferenceException,
)


def safe_click(driver, element, max_attempts=3, use_js=False):
    """
    Safely click an element with fallback to JavaScript click

    Args:
        driver: Selenium WebDriver instance
        element: WebElement to click
        max_attempts: Number of retry attempts
        use_js: If True, use JavaScript click instead of regular click

    Returns:
        True if click succeeded, False otherwise
    """
    for attempt in range(max_attempts):
        try:
            if use_js or attempt > 0:
                # Use JavaScript click as fallback or if explicitly requested
                driver.execute_script("arguments[0].click();", element)
                return True
            else:
                # Try regular click first
                element.click()
                return True
        except ElementClickInterceptedException:
            if attempt < max_attempts - 1:
                # Wait a bit and try again with JS click
                time.sleep(0.5)
                continue
            else:
                # Last attempt, try JS click
                try:
                    driver.execute_script("arguments[0].click();", element)
                    return True
                except:
                    return False
        except StaleElementReferenceException:
            # Element went stale, can't click it
            return False
        except Exception as e:
            if attempt < max_attempts - 1:
                time.sleep(0.5)
                continue
            return False

    return False


def wait_and_click(driver, selector, by=By.CSS_SELECTOR, timeout=10, use_js=False):
    """
    Wait for an element to be clickable and click it

    Args:
        driver: Selenium WebDriver instance
        selector: Element selector
        by: Selenium By selector type
        timeout: Max wait time in seconds
        use_js: If True, use JavaScript click

    Returns:
        True if click succeeded, False otherwise
    """
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((by, selector))
        )
        return safe_click(driver, element, use_js=use_js)
    except TimeoutException:
        # Element not clickable, try to find it anyway
        try:
            element = driver.find_element(by, selector)
            return safe_click(driver, element, use_js=True)
        except:
            return False
    except Exception:
        return False


def scroll_to_element(driver, element):
    """
    Scroll an element into view

    Args:
        driver: Selenium WebDriver instance
        element: WebElement to scroll to
    """
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
            element
        )
        time.sleep(0.3)  # Give time for scroll animation
    except:
        pass


def remove_overlays(driver):
    """
    Remove common overlay elements that might block clicks
    (cookie notices, popups, etc.)

    Args:
        driver: Selenium WebDriver instance
    """
    # Common overlay selectors
    overlay_selectors = [
        ".modal-backdrop",
        ".cookie-banner",
        ".popup-overlay",
        "#onetrust-banner-sdk",
        "[class*='cookie']",
        "[class*='gdpr']",
        "[class*='consent']",
    ]

    for selector in overlay_selectors:
        try:
            driver.execute_script(f"""
                document.querySelectorAll('{selector}').forEach(el => {{
                    el.style.display = 'none';
                    el.remove();
                }});
            """)
        except:
            pass


def wait_for_element(driver, selector, by=By.CSS_SELECTOR, timeout=10):
    """
    Wait for an element to be present in the DOM

    Args:
        driver: Selenium WebDriver instance
        selector: Element selector
        by: Selenium By selector type
        timeout: Max wait time in seconds

    Returns:
        WebElement if found, None otherwise
    """
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
        return element
    except TimeoutException:
        return None
    except Exception:
        return None
