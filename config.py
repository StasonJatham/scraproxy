import os
from diskcache import Cache
from fastapi.security import HTTPBearer
from utils import load_env_file
import hashlib


def url_to_sha256_filename(url: str, extension: str = "webm") -> str:
    sha256_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    base_name = url.split("://")[-1].split("/")[0]
    base_name = base_name.replace(":", "_").replace("/", "_")
    filename = f"{base_name}_{sha256_hash}.{extension}"
    return filename


def setup_configurations():
    load_env_file()

    cache = Cache("./cache")
    cache_expiration_seconds = int(os.getenv("CACHE_EXPIRATION_SECONDS", 3600))

    playwright_browsers_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    if playwright_browsers_path != "0":
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = playwright_browsers_path

    api_key = os.environ.get("API_KEY", "none")
    security = HTTPBearer(auto_error=False)

    return cache, cache_expiration_seconds, security, api_key


async def close_cookie_banners(page):
    """
    Attempts to close cookie banners on a webpage by trying various common selectors and methods.

    Parameters:
    - page: Playwright Page object

    Returns:
    - True if a cookie banner was found and closed.
    - False if no cookie banner was found or it could not be closed.
    """
    # List of common selectors for cookie banner accept buttons
    selectors = [
        # Text-based selectors
        'text="Accept"',
        'text="I Accept"',
        'text="Accept All"',
        'text="Agree"',
        'text="I Agree"',
        'text="Accept Cookies"',
        'text="Allow"',
        'text="Allow All"',
        'text="Got It"',
        'text="OK"',
        'text="Yes"',
        'text="Continue"',
        'text="Close"',
        'text="Dismiss"',
        'text="Understood"',
        'text="Consent"',
        'text="Accept & Continue"',
        'text="Accept and Close"',
        'text="Accept all cookies"',
        # Button with specific text
        'button:has-text("Accept")',
        'button:has-text("Agree")',
        'button:has-text("OK")',
        'button:has-text("Yes")',
        # Aria-label selectors
        'button[aria-label*="Accept"]',
        'button[aria-label*="Agree"]',
        'button[aria-label*="Consent"]',
        # ID and class selectors containing keywords
        'button[id*="accept"]',
        'button[id*="consent"]',
        'button[class*="accept"]',
        'button[class*="consent"]',
        # Divs or spans that might be clickable
        '[role="button"][id*="accept"]',
        '[role="button"][class*="accept"]',
        '[role="button"][id*="consent"]',
        '[role="button"][class*="consent"]',
        # Generic selectors
        '[id*="cookie"] button',
        '[class*="cookie"] button',
        '[id*="consent"] button',
        '[class*="consent"] button',
        # Links
        'a:has-text("Accept")',
        'a:has-text("Agree")',
    ]

    # Try clicking each selector
    for selector in selectors:
        try:
            # Wait for the selector to be available and visible
            await page.locator(selector).wait_for(state="visible", timeout=3000)
            await page.locator(selector).click()
            print(f"Clicked cookie banner using selector: {selector}")
            return True  # Stop after first successful click
        except Exception:
            pass  # Ignore exceptions and try the next selector

    # If none of the above worked, try injecting JavaScript
    try:
        success = await page.evaluate("""() => {
            const buttons = Array.from(document.querySelectorAll('button, [role="button"], a, div'))
                .filter(el => {
                    const text = el.innerText.toLowerCase();
                    return (
                        el.offsetParent !== null &&  // Element is visible
                        (text.includes('accept') ||
                         text.includes('agree') ||
                         text.includes('consent') ||
                         text.includes('allow') ||
                         text.includes('close') ||
                         text.includes('got it') ||
                         text.includes('yes') ||
                         text.includes('ok'))
                    );
                });
            if (buttons.length > 0) {
                buttons[0].click();
                return true;
            }
            return false;
        }""")
        if success:
            print("Clicked cookie banner using injected JavaScript.")
            return True
    except Exception:
        pass  # Ignore exceptions

    # As a last resort, try to hide any elements that look like cookie banners
    try:
        await page.add_style_tag(
            content="""
            [id*='cookie'], [class*='cookie'], [id*='consent'], [class*='consent'], [role='dialog'], .modal, .overlay {
                display: none !important;
                visibility: hidden !important;
            }
        """
        )
        print("Attempted to hide cookie banners by injecting CSS.")
    except Exception:
        pass  # Ignore exceptions

    print("No cookie banner found or could not close it.")
    return False
