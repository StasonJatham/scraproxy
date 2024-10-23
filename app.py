from fastapi import FastAPI, Depends, HTTPException, Form, Query, Security
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from fastapi.responses import FileResponse
from starlette.middleware.gzip import GZipMiddleware
import playwright._impl._errors as playwright_errors
import base64
import os
from bs4 import BeautifulSoup
import htmlmin

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
from utils import generate_cache_key, optimize_image, create_thumbnail
import json
from PIL import Image
import io
import uuid
from config import setup_configurations, url_to_sha256_filename, hide_cookie_banners


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
    cookiebanner: bool = Query(False, description="Attempt to close cookie banners"),
    credentials: HTTPAuthorizationCredentials = Depends(optional_auth),
):
    """
    Browse a webpage and gather various details including network data, logs, performance metrics, screenshots, and a video of the session.

    ### Parameters:
    - **url**: (str) The URL of the webpage to browse.
    - **method**: (str) The HTTP method to use. Defaults to GET.
    - **post_data**: (str) Optional POST data to send if method is POST.
    - **browser_name**: (str) The browser to use (chromium, firefox, webkit). Defaults to "chromium".
    - **credentials**: (HTTPAuthorizationCredentials) Optional Bearer token for API authentication.

    ### Returns:
    - A JSON object containing:
        - **redirects**: (List[RedirectModel]) Information about redirects during the session.
        - **page_title**: (str) The title of the webpage.
        - **meta_description**: (str) The meta description of the webpage, if available.
        - **network_data**: (List[NetworkDataModel]) Detailed timing and headers for each network request.
        - **logs**: (List[LogModel]) Console logs and JavaScript errors encountered on the webpage.
        - **cookies**: (List[CookieModel]) Cookies set by the webpage.
        - **performance_metrics**: (PerformanceMetricsModel) Performance timing metrics for the page load.
        - **screenshot**: (str) A base64-encoded screenshot of the webpage.
        - **thumbnail**: (str) A base64-encoded thumbnail of the webpage.
        - **downloaded_files**: (List[DownloadedFileModel]) Files downloaded during the browsing session.
        - **video**: (str) A base64-encoded video of the browsing session.

    ### Example of decoding the video on the client side:
    ```python
    import base64

    base64_video = response_data['video']
    video_bytes = base64.b64decode(base64_video)
    with open('session_video.webm', 'wb') as video_file:
        video_file.write(video_bytes)
    ```
    """
    cache_key = generate_cache_key(f"{url}-{method}-{post_data}-{browser_name}")
    request_uuid_map = {}

    if cache_key in cache:
        return JSONResponse(content=json.loads(cache[cache_key]))

    async with async_playwright() as p:
        browser_type = getattr(p, browser_name, None)
        if browser_type is None:
            return JSONResponse(
                content={"error": f'Browser "{browser_name}" is not supported'},
                status_code=400,
            )

        download_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(download_dir, exist_ok=True)

        # Set up video recording directory
        video_dir = os.path.join(os.getcwd(), "videos")
        os.makedirs(video_dir, exist_ok=True)

        # Launch browser with video recording enabled
        browser = await browser_type.launch(headless=True)
        context = await browser.new_context(
            accept_downloads=True,
            record_video_dir=video_dir,
            record_video_size={"width": 1280, "height": 720},
        )
        page = await context.new_page()

        network_data = []
        logs = []
        redirects = []
        performance_metrics = {}
        downloaded_files = []

        async def log_request(request):
            try:
                request_uuid = str(uuid.uuid4())
                request_uuid_map[request] = request_uuid

                timing = request.timing or {}

                try:
                    headers = await request.all_headers()
                except Exception as e:
                    headers = "Unavailable due to error"
                    logs.append(
                        {"warning": f"Failed to fetch request headers: {str(e)}"}
                    )

                try:
                    cookies = await context.cookies()
                except Exception as e:
                    cookies = "Unavailable due to error"
                    logs.append({"warning": f"Failed to fetch cookies: {str(e)}"})

                redirected_from_url = (
                    request.redirected_from.url if request.redirected_from else None
                )
                redirected_to_url = (
                    request.redirected_to.url if request.redirected_to else None
                )

                network_data.append(
                    {
                        "uuid": request_uuid,
                        "network": "request",
                        "url": request.url,
                        "method": request.method,
                        "headers": headers,
                        "cookies": cookies,
                        "resource_type": request.resource_type,
                        "redirected_from": redirected_from_url,
                        "redirected_to": redirected_to_url,
                        "timing": timing,
                    }
                )

            except Exception as e:
                logs.append(
                    {"error": f"An error occurred while logging the request: {str(e)}"}
                )

        async def log_response(response):
            try:
                request = response.request
                request_uuid = request_uuid_map.get(request)

                timing = request.timing or {}

                try:
                    request_headers = await request.all_headers()
                except Exception as e:
                    request_headers = "Unavailable due to error"
                    logs.append(
                        {"warning": f"Failed to fetch request headers: {str(e)}"}
                    )

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

                try:
                    cookies = await context.cookies()
                except Exception as e:
                    cookies = "Unavailable due to error"
                    logs.append({"warning": f"Failed to fetch cookies: {str(e)}"})

                try:
                    security_details = await response.security_details()
                except Exception as e:
                    security_details = "Unavailable due to error"
                    logs.append(
                        {"warning": f"Failed to fetch security details: {str(e)}"}
                    )

                try:
                    server_address = await response.server_addr()
                except Exception as e:
                    server_address = "Unavailable due to error"
                    logs.append(
                        {"warning": f"Failed to fetch server address: {str(e)}"}
                    )

                redirected_to_url = (
                    request.redirected_to.url if request.redirected_to else None
                )
                redirected_from_url = (
                    request.redirected_from.url if request.redirected_from else None
                )

                network_data.append(
                    {
                        "uuid": request_uuid,
                        "network": "response",
                        "url": response.url,
                        "status": response.status,
                        "response_size": response_size,
                        "cookies": cookies,
                        "security": security_details,
                        "server": server_address,
                        "resource_type": request.resource_type,
                        "redirected_to": redirected_to_url,
                        "redirected_from": redirected_from_url,
                        "timing": timing,
                        "request_headers": request_headers,
                        "response_headers": response_headers,
                        "response_body": response_body,
                    }
                )

                if request.redirected_from:
                    redirects.append(
                        {
                            "step": len(redirects) + 1,
                            "from": request.redirected_from.url,
                            "to": request.url,
                            "status_code": status_code,
                            "server": server_address,
                            "resource_type": request.resource_type,
                        }
                    )

            except Exception as e:
                logs.append(
                    {"error": f"An error occurred while logging the response: {str(e)}"}
                )

        def log_console(msg):
            try:
                logs.append({"console_message": msg.text})
            except Exception:
                pass

        def log_js_error(error):
            try:
                logs.append({"javascript_error": str(error)})
            except Exception:
                pass

        page.on("request", log_request)
        page.on("response", log_response)
        page.on("console", log_console)
        page.on("pageerror", log_js_error)

        async def handle_download(download):
            path = await download.path()
            file_name = download.suggested_filename
            with open(path, "rb") as f:
                file_content = base64.b64encode(f.read()).decode("utf-8")
                downloaded_files.append(
                    {"file_name": file_name, "file_content": file_content}
                )
            os.remove(path)

        page.on("download", handle_download)

        try:
            if method == "POST" and post_data:
                await page.goto(
                    url,
                    method=method,
                    post_data=post_data,
                    wait_until="networkidle",
                    timeout=120000,
                )
            else:
                await page.goto(url, wait_until="networkidle", timeout=120000)

            # attemt to close cookiebanner
            if cookiebanner:
                await hide_cookie_banners(page)
            await page.wait_for_load_state("networkidle", timeout=120000)
        except PlaywrightTimeoutError:
            logs.append({"console_message": "Navigation timed out"})

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
        # attemt to close cookiebanner

        # Capture screenshot
        screenshot = await page.screenshot()
        image = Image.open(io.BytesIO(screenshot))
        full_optimized = optimize_image(image, quality=85)
        thumbnail_image = create_thumbnail(image, max_size=450)
        screenshot_b64 = base64.b64encode(full_optimized).decode("utf-8")
        thumbnail_b64 = base64.b64encode(thumbnail_image).decode("utf-8")

        # Close context to save video
        await context.close()
        await browser.close()

        # Retrieve video path
        video_file_path = await page.video.path()

        # Read and encode the video file
        with open(video_file_path, "rb") as video_file:
            video_base64 = base64.b64encode(video_file.read()).decode("utf-8")

        # Clean up the video file
        os.remove(video_file_path)

        response_data = {
            "redirects": redirects,
            "page_title": title,
            "meta_description": meta_description,
            "network_data": network_data,
            "logs": logs,
            "cookies": cookies,
            "performance_metrics": performance_metrics,
            "screenshot": screenshot_b64,
            "thumbnail": thumbnail_b64,
            "downloaded_files": downloaded_files,
            "video": video_base64,
        }

        serialized_response_data = json.dumps(response_data)
        cache.set(cache_key, serialized_response_data, expire=CACHE_EXPIRATION_SECONDS)
        return JSONResponse(content=response_data)


