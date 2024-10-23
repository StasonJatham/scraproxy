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


async def hide_cookie_banners(page):
    """
    Hides cookie banners on a webpage by injecting CSS styles that target common cookie banner elements.

    Parameters:
    - page: Playwright Page object

    Returns:
    - None
    """
    selectors = [
        # IDs and classes containing 'cookie', 'consent', 'gdpr', etc.
        "[id*='cookie']",
        "[class*='cookie']",
        "[id*='consent']",
        "[class*='consent']",
        "[id*='gdpr']",
        "[class*='gdpr']",
        "[id*='eprivacy']",
        "[class*='eprivacy']",
        "[id*='eu-cookie']",
        "[class*='eu-cookie']",
        "[id*='alert']",
        "[class*='alert']",
        "[id*='notice']",
        "[class*='notice']",
        "[id*='banner']",
        "[class*='banner']",
        "[id*='popup']",
        "[class*='popup']",
        "[id*='message']",
        "[class*='message']",
        "[id*='overlay']",
        "[class*='overlay']",
        "[aria-label*='cookie']",
        "[aria-label*='consent']",
        "[aria-label*='gdpr']",
        "[role='dialog']",
        "[role='alertdialog']",
        ".modal",
        ".overlay",
        ".popup",
        ".cookie-banner",
        ".cookie-consent",
        ".cookie-container",
        ".consent-banner",
        ".consent-message",
        ".cc-window",
        ".cc-banner",
        ".cookie-notice",
        ".gdpr-banner",
        ".alert",
        ".notification",
        ".privacy-message",
        ".qc-cmp-ui",  # Quantcast CMP
        "#usercentrics-root",  # Usercentrics CMP
        "#onetrust-banner-sdk",  # OneTrust CMP
        # Add more selectors as needed
    ]

    # Combine selectors into a single CSS selector
    combined_selectors = ", ".join(selectors)

    # JavaScript code to hide elements matching the selectors
    hide_script = f"""
    (function() {{
        const selectors = `{combined_selectors}`;
        const elements = document.querySelectorAll(selectors);
        elements.forEach(function(el) {{
            el.style.display = 'none';
            el.style.visibility = 'hidden';
        }});
    }})();
    """

    try:
        # Inject the script into the page
        await page.evaluate(hide_script)
        print("Injected script to hide cookie banners.")
    except Exception as e:
        print(f"Error hiding cookie banners: {e}")

    try:
        await page.evaluate("""                            
            (function() {
                function hideCookieBanners() {
                    // List of common selectors for cookie banners
                    const selectors = [
                    // IDs and classes containing 'cookie', 'consent', 'gdpr', etc.
                    "[id*='cookie']",
                    "[class*='cookie']",
                    "[id*='consent']",
                    "[class*='consent']",
                    "[id*='gdpr']",
                    "[class*='gdpr']",
                    "[id*='eprivacy']",
                    "[class*='eprivacy']",
                    "[id*='eu-cookie']",
                    "[class*='eu-cookie']",
                    "[id*='alert']",
                    "[class*='alert']",
                    "[id*='notice']",
                    "[class*='notice']",
                    "[id*='banner']",
                    "[class*='banner']",
                    "[id*='popup']",
                    "[class*='popup']",
                    "[id*='message']",
                    "[class*='message']",
                    "[id*='overlay']",
                    "[class*='overlay']",
                    "[aria-label*='cookie']",
                    "[aria-label*='consent']",
                    "[aria-label*='gdpr']",
                    "[role='dialog']",
                    "[role='alertdialog']",
                    ".modal",
                    ".overlay",
                    ".popup",
                    ".cookie-banner",
                    ".cookie-consent",
                    ".cookie-container",
                    ".consent-banner",
                    ".consent-message",
                    ".cc-window",
                    ".cc-banner",
                    ".cookie-notice",
                    ".gdpr-banner",
                    ".alert",
                    ".notification",
                    ".privacy-message",
                    ".qc-cmp-ui",        // Quantcast CMP
                    "#usercentrics-root", // Usercentrics CMP
                    "#onetrust-banner-sdk", // OneTrust CMP
                    // Add more selectors as needed
                    ];

                    function isCookieBanner(el) {
                    if (!el || el === document.documentElement) return false;

                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || el.offsetHeight === 0 || el.offsetWidth === 0) {
                        return false;
                    }

                    // Check for common text content
                    const textContent = el.textContent.toLowerCase();
                    const consentTexts = [
                        'we use cookies', 'we use cookies and similar technologies', 'this website uses cookies',
                        'cookie', 'cookies', 'consent', 'gdpr', 'privacy', 'your experience',
                        'accept', 'agree', 'allow', 'privacy policy', 'more information', 'learn more',
                        '了解更多', 'подробнее', 'más información', 'plus d\'informations', 'weiterlesen',
                        'maggiori informazioni', 'meer informatie', 'sapere di più', '了解更多信息', 'chiudi', 'schließen', 'close'
                    ];
                    for (const text of consentTexts) {
                        if (textContent.includes(text)) {
                        return true;
                        }
                    }

                    // Recursively check parent nodes up to a certain level
                    let parent = el.parentElement;
                    let depth = 0;
                    while (parent && depth < 3) {
                        if (isCookieBanner(parent)) {
                        return true;
                        }
                        parent = parent.parentElement;
                        depth++;
                    }

                    return false;
                    }

                    function hideElements(elements) {
                    for (const el of elements) {
                        try {
                        el.style.display = 'none';
                        el.style.visibility = 'hidden';
                        console.log('Hid cookie banner element:', el);
                        } catch (e) {
                        console.warn('Failed to hide element:', el, e);
                        }
                    }
                    }

                    function getAllElementsWithSelectors(root, selectors) {
                    const elements = new Set();

                    // For each selector, find matching elements
                    for (const selector of selectors) {
                        const found = root.querySelectorAll(selector);
                        for (const el of found) {
                        elements.add(el);
                        }
                    }

                    // Convert the set to an array
                    return Array.from(elements);
                    }

                    function traverseShadowDOM(root) {
                    let elements = [];
                    function traverse(node) {
                        if (node.shadowRoot) {
                        elements = elements.concat(getAllElementsWithSelectors(node.shadowRoot, selectors));
                        traverse(node.shadowRoot);
                        }
                        node.childNodes.forEach(child => {
                        if (child.nodeType === Node.ELEMENT_NODE) {
                            traverse(child);
                        }
                        });
                    }
                    traverse(root);
                    return elements;
                    }

                    function hideCookieBannersInRoot(root) {
                    // Find elements matching selectors
                    let elements = getAllElementsWithSelectors(root, selectors);

                    // Include elements found in Shadow DOM
                    elements = elements.concat(traverseShadowDOM(root));

                    // Filter elements that are likely to be cookie banners
                    elements = elements.filter(el => isCookieBanner(el));

                    // Hide identified elements
                    hideElements(elements);
                    }

                    function hideCookieBanners() {
                    // Hide cookie banners in the main document
                    hideCookieBannersInRoot(document);

                    // Hide cookie banners in iframes (same-origin only)
                    const iframes = document.getElementsByTagName('iframe');
                    for (const iframe of iframes) {
                        try {
                        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                        if (iframeDoc) {
                            hideCookieBannersInRoot(iframeDoc);
                        }
                        } catch (e) {
                        // Ignore cross-origin iframes
                        }
                    }
                    }

                    // Run the function after ensuring the DOM is loaded
                    if (document.readyState === 'complete' || document.readyState === 'interactive') {
                    setTimeout(hideCookieBanners, 1500); // Wait 1.5 seconds for dynamic content
                    } else {
                    document.addEventListener('DOMContentLoaded', function() {
                        setTimeout(hideCookieBanners, 1500); // Wait 1.5 seconds after DOM content is loaded
                    });
                    }
                }

                hideCookieBanners();
                })();                    
        """)
    except Exception as e:
        print(f"Error hiding cookie banners: {e}")
