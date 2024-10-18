from fastapi import FastAPI, Depends, HTTPException, Form, Query, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)
from starlette.middleware.gzip import GZipMiddleware
import playwright._impl._errors as playwright_errors
import base64
import os
from bs4 import BeautifulSoup
import htmlmin
from diskcache import Cache
from definitions import (
    ScreenshotResponse,
    MinimizeHTMLResponse,
    ExtractTextResponse,
    ResponseModel,
    ReaderResponse,
    MarkdownResponse,
)
import html2text
from readability import Document
from utils import generate_cache_key, load_env_file
import json


app = FastAPI(
    title="Playwright-based Webpage Scraper API",
    description="""
    This API allows users to browse webpages, capture screenshots, minimize HTML content, and extract text from HTML.
    Built using **FastAPI** and **Playwright**, this API provides advanced browsing features, handling redirects, and capturing network details. 
    It is designed for automation, scraping, and content extraction.

    ## Features:
    - **Browse Endpoint**: Retrieve detailed information about a webpage including network data, logs, performance metrics, redirects, and more.
    - **Screenshot Endpoint**: Capture a screenshot of any given URL, with optional full-page capture.
    - **Minimize HTML Endpoint**: Minify HTML content by removing unnecessary comments and whitespace.
    - **Extract Text Endpoint**: Extract clean, plain text from provided HTML content.

    ## Authentication:
    - API uses optional Bearer token authentication. If an API key is set via the `API_KEY` environment variable, it must be provided in the Authorization header. Otherwise, no authentication is required.
    
    ## Usage:
    - The **Browse** endpoint can track redirects and capture detailed request and response data.
    - The **Screenshot** endpoint allows live capture or retrieval from cache.
    - Minify HTML or extract text from raw HTML via the **Minimize HTML** and **Extract Text** endpoints.
    """,
    version="1.0.0",
)
app.add_middleware(GZipMiddleware, minimum_size=500)


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


# Initialize configurations
cache, CACHE_EXPIRATION_SECONDS, security, API_KEY = setup_configurations()