@app.get("/screenshot", response_model=ScreenshotResponse, status_code=200)
async def screenshotter(
    url: str,
    full_page: bool = Query(False),
    live: bool = Query(False),
    thumbnail_size: int = 450,
    quality: int = 85,
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
    cache_key = generate_cache_key(f"{url}_{full_page}")

    if not live and cache_key in cache:
        return JSONResponse(content=cache[cache_key])

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        screenshot = await page.screenshot(full_page=full_page)
        await browser.close()

        image = Image.open(io.BytesIO(screenshot))
        full_optimized = optimize_image(image, quality=quality)
        thumbnail_image = create_thumbnail(image, max_size=thumbnail_size)
        screenshot_b64 = base64.b64encode(full_optimized).decode("utf-8")
        thumbnail_b64 = base64.b64encode(thumbnail_image).decode("utf-8")
        images = {
            "url": page.url,
            "screenshot": screenshot_b64,
            "thumbnail": thumbnail_b64,
        }

    if not live:
        cache.set(cache_key, images, expire=CACHE_EXPIRATION_SECONDS)

    return JSONResponse(content=images)


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

    cache_key = generate_cache_key(html)
    if cache_key in cache:
        return JSONResponse(content={"minified_html": cache[cache_key]})

    minified_html = htmlmin.minify(html, remove_comments=True, remove_empty_space=True)
    cache.set(cache_key, minified_html, expire=CACHE_EXPIRATION_SECONDS)
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
    cache_key = generate_cache_key(html)

    if cache_key in cache:
        return JSONResponse(content={"text": cache[cache_key]})

    soup = BeautifulSoup(html, "html.parser")
    text_content = soup.get_text(separator=" ", strip=True)
    cache.set(cache_key, text_content, expire=CACHE_EXPIRATION_SECONDS)
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

    doc = Document(html)
    reader_content = doc.summary()
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

    markdown_converter = html2text.HTML2Text()
    markdown_converter.ignore_links = False
    markdown_content = markdown_converter.handle(html)

    return MarkdownResponse(markdown=markdown_content)


@app.get("/video", response_class=FileResponse)
async def video(
    url: str,
    browser_name: str = "chromium",
    width: int = Query(1280),
    height: int = Query(720),
):
    """
    Browse a webpage, record a video of the session, and return the video file to play in the browser.

    ### Parameters:
    - **url**: (str) The URL of the webpage to browse.
    - **browser_name**: (str) The browser to use (chromium, firefox, webkit). Defaults to "chromium".
    - **width**: (int) Video width. Defaults to 1280.
    - **height**: (int) Video height. Defaults to 720.

    ### Returns:
    - The recorded video file of the browsing session.
    """

    async with async_playwright() as p:
        browser_type = getattr(p, browser_name, None)
        if browser_type is None:
            raise HTTPException(
                status_code=400, detail=f'Browser "{browser_name}" is not supported'
            )

        video_dir = os.path.join(os.getcwd(), "videos")
        os.makedirs(video_dir, exist_ok=True)
        video_filename = url_to_sha256_filename(url)

        browser = await browser_type.launch(headless=True)
        context = await browser.new_context(
            record_video_dir=video_dir,
            record_video_size={"width": width, "height": height},
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle")
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error navigating to the page: {str(e)}"
            )

        await context.close()
        video_path = await page.video.path()
        await browser.close()
        return FileResponse(
            video_path, media_type="video/webm", filename=video_filename
        )
