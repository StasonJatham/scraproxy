from PIL import Image
import hashlib
import io
import os
from dotenv import load_dotenv


def load_env_file(env_file=".env"):
    """
    Checks for the presence of a .env file and loads its contents
    into environment variables.

    Args:
        env_file (str): The path to the .env file (default is '.env').

    Returns:
        bool: True if the .env file was found and loaded, False otherwise.
    """
    if os.path.exists(env_file):
        load_dotenv(env_file)
        print(f"{env_file} loaded successfully.")
        return True
    else:
        print(f"{env_file} file not found.")
        return False


# Helper function to optimize image
def optimize_image(image, width=None, height=None, quality=85):
    if width and height:
        image = image.resize((width, height), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def generate_cache_key(data):
    return hashlib.md5(data.encode("utf-8")).hexdigest()