def optional_auth(
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    """
    If API_KEY is "none", skip authentication.
    If API_KEY is set, enforce Bearer token authentication.
    """
    if API_KEY == "none":
        return None
    elif credentials:
        token = credentials.credentials
        if token == API_KEY:
            return credentials
        else:
            raise HTTPException(status_code=403, detail="Invalid API key")
    else:
        raise HTTPException(
            status_code=401, detail="Authorization header missing or invalid"
        )


@app.get("/browse", response_model=ResponseModel)
async def browse(
    url: str,
    method: str = "GET",
    post_data: str = None,
    browser_name: str = "chromium",
    credentials: HTTPAuthorizationCredentials = Depends(optional_auth),
):
    """
    Browse a webpage and gather various details including network data, logs, performance metrics, and more.

    ### Parameters:
    - **url**: (str) The URL of the webpage to browse.
    - **method**: (str) The HTTP method to use. Defaults to GET.
    - **post_data**: (str) Optional POST data to send if method is POST.
    - **browser_name**: (str) The browser to use (chromium, firefox, webkit). Defaults to "chromium".
    - **credentials**: (HTTPAuthorizationCredentials) Optional Bearer token for API authentication.

    ### Returns:
    - A JSON object containing:
        - **page_title**: (str) The title of the webpage.
        - **meta_description**: (str) The meta description of the webpage, if available.
        - **network_data**: (List[NetworkDataModel]) Detailed timing and headers for each network request.
        - **logs**: (List[LogModel]) Console logs and JavaScript errors encountered on the webpage.
        - **cookies**: (List[CookieModel]) Cookies set by the webpage.
        - **performance_metrics**: (PerformanceMetricsModel) Performance timing metrics for the page load.
        - **screenshot**: (str) A base64-encoded screenshot of the webpage.
        - **downloaded_files**: (List[DownloadedFileModel]) A list of files downloaded during the browsing session.
        - **redirects**: (List[RedirectModel]) Information about the redirects that occurred during the browsing session.
    """
    cache_key = generate_cache_key(f"{url}-{method}-{post_data}-{browser_name}")

    # Check if the result is already cached
    if cache_key in cache:
        return JSONResponse(
            content=json.loads(cache[cache_key])
        )  # Deserialize and return cached data

    async with async_playwright() as p:
        # Select the browser
        browser_type = getattr(p, browser_name, None)
        if browser_type is None:
            return JSONResponse(
                content={"error": f'Browser "{browser_name}" is not supported'},
                status_code=400,
            )

        # Set up download directory
        download_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(download_dir, exist_ok=True)

        browser = await browser_type.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        network_data = []
        logs = []
        redirects = []  # To capture redirects
        performance_metrics = {}
        downloaded_files = []

        # Track requests and responses with detailed timings and error handling
        async def log_request(request):
            try:
                # Try to log timing data, but continue even if it fails
                timing = request.timing or {}

                # Try to fetch request headers
                try:
                    headers = await request.all_headers()
                except Exception as e:
                    headers = "Unavailable due to error"
                    logs.append(
                        {"warning": f"Failed to fetch request headers: {str(e)}"}
                    )

                # Try to fetch cookies
                try:
                    cookies = await context.cookies()
                except Exception as e:
                    cookies = "Unavailable due to error"
                    logs.append({"warning": f"Failed to fetch cookies: {str(e)}"})

                # Log the request data
                network_data.append(
                    {
                        "url": request.url,
                        "method": request.method,
                        "headers": headers,
                        "cookies": cookies,
                        "resource_type": request.resource_type,
                        "timing": {
                            "start_time": timing.get("startTime", -1),
                            "domain_lookup_start": timing.get("domainLookupStart", -1),
                            "domain_lookup_end": timing.get("domainLookupEnd", -1),
                            "connect_start": timing.get("connectStart", -1),
                            "secure_connection_start": timing.get(
                                "secureConnectionStart", -1
                            ),
                            "connect_end": timing.get("connectEnd", -1),
                            "request_start": timing.get("requestStart", -1),
                            "response_start": timing.get("responseStart", -1),
                            "response_end": timing.get("responseEnd", -1),
                        },
                    }
                )

            except Exception as e:
                # Log any unexpected errors during the request logging
                logs.append(
                    {"error": f"An error occurred while logging the request: {str(e)}"}
                )

        async def log_response(response):
            try:
                request = response.request
                timing = request.timing or {}

                # Try to fetch request headers
                try:
                    request_headers = await request.all_headers()
                except Exception as e:
                    request_headers = "Unavailable due to error"
                    logs.append(
                        {"warning": f"Failed to fetch request headers: {str(e)}"}
                    )

                # Try to fetch response headers
                try:
                    response_headers = await response.all_headers()
                except Exception as e:
                    response_headers = "Unavailable due to error"
                    logs.append(
                        {"warning": f"Failed to fetch response headers: {str(e)}"}
                    )

                status_code = response.status
                response_body = None
                response_size = 0

                # Try to fetch response body
                try:
                    content_type = response_headers.get("content-type", "")
                    if "text" in content_type or "json" in content_type:
                        response_body = await response.text()
                        response_size = len(response_body)
                    else:
                        body = await response.body()
                        response_body = base64.b64encode(body).decode("utf-8")
                        response_size = len(body)
                except Exception as e:
                    response_body = "Response body unavailable due to error"
                    logs.append({"warning": f"Failed to fetch response body: {str(e)}"})

                # Try to fetch cookies
                try:
                    cookies = await context.cookies()
                except Exception as e:
                    cookies = "Unavailable due to error"
                    logs.append({"warning": f"Failed to fetch cookies: {str(e)}"})

                # Try to fetch security details
                try:
                    security_details = await response.security_details()
                except Exception as e:
                    security_details = "Unavailable due to error"
                    logs.append(
                        {"warning": f"Failed to fetch security details: {str(e)}"}
                    )

                # Try to fetch server address
                try:
                    server_address = await response.server_addr()
                except Exception as e:
                    server_address = "Unavailable due to error"
                    logs.append(
                        {"warning": f"Failed to fetch server address: {str(e)}"}
                    )

                # Log the response data
                network_data.append(
                    {
                        "url": response.url,
                        "status": response.status,
                        "response_size": response_size,
                        "cookies": cookies,
                        "security": security_details,
                        "server": server_address,
                        "resource_type": request.resource_type,
                        "timing": {
                            "start_time": timing.get("startTime", -1),
                            "domain_lookup_start": timing.get("domainLookupStart", -1),
                            "domain_lookup_end": timing.get("domainLookupEnd", -1),
                            "connect_start": timing.get("connectStart", -1),
                            "secure_connection_start": timing.get(
                                "secureConnectionStart", -1
                            ),
                            "connect_end": timing.get("connectEnd", -1),
                            "request_start": timing.get("requestStart", -1),
                            "response_start": timing.get("responseStart", -1),
                            "response_end": timing.get("responseEnd", -1),
                        },
                        "request_headers": request_headers,
                        "response_headers": response_headers,
                        "response_body": response_body,
                    }
                )

                # Handle redirects using redirected_from or redirected_to properties
                if request.redirected_from:
                    redirects.append(
                        {
                            "step": len(redirects) + 1,
                            "from": request.redirected_from.url,  # The original URL before the redirect
                            "to": request.redirected_from.redirected_to.url,  # The URL where it was redirected
                            "status_code": status_code,
                            "server": await response.server_addr(),
                            "resource_type": request.resource_type,
                        }
                    )

            except Exception as e:
                # Log any unexpected errors during the response logging
                logs.append(
                    {"error": f"An error occurred while logging the response: {str(e)}"}
                )

        def log_console(msg):
            logs.append({"console_message": msg})

        def log_js_error(error):
            logs.append({"javascript_error": str(error)})

        page.on("request", log_request)
        page.on("response", log_response)
        page.on("console", log_console)
        page.on("pageerror", log_js_error)

        # Handle file downloads
        async def handle_download(download):
            path = await download.path()
            file_name = download.suggested_filename
            with open(path, "rb") as f:
                file_content = base64.b64encode(f.read()).decode("utf-8")
                downloaded_files.append(
                    {"file_name": file_name, "file_content": file_content}
                )
            # Optionally remove the downloaded file after reading
            os.remove(path)

        page.on("download", handle_download)

        # Navigate to the URL
        try:
            if method == "POST" and post_data:
                await page.goto(url, method=method, post_data=post_data)
            else:
                await page.goto(url)
            await page.wait_for_load_state("load")

        except PlaywrightTimeoutError:
            # Log timeout issues
            logs.append({"console_message": "Navigation timed out"})

        # Capture page information, handle navigation destruction gracefully
        try:
            title = await page.title()
            meta_description = (
                await page.locator("meta[name='description']").get_attribute("content")
                or "No Meta Description"
            )
        except playwright_errors.Error:
            title = "Title unavailable due to navigation"
            meta_description = "Meta description unavailable due to navigation"

        performance_timing = await page.evaluate("window.performance.timing.toJSON()")
        performance_metrics["performance_timing"] = performance_timing

        cookies = await context.cookies()
        screenshot = await page.screenshot()

        # Collect the response data (ensure all data is serializable)
        response_data = {
            "redirects": redirects,
            "page_title": title,
            "meta_description": meta_description,
            "network_data": network_data,
            "logs": logs,
            "cookies": cookies,
            "performance_metrics": performance_metrics,
            "screenshot": base64.b64encode(screenshot).decode("utf-8"),
            "downloaded_files": downloaded_files,
        }

        await browser.close()
        serialized_response_data = json.dumps(response_data)
        cache.set(cache_key, serialized_response_data, expire=CACHE_EXPIRATION_SECONDS)
        return JSONResponse(content=response_data)


@app.get("/screenshot", response_model=ScreenshotResponse, status_code=200)
async def screenshotter(
    url: str,
    full_page: bool = Query(False),
    live: bool = Query(False),
    credentials: HTTPAuthorizationCredentials = Depends(optional_auth),
):
    """
    Capture a screenshot of the specified URL, optionally skipping the cache if `live=True`.

    If the `live` parameter is set to `True`, the cache will be bypassed, and a fresh screenshot
    will be taken. Otherwise, the cached screenshot will be returned if available.

    Args:
        url (str): The URL of the page to capture a screenshot of.
        full_page (bool, optional): Whether to capture the full page or just the visible viewport. Defaults to False.
        live (bool, optional): Whether to skip the cache and take a fresh screenshot. Defaults to False.

    Returns:
        JSONResponse: A JSON response containing the base64-encoded screenshot of the page.

    Raises:
        HTTPException: If there is any issue during the Playwright interaction or screenshot capture.
    """
    # Generate a unique cache key for this request
    cache_key = generate_cache_key(f"{url}_{full_page}")

    # If `live` is False, check if the screenshot is already cached
    if not live and cache_key in cache:
        return JSONResponse(content={"screenshot": cache[cache_key]})

    # Take a new screenshot using Playwright if not cached or `live=True`
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url)
        screenshot = await page.screenshot(full_page=full_page)
        await browser.close()

    # Convert the screenshot to base64 encoding
    screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")

    # Cache the new screenshot unless `live=True`
    if not live:
        cache.set(cache_key, screenshot_b64, expire=CACHE_EXPIRATION_SECONDS)

    # Return the screenshot as a JSON response
    return JSONResponse(content={"screenshot": screenshot_b64})


