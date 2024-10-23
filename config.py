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
