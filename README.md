# Scraproxy

This repository provides a high-performance web scraping API built with FastAPI and Playwright. It enables users to automate browsing, capture screenshots, minimize HTML, extract text, and even record videos of browsing sessions. The API supports various advanced features like network request/response tracking and cookie banner handling, making it ideal for automation, scraping, and content extraction.

## Features

- Browse Web Pages: Gather detailed information such as network data, logs, redirects, cookies, and performance metrics.
- Screenshots: Capture live screenshots or retrieve them from cache, with support for full-page screenshots and thumbnails.
- Minify HTML: Minimize HTML content by removing unnecessary elements like comments and whitespace.
- Extract Text: Extract clean, plain text from HTML content.
- Video Recording: Record a browsing session and retrieve the video as a webm file.
- Reader Mode: Extract the main readable content and title from an HTML page, similar to “reader mode” in browsers.
- Markdown Conversion: Convert HTML content into Markdown format.
- Authentication: Optional Bearer token authentication using API_KEY.

## Endpoints

### 1. /browse

Browse a webpage and retrieve various details like page title, meta description, network data, logs, cookies, and more.

### 2. /screenshot

Capture a screenshot of the specified URL, with support for full-page captures and thumbnails.

### 3. /minimize

Minimize HTML content by removing comments and unnecessary whitespace.

### 4. /extract_text

Extract plain text from the provided HTML content.

### 5. /reader

Extract the main readable content from an HTML page.

### 6. /markdown

Convert the provided HTML content into Markdown format.

### 7. /video

Record a video of a browsing session and return the video file in webm format. This allows for capturing the entire session from page load to interaction.

## Technology Stack

- FastAPI: For building high-performance, modern APIs.
- Playwright: For automating web browser interactions and scraping.
- Docker: Containerized for consistent environments and easy deployment.
- Diskcache: Efficient caching to reduce redundant scraping requests.
- Pillow: For image processing, optimization, and thumbnail creation.

## Setup

1. Clone the repository.
2. Create a .env file or set the necessary environment variables:
   - API_KEY (optional): For authentication.
   - CACHE_EXPIRATION_SECONDS: Cache expiration time in seconds (default is 3600).
   - PLAYWRIGHT_BROWSERS_PATH: (Optional) Set a custom path for Playwright browsers.
3. Build and run the Docker container:

`docker-compose up --build`

## Usage

1. To browse a webpage, send a GET request to /browse with the URL.
2. For screenshots, use the /screenshot endpoint, providing the target URL.
3. Use the /minimize and /extract_text endpoints to process raw HTML.
4. Use the /video endpoint to record and retrieve the video of a browsing session.
5. Use /reader to extract readable content and /markdown to convert HTML into Markdown format.
