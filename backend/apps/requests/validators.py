import os

from rest_framework.exceptions import ValidationError

from apps.core.models import SystemConfig

_ZIP = b"PK\x03\x04"
_OLE = b"\xd0\xcf\x11\xe0"

# extension -> (content type served back, accepted leading bytes; None = plain text)
ALLOWED_FILES = {
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".webp": ("image/webp", (b"RIFF",)),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", (_ZIP,)),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (_ZIP,)),
    ".doc": ("application/msword", (_OLE,)),
    ".xls": ("application/vnd.ms-excel", (_OLE,)),
    ".csv": ("text/csv", None),
    ".txt": ("text/plain", None),
}
INLINE_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp"}


def validate_upload(upload):
    """Check extension, size and file signature. Returns (clean name, content type).

    The content type is derived from the extension we verified, never from the
    client-supplied header.
    """
    name = os.path.basename(upload.name or "").replace("\x00", "").strip()
    ext = os.path.splitext(name)[1].lower()
    if not name or ext not in ALLOWED_FILES:
        allowed = ", ".join(sorted(e.lstrip(".").upper() for e in ALLOWED_FILES))
        raise ValidationError({"file": [f"This file type is not allowed. Allowed types: {allowed}."]})

    limit_mb = SystemConfig.load().max_upload_mb
    if upload.size > limit_mb * 1024 * 1024:
        raise ValidationError({"file": [f"File is too large. The maximum size is {limit_mb} MB."]})
    if upload.size == 0:
        raise ValidationError({"file": ["The file is empty."]})

    content_type, signatures = ALLOWED_FILES[ext]
    head = upload.read(2048)
    upload.seek(0)
    if signatures is None:
        if b"\x00" in head:
            raise ValidationError({"file": ["The file content does not match its extension."]})
    elif not head.startswith(signatures):
        raise ValidationError({"file": ["The file content does not match its extension."]})
    return name[:255], content_type
