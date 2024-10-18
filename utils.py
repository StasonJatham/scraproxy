from PIL import Image
import hashlib
import io


# Helper function to optimize image
def optimize_image(image, width=None, height=None, quality=85):
    if width and height:
        image = image.resize((width, height), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def generate_cache_key(data):
    return hashlib.md5(data.encode("utf-8")).hexdigest()
