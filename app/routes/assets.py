"""素材路由:目录扫描、目录缓存、原始/缩略图/文本读取、素材导出。"""

from __future__ import annotations

import io
import os
import uuid
import zipfile
import zlib

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

from core.catalog import find_entry
from core.zipio import read_central_directory, read_entry_data

from .. import config as app_config
from ..deps import get_state, need_apk, need_pick
from ..mime import guess_mime
from ..state import AppState

router = APIRouter(tags=["assets"])

# 支持生成缩略图的格式
THUMB_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


@router.post("/api/scan")
def scan(state: AppState = Depends(get_state)):
    pick = need_pick(state)
    cat = state.scan(pick["path"], pick["platform"])
    return {"ok": True, "total": cat["total"], "sub_counts": cat["sub_counts"],
            "platform": pick["platform"], "pkg_source": pick["source"]}


@router.get("/api/catalog")
def catalog(state: AppState = Depends(get_state)):
    pick = need_pick(state)
    return state.get_catalog(pick["path"], pick["platform"])


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
    data = read_entry_data(p, e)
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
def asset_thumb(request: Request, path: str, max: int = 256,
                state: AppState = Depends(get_state)):
    """图片缩略图(JPEG,磁盘缓存 + ETag 条件请求)。

    注意:URL 长期不变(路径+max),若带长 max-age 缓存,后端更换生成规则后
    浏览器会一直命中旧图;这里用 no-cache + ETag,304 开销极小且永远新鲜。
    """
    from PIL import Image

    p = need_apk(state)
    e = find_entry(p, path)
    if e is None or os.path.splitext(path)[1].lower() not in THUMB_EXTS:
        raise HTTPException(404)
    os.makedirs(app_config.THUMB_DIR, exist_ok=True)
    # v3: 缩略图透明区为纯白底
    key = f"v3-{len(path)}-{path}-{e.usize}-{max}".replace("/", "_")
    cache = os.path.join(app_config.THUMB_DIR, key + ".jpg")
    if not os.path.exists(cache):
        data = read_entry_data(p, e)
        img = Image.open(io.BytesIO(data))
        img.thumbnail((max, max), Image.LANCZOS)
        if img.mode == "RGBA":
            # 透明 PNG:合成到白色底,避免转 RGB 时黑底
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(cache, "JPEG", quality=82)
    etag = f'"{os.path.getmtime(cache):.0f}-{os.path.getsize(cache)}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return FileResponse(cache, media_type="image/jpeg", headers={
        "Cache-Control": "public, max-age=0, must-revalidate",
        "ETag": etag,
    })


@router.get("/api/asset/text")
def asset_text(path: str, limit: int = 200000, state: AppState = Depends(get_state)):
    """文本预览(截断到 limit 字节)。"""
    p = need_apk(state)
    e = find_entry(p, path)
    if e is None:
        raise HTTPException(404)
    data = read_entry_data(p, e)
    try:
        text = data[:limit].decode("utf-8", errors="replace")
    except Exception:
        text = ""
    return {"path": path, "size": len(data), "text": text, "truncated": len(data) > limit}


# ------------------------------------------------------------------ 素材导出

@router.get("/api/asset/download")
def asset_download(path: str, state: AppState = Depends(get_state)):
    """单个素材下载(附件形式)。"""
    p = need_apk(state)
    e = find_entry(p, path)
    if e is None:
        raise HTTPException(404, f"条目不存在: {path}")
    data = read_entry_data(p, e)
    fname = os.path.basename(path) or "asset.bin"
    return Response(data, media_type=guess_mime(path), headers={
        "Content-Disposition": f'attachment; filename="{fname}"',
    })


@router.post("/api/assets/export")
def assets_export(body: dict, background_tasks: BackgroundTasks,
                  state: AppState = Depends(get_state)):
    """批量导出:按素材路径列表打包 zip(保留 APK 内路径结构)。

    性能:按条目在 APK 内的偏移排序后单次顺序读取,避免每个条目都随机 seek。
    个别读取失败的条目跳过,不中断整体导出。
    """
    paths = body.get("paths") or []
    if not paths:
        raise HTTPException(400, "没有要导出的素材")
    p = need_apk(state)
    entry_map = {e.name: e for e in read_central_directory(p)[0]}
    missing = [x for x in paths if x not in entry_map]
    if missing:
        raise HTTPException(400, f"{len(missing)} 个素材不存在,如: {missing[0]}")

    export_dir = os.path.join(app_config.DATA_DIR, "export")
    os.makedirs(export_dir, exist_ok=True)
    tmp = os.path.join(export_dir, f"assets_{uuid.uuid4().hex[:8]}.zip")
    entries = sorted((entry_map[x] for x in paths), key=lambda e: e.header_offset)
    # 素材多为已压缩格式(png/jpg),直接存储避免无谓压缩
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z, open(p, "rb") as fin:
        for e in entries:
            try:
                fin.seek(e.header_offset + 30 + e.local_fn_len + e.local_extra_len)
                raw = fin.read(e.csize)
                if e.method == 0:
                    data = raw
                elif e.method == 8:
                    data = zlib.decompress(raw, -15)
                else:
                    continue  # 不支持的压缩方式,跳过
            except Exception:
                continue
            z.writestr(e.name, data)
    background_tasks.add_task(os.remove, tmp)
    return FileResponse(tmp, media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="arcaea_assets.zip"'})
