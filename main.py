from flask import Flask, request, jsonify, abort
from flask_compress import Compress
from playwright.sync_api import sync_playwright
import base64
import json
import os
import shutil
import hashlib
import threading
from functools import wraps
import time
from PIL import Image
import io

app = Flask(__name__)
Compress(app)

cache = {}
cache_lock = threading.Lock()
CACHE_MAX_SIZE = 100  # Max number of cached items
CACHE_EXPIRATION = 300  # Cache expiration in seconds
API_KEY = os.environ.get("API_KEY")


@app.before_request
def check_api_key():
    """Middleware to check if the correct API_KEY is passed in the request header."""

    if not API_KEY or API_KEY == "none":
        return  # Skip authentication check

    auth_header = request.headers.get("Authorization")

    if not auth_header:
        abort(401, description="Authorization header missing")

    if not auth_header.startswith("Bearer "):
        abort(401, description="Invalid authorization header format")

    token = auth_header.split(" ")[1]

    if token != API_KEY:
        abort(403, description="Invalid API key (Bearer token)")


def parse_parameters(req):
    if req.method == "POST":
        data = req.get_json()
    else:
        data = req.args.to_dict()

    url = data.get("url")
    method = data.get("method", "GET").upper()
    post_data = data.get("postData")
    browser_name = data.get("browser", "chromium").lower()
    extensions = data.get("extensions", [])

    if isinstance(extensions, str):
        try:
            extensions = json.loads(extensions)
        except json.JSONDecodeError:
            extensions = extensions.split(",")

    if req.method == "GET" and post_data:
        post_data = base64.b64decode(post_data).decode("utf-8")

    return url, method, post_data, browser_name, extensions


def generate_cache_key(url, method, post_data, browser_name, extensions):
    key_data = {
        "url": url,
        "method": method,
        "post_data": post_data,
        "browser_name": browser_name,
        "extensions": extensions,
    }
    key_string = json.dumps(key_data, sort_keys=True)
    return hashlib.md5(key_string.encode("utf-8")).hexdigest()


