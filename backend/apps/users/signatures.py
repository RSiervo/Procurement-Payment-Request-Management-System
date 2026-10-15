"""E-signature images: checking what people upload, and taking snapshots of them.

An uploaded signature is never stored as received. It is opened as an image and
re-drawn as a fresh PNG of bounded size, which removes embedded metadata and anything
that is not picture data. Approvals and submissions keep their own copy of the
signature used at that moment, so replacing a signature later never changes a form
that was already signed.
"""

import io
import uuid

from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

MAX_BYTES = 2 * 1024 * 1024
MAX_SIZE = (600, 240)        # pixels; plenty for a signature printed about 35 mm wide
MIN_SIZE = (40, 15)
ALLOWED_FORMATS = {"PNG", "JPEG"}


def _error(message):
    return ValidationError({"file": [message]})


def normalise(upload):
    """Return a clean PNG (as a ContentFile with a random name) made from an uploaded image."""
    if upload is None:
        raise _error("Choose an image of your signature.")
    if upload.size > MAX_BYTES:
        raise _error("The image is too large. Use a file under 2 MB.")
    data = upload.read()
    try:
        Image.open(io.BytesIO(data)).verify()   # structural check; the image must be reopened afterwards
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise _error("This file is not a valid image. Upload a PNG or JPG of your signature.") from None
    if image.format not in ALLOWED_FORMATS:
        raise _error("Upload your signature as a PNG or JPG image.")
    if image.width < MIN_SIZE[0] or image.height < MIN_SIZE[1]:
        raise _error("The image is too small to print clearly. Use a larger picture of your signature.")

    image = image.convert("RGBA")
    image.thumbnail(MAX_SIZE)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return ContentFile(out.getvalue(), name=f"{uuid.uuid4().hex}.png")


def snapshot(field):
    """A copy of a stored signature, to keep with the record it signed. None if there is none."""
    if not field:
        return None
    with field.open("rb") as source:
        return ContentFile(source.read(), name=f"{uuid.uuid4().hex}.png")
