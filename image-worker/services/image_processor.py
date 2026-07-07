import io
import logging
from typing import Tuple

from PIL import Image

logger = logging.getLogger(__name__)

THUMBNAIL_MAX_SIZE = (320, 320)
JPEG_QUALITY = 85


def process_image(data: bytes, content_type: str) -> Tuple[bytes, str]:
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB") if image.mode not in ("RGB", "RGBA") else image
        if image.mode == "RGBA":
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])
            image = background

        image.thumbnail(THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)

        output = io.BytesIO()
        save_format = "JPEG"
        output_content_type = "image/jpeg"
        if content_type == "image/png":
            save_format = "PNG"
            output_content_type = "image/png"
        elif content_type == "image/webp":
            save_format = "WEBP"
            output_content_type = "image/webp"

        if save_format == "JPEG":
            image.save(output, format=save_format, quality=JPEG_QUALITY, optimize=True)
        else:
            image.save(output, format=save_format, optimize=True)

        return output.getvalue(), output_content_type