def cache_response(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        cache_key = kwargs.get("cache_key")
        if not cache_key:
            return func(*args, **kwargs)

        # Check cache
        with cache_lock:
            cache_entry = cache.get(cache_key)
            if cache_entry:
                if time.time() - cache_entry["timestamp"] < CACHE_EXPIRATION:
                    return cache_entry["response"]
                else:
                    del cache[cache_key]  # Remove expired cache entry

        # Get response and store in cache
        response = func(*args, **kwargs)
        with cache_lock:
            if len(cache) >= CACHE_MAX_SIZE:
                # Remove the oldest cache entry
                oldest_key = min(cache.keys(), key=lambda k: cache[k]["timestamp"])
                del cache[oldest_key]
            cache[cache_key] = {"response": response, "timestamp": time.time()}

        return response

    return wrapper


@app.route("/browse", methods=["GET", "POST"])
def browse():
    try:
        url, method, post_data, browser_name, extensions = parse_parameters(request)

        if not url:
            return jsonify({"error": "URL is required"}), 400

        cache_key = generate_cache_key(url, method, post_data, browser_name, extensions)

        # Call the processing function with caching
        response_data = process_request(
            url=url,
            method=method,
            post_data=post_data,
            browser_name=browser_name,
            extensions=extensions,
            cache_key=cache_key,
        )

        return jsonify(response_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@cache_response
def process_request(url, method, post_data, browser_name, extensions, cache_key=None):
    with sync_playwright() as p:
        # Select the browser
        if browser_name == "chromium":
            browser_type = p.chromium
        elif browser_name == "firefox":
            browser_type = p.firefox
        elif browser_name == "webkit":
            browser_type = p.webkit
        else:
            return {"error": f'Browser "{browser_name}" is not supported'}

        # Set up download directory
        download_dir = os.path.join(os.getcwd(), "downloads")
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        # Browser launch options
        launch_options = {
            "headless": True,
            "downloads_path": download_dir,
        }

        browser = browser_type.launch(**launch_options)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        network_data = []
        redirects = []
        request_map = {}

        # Track requests and responses
        def log_request(request):
            # Track the URL and request data in case it's redirected
            request_map[request.url] = {
                "method": request.method,
                "headers": dict(request.headers),
                "post_data": request.post_data,
            }

        def log_response(response):
            try:
                request = response.request
                response_headers = dict(response.all_headers())
                request_headers = dict(request.headers)
                status_code = response.status

                # Capture response body and size, but handle errors for redirects
                response_body = None
                response_size = 0
                try:
                    content_type = response_headers.get("content-type", "")
                    if "text" in content_type or "json" in content_type:
                        response_body = response.text()
                        response_size = len(response_body)
                    else:
                        response_body = base64.b64encode(response.body()).decode(
                            "utf-8"
                        )
                        response_size = len(response.body())
                except Exception:
                    response_body = "Response body unavailable (possibly a redirect)"
                    response_size = 0

                # Append detailed network data including request and response information
                network_data.append(
                    {
                        "url": response.url,
                        "method": request.method,
                        "security": response.security_details(),
                        "server": response.server_addr(),
                        "request_headers": request_headers,
                        "request_body": request.post_data,
                        "status_code": status_code,
                        "response_headers": response_headers,
                        "response_body": response_body,
                        "response_size": response_size,
                        "cookies": context.cookies(),
                    }
                )

                # Track redirects based on 3xx status codes
                if 300 <= status_code < 400:
                    location = response_headers.get("location")
                    if location:
                        # Add numbered redirects
                        redirects.append(
                            {
                                "step": len(redirects) + 1,
                                "from": response.url,
                                "to": location,
                                "status_code": status_code,
                            }
                        )
                        # Update the request map with the redirect location
                        request_map[location] = request_map.get(request.url, {})
            except Exception as e:
                print(f"Error logging response: {e}")

        page.on("request", log_request)
        page.on("response", log_response)

        # Navigate to the URL
        if method == "POST" and post_data:
            response = page.request.post(url, data=post_data)
            page.goto(response.url)
        else:
            page.goto(url, wait_until="networkidle")

        # Wait for downloads to complete (if any)
        # Alternatively, you can use event handlers for download events

        # Take screenshot
        screenshot = page.screenshot()

        # Collect downloaded files
        downloaded_files = []
        for root, dirs, files in os.walk(download_dir):
            for file in files:
                file_path = os.path.join(root, file)
                with open(file_path, "rb") as f:
                    file_content = base64.b64encode(f.read()).decode("utf-8")
                    downloaded_files.append(
                        {"file_name": file, "file_content": file_content}
                    )
                os.remove(file_path)  # Remove the file after reading
        shutil.rmtree(download_dir)  # Clean up the download directory

        browser.close()

        response_data = {
            "redirects": redirects,
            "network_data": network_data,
            "screenshot": base64.b64encode(screenshot).decode("utf-8"),
            "downloaded_files": downloaded_files,
        }

        return response_data


@app.route("/screenshot", methods=["GET"])
def screenshotter():
    url = request.args.get("url")
    full_page = request.args.get("full", "false").lower() == "true"

    custom_width = request.args.get("width", type=int)
    custom_height = request.args.get("height", type=int)
    custom_quality = request.args.get("quality", type=int, default=85)
    thumbnail_size = request.args.get("thumbnail_size", type=int, default=450)

    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        with sync_playwright() as p:
            launch_options = {
                "headless": True,
            }

            browser = p.chromium.launch(**launch_options)
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, wait_until="networkidle")
            acutal_url = page.evaluate("location.href")
            screenshot = page.screenshot(full_page=full_page)
            browser.close()

            image = Image.open(io.BytesIO(screenshot))
            full_optimized = optimize_image(image, quality=custom_quality)

            if custom_width and custom_height:
                small_image = optimize_image(
                    image,
                    width=custom_width,
                    height=custom_height,
                    quality=custom_quality,
                )
            else:
                small_image = None

            thumbnail_image = create_thumbnail(image, max_size=thumbnail_size)

            return jsonify(
                {
                    "url": url,
                    "final_url": acutal_url,
                    "full_screenshot": base64.b64encode(full_optimized).decode("utf-8"),
                    "small_screenshot": base64.b64encode(small_image).decode("utf-8")
                    if small_image
                    else None,
                    "thumbnail_screenshot": base64.b64encode(thumbnail_image).decode(
                        "utf-8"
                    ),
                }
            )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def optimize_image(image, width=None, height=None, quality=85):
    """
    Resizes and optimizes an image using Pillow.
    - If width and height are None, the image is optimized in its original size.
    - Otherwise, the image is resized to the given width and height.
    """
    if width and height:
        image = image.resize((width, height), Image.Resampling.LANCZOS)

    # Convert the image to JPEG and optimize it
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def create_thumbnail(image, max_size):
    """
    Creates a thumbnail using Pillow's thumbnail method, maintaining aspect ratio.
    The image will fit within a (max_size x max_size) box while keeping proportions.
    """
    img_copy = image.copy()
    img_copy.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    # Convert the thumbnail to JPEG and optimize it
    buffer = io.BytesIO()
    img_copy.save(buffer, format="JPEG", quality=85, optimize=True)
    return buffer.getvalue()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