@app.post("/minimize", response_model=MinimizeHTMLResponse, status_code=200)
async def minimize_html(
    html: str = Form(...),
    credentials: HTTPAuthorizationCredentials = Depends(optional_auth),
):
    """
    Minimize the given HTML content by removing unnecessary comments and whitespace.

    The HTML content provided in the `html` form field is minimized using the `htmlmin` library,
    which removes comments and extra spaces. If the minimized HTML is cached, the cached version is returned.
    Otherwise, the HTML is minimized, cached, and returned.

    Args:
        html (str): The HTML content to be minimized, provided as a form field.

    Returns:
        MinimizeHTMLResponse: A JSON response containing the minimized HTML content.

    Raises:
        HTTPException: If there are any issues during HTML minimization.

    Response schema:
        200 Successful Response:
        {
            "minified_html": "string"
        }
    """
    # Generate a cache key for the HTML content
    cache_key = generate_cache_key(html)

    # If the minimized HTML is already cached, return the cached version
    if cache_key in cache:
        return JSONResponse(content={"minified_html": cache[cache_key]})

    # Minimize the HTML content
    minified_html = htmlmin.minify(html, remove_comments=True, remove_empty_space=True)

    # Cache the minimized HTML content
    cache.set(cache_key, minified_html, expire=CACHE_EXPIRATION_SECONDS)

    # Return the minimized HTML content
    return MinimizeHTMLResponse(minified_html=minified_html)


