# Scraproxy (Working Title)

Scraproxy is a small API built around Playwright, allowing you to take screenshots of websites through an API with support for image optimization, authentication via API keys, and flexible response formatting.

## Features

- Screenshot: Capture screenshots of web pages (full page or viewport).
- Image Optimization: Return optimized versions of the screenshot, including a full-sized image, a smaller image, and a thumbnail.
- Bearer Token Authentication: Secure your API with an optional API key that is passed as a Bearer token in the Authorization header.
- Flexible Image Settings: Customize image dimensions, quality, and thumbnail size via query parameters.
- Compression: Responses are automatically compressed with Brotli or Gzip.

## Table of Contents

1. Requirements
2. Installation
3. Usage
4. API Endpoints
5. Building and Running with Docker
6. Environment Variables
7. Example Requests
8. Contributing
9. License

## Requirements

- Python 3.11
- Docker (for containerization)
- Playwright (for browser automation)
- Pillow (for image optimization)

## Installation

### 1. Clone the repository:

```bash
git clone https://github.com/StasonJatham/scraproxy.git
cd scraproxy
```

### 2. Install Python dependencies:

Create a virtual environment and install the required packages:

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Install Playwright and its dependencies:

```bash
playwright install --with-deps chromium
```

## Usage

To start the API locally, run the following command after activating your virtual environment:

```bash
python main.py
```

The API will run at `http://localhost:5000`.

### API Endpoints

#### 1. `/screenshot` (GET)

This endpoint takes a screenshot of the specified URL and returns multiple image formats (full-sized, small, and thumbnail) as base64-encoded strings.

##### Query Parameters:

- url (required): The URL of the website to capture.
- full (optional): Set full=true to capture the entire page. Default is false (visible viewport only).
- width (optional): Custom width for the resized screenshot.
- height (optional): Custom height for the resized screenshot.
- quality (optional): JPEG quality for optimized images (default is 85).
- thumbnail_size (optional): Maximum size for the thumbnail image (default is 450).

##### Example Request:

```
GET /screenshot?url=https://example.com&full=true&width=800&height=600&thumbnail_size=300
```

Response:

```
{
  "url": "https://example.com",
  "full_screenshot": "<base64-encoded full screenshot>",
  "small_screenshot": "<base64-encoded small screenshot>",
  "thumbnail_screenshot": "<base64-encoded thumbnail screenshot>"
}
```

## Building and Running with Docker

### 1. Build the Docker Image

To build the Docker image, run the following command in the root directory of the project:

```bash
docker build -t scraproxy .
```

### 2. Run the Docker Container

Run the container with port mapping and optional API key:

```bash
docker run -p 5000:5000 -e API_KEY="my_secure_api_key" scraproxy
```

This will start the API at `http://localhost:5000`. You can now interact with the API as described in the Usage section.

#### Environment Variables

- API_KEY: (Optional) If set, API requests must include this API key in the Authorization: Bearer `<token>` header for authentication.
- PLAYWRIGHT_BROWSERS_PATH: Path to the browsers for Playwright. Set to 0 to let Playwright handle browser paths inside Docker.

#### Example:

To run the container with an API key:

```bash
docker run -p 5000:5000 -e API_KEY="your_api_key_here" scraproxy
```

To run the container without API key authentication:

```bash
docker run -p 5000:5000 scraproxy
```

#### Example Requests

##### 1. With Bearer Token Authentication:

```bash
curl -H "Authorization: Bearer my_secure_api_key" "http://localhost:5000/screenshot?url=https://example.com"
```

##### 2. Without Authentication (if no API key is set):

```bash
curl "http://localhost:5000/screenshot?url=https://example.com"
```

## Notes:

- The API will skip API key validation if API_KEY is not set or is at the default value.
- For performance optimization, images are automatically compressed before being sent in the response.
