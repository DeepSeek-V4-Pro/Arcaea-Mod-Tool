"""素材路由:目录扫描、目录缓存、原始/缩略图/文本读取。"""

from __future__ import annotations

import io
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from core.catalog import find_entry, read_asset

from .. import config as app_config
from ..deps import get_state, need_apk
from ..mime import guess_mime
from ..state import AppState

router = APIRouter(tags=["assets"])

# 支持生成缩略图的格式
THUMB_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


@router.post("/api/scan")
def scan(state: AppState = Depends(get_state)):
    cat = state.scan(need_apk(state))
    return {"ok": True, "total": cat["total"], "sub_counts": cat["sub_counts"]}


@router.get("/api/catalog")
def catalog(state: AppState = Depends(get_state)):
    return state.get_catalog(need_apk(state))


@router.get("/api/asset/raw")
def asset_raw(path: str, range: str | None = None, state: AppState = Depends(get_state)):
    """原始字节读取,支持 HTTP Range(用于大图分段加载)。"""
    p = need_apk(state)
    e = find_entry(p, path)
    if e is None:
        raise HTTPException(404, f"条目不存在: {path}")
    total = e.usize
    start, end = 0, total - 1
    if range:
        m = range.removeprefix("bytes=").split("-")
        try:
            start = int(m[0]) if m[0] else 0
            if len(m) > 1 and m[1]:
                end = min(int(m[1]), total - 1)
        except ValueError:
            raise HTTPException(416)
    if start > end or start >= total:
        raise HTTPException(416)
    data = read_asset(p, path)
    if data is None:
        raise HTTPException(404)
    chunk = data[start:end + 1]
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(len(chunk)),
        "Content-Type": guess_mime(path),
        "Cache-Control": "public, max-age=3600",
    }
    if range:
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
        return Response(chunk, status_code=206, headers=headers)
    return Response(chunk, headers=headers)


@router.get("/api/asset/thumb")
def asset_thumb(path: str, max: int = 256, state: AppState = Depends(get_state)):
    """图片缩略图(JPEG,磁盘缓存)。"""
    from PIL import Image

    p = need_apk(state)
    e = find_entry(p, path)
    if e is None or os.path.splitext(path)[1].lower() not in THUMB_EXTS:
        raise HTTPException(404)
    os.makedirs(app_config.THUMB_DIR, exist_ok=True)
    key = f"{len(path)}-{path}-{e.usize}-{max}".replace("/", "_")
    cache = os.path.join(app_config.THUMB_DIR, key + ".jpg")
    if not os.path.exists(cache):
        data = read_asset(p, path)
        img = Image.open(io.BytesIO(data))
        img.thumbnail((max, max), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(cache, "JPEG", quality=82)
    return FileResponse(cache, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/api/asset/text")
def asset_text(path: str, limit: int = 200000, state: AppState = Depends(get_state)):
    """文本预览(截断到 limit 字节)。"""
    p = need_apk(state)
    e = find_entry(p, path)
    if e is None:
        raise HTTPException(404)
    data = read_asset(p, path)
    try:
        text = data[:limit].decode("utf-8", errors="replace")
    except Exception:
        text = ""
    return {"path": path, "size": len(data), "text": text, "truncated": len(data) > limit}
