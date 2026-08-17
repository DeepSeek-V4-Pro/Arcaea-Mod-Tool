"""Content-Type 猜测(供资源读取与补丁预览使用)。"""

from __future__ import annotations

import os

MIME_TABLE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".otf": "font/otf",
    ".ttf": "font/ttf",
}


def guess_mime(path: str) -> str:
    return MIME_TABLE.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