@app.post("/extract_text", response_model=ExtractTextResponse, status_code=200)
async def extract_text_from_html(
    html: str = Form(...),
    credentials: HTTPAuthorizationCredentials = Depends(optional_auth),
):
    """
    Extract plain text from the provided HTML content.

    The HTML content provided in the `html` form field is parsed using `BeautifulSoup`
    to extract the plain text, removing all HTML tags and formatting. If the text is cached,
    the cached version is returned. Otherwise, the plain text is extracted, cached, and returned.

    Args:
        html (str): The HTML content from which to extract plain text, provided as a form field.

    Returns:
        ExtractTextResponse: A JSON response containing the extracted plain text.

    Raises:
        HTTPException: If there are any issues during HTML parsing or text extraction.

    Response schema:
        200 Successful Response:
        {
            "text": "string"
        }
    """
    # Generate a cache key for the HTML content
    cache_key = generate_cache_key(html)

    # If the extracted text is already cached, return the cached version
    if cache_key in cache:
        return JSONResponse(content={"text": cache[cache_key]})

    # Parse the HTML content and extract the plain text
    soup = BeautifulSoup(html, "html.parser")
    text_content = soup.get_text(separator=" ", strip=True)

    # Cache the extracted text content
    cache.set(cache_key, text_content, expire=CACHE_EXPIRATION_SECONDS)

    # Return the extracted plain text
    return ExtractTextResponse(text=text_content)


@app.post("/reader", response_model=ReaderResponse)
async def html_to_reader(html: str = Form(...)):
    """
    Extracts the main readable content and title from the provided HTML using the readability library.

    Parameters:
    - **html**: The raw HTML content provided via a form field.

    Returns:
    - **ReaderResponse**: A JSON object containing the extracted title and main content.
    """
    if not html:
        raise HTTPException(status_code=400, detail="No HTML content provided")

    # Use readability-lxml to extract the main content
    doc = Document(html)
    reader_content = doc.summary()  # Extracts the main content
    title = doc.title()

    return ReaderResponse(title=title, content=reader_content)


@app.post("/markdown", response_model=MarkdownResponse)
async def html_to_markdown(html: str = Form(...)):
    """
    Convert the provided HTML content into Markdown format.

    ### Parameters:
    - **html**: The raw HTML content provided via a form field.

    ### Returns:
    - **MarkdownResponse**: A JSON object containing the converted Markdown content.
    """
    if not html:
        raise HTTPException(status_code=400, detail="No HTML content provided")

    # Convert the HTML to Markdown using html2text
    markdown_converter = html2text.HTML2Text()
    markdown_converter.ignore_links = False  # Optionally keep the links
    markdown_content = markdown_converter.handle(html)

    return MarkdownResponse(markdown=markdown_content)
