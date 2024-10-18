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
        return True
    else:
        return False


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


def generate_cache_key(data):
    return hashlib.md5(data.encode("utf-8")).hexdigest()
