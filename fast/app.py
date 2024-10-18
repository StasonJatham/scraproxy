from fastapi import FastAPI, Depends, HTTPException, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright
import hashlib
import base64
import os
from bs4 import BeautifulSoup
import htmlmin
from diskcache import Cache
from PIL import Image
import io

# Initialize FastAPI app
app = FastAPI()

# Initialize disk cache
cache = Cache("./cache_dir")
CACHE_EXPIRATION_SECONDS = 3600

# API key from environment
API_KEY = "none"  # os.environ.get("API_KEY")

if not API_KEY or API_KEY == "none":
    security = None
else:
    security = HTTPBearer()


# Helper function to generate cache keys
def generate_cache_key(data):
    return hashlib.md5(data.encode("utf-8")).hexdigest()


@app.post("/browse")
async def browse(
    url: str = Form(...),
    method: str = "GET",
    post_data: str = None,
    browser_name: str = "chromium",
    # credentials: HTTPAuthorizationCredentials = Depends(security),
):
    cache_key = generate_cache_key(f"{url}-{method}-{post_data}-{browser_name}")

    # Check if the result is already cached
    if cache_key in cache:
        return JSONResponse(content=cache[cache_key])

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
        performance_metrics = {}
        downloaded_files = []

        # Track requests and responses with timings
        def log_request(request):
            timing = request.timing
            network_data.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "timing": {
                        "start_time": timing["startTime"],
                        "request_time": timing["requestTime"],
                    },
                }
            )

        def log_response(response):
            request = response.request
            network_data.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "timing": response.timing,
                    "request_headers": dict(request.headers),
                    "response_headers": dict(response.headers()),
                }
            )

        def log_console(msg):
            logs.append({"console_message": msg.text()})

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
        if method == "POST" and post_data:
            await page.goto(url, method=method, post_data=post_data)
        else:
            await page.goto(url)

        # Capture page information
        title = await page.title()
        meta_description = (
            await page.locator("meta[name='description']").get_attribute("content")
            or "No Meta Description"
        )
        performance_timing = await page.evaluate("window.performance.timing.toJSON()")
        performance_metrics["performance_timing"] = performance_timing

        cookies = await context.cookies()
        viewport_size = await page.viewport_size()
        screenshot = await page.screenshot()

        # Collect the response data
        response_data = {
            "page_title": title,
            "meta_description": meta_description,
            "network_data": network_data,
            "logs": logs,
            "cookies": cookies,
            "viewport_size": viewport_size,
            "performance_metrics": performance_metrics,
            "screenshot": base64.b64encode(screenshot).decode("utf-8"),
            "downloaded_files": downloaded_files,
        }

        # Cache the response
        cache.set(cache_key, response_data, expire=CACHE_EXPIRATION_SECONDS)
        await browser.close()
        return JSONResponse(content=response_data)


# Endpoint 2: Screenshot of URL
@app.get("/screenshot")
async def screenshotter(
    url: str,
    full_page: bool = False,
    # credentials: HTTPAuthorizationCredentials = Depends(security),
):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url)
        screenshot = await page.screenshot(full_page=full_page)
        await browser.close()

        # Process screenshot
        screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")

    return JSONResponse(content={"screenshot": screenshot_b64})


# Helper function to optimize image
def optimize_image(image, width=None, height=None, quality=85):
    if width and height:
        image = image.resize((width, height), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


# Endpoint 3: Minimize the HTML
@app.post("/minimize")
async def minimize_html(
    html: str = Form(...),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    cache_key = generate_cache_key(html)
    if cache_key in cache:
        return JSONResponse(content={"minified_html": cache[cache_key]})

    minified_html = htmlmin.minify(html, remove_comments=True, remove_empty_space=True)
    cache.set(cache_key, minified_html, expire=CACHE_EXPIRATION_SECONDS)
    return JSONResponse(content={"minified_html": minified_html})


# Endpoint 4: Extract text from HTML
@app.post("/extract_text")
async def extract_text_from_html(
    html: str = Form(...),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    cache_key = generate_cache_key(html)
    if cache_key in cache:
        return JSONResponse(content={"text": cache[cache_key]})

    soup = BeautifulSoup(html, "html.parser")
    text_content = soup.get_text(separator=" ", strip=True)
    cache.set(cache_key, text_content, expire=CACHE_EXPIRATION_SECONDS)
    return JSONResponse(content={"text": text_content})
