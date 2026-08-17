"""补丁路由:替换内容的上传 / 文本编辑 / 图片处理预览。"""

from __future__ import annotations

import base64
import io
import json
import os
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from core.catalog import find_entry, read_asset

from ..deps import get_state, need_apk
from ..mime import guess_mime
from ..state import AppState

router = APIRouter(tags=["patches"])

# 原素材像素尺寸缓存: (apk_path, asset_path) -> (w, h) | None
# 图片处理预览会随选项变化反复触发,避免每次都从大 APK 里解压原图读尺寸。
_orig_sizes: dict[tuple[str, str], tuple[int, int] | None] = {}

# 官方头像素材 = 正方形画布 + 内切菱形镂空(四角透明)
_ICON_RE = re.compile(r"^assets/char/.*_icon\.png$", re.IGNORECASE)
# 联机立绘:半身构图 + 底部渐变透明(截断处淡出)
_MP_RE = re.compile(r"^assets/char/[^/]*_mp\.png$", re.IGNORECASE)
# 联机立绘取源图顶部比例(实测官方 ≈ 原立绘上部 55%)
_MP_ZONE = 0.55


def _resolve_shape(path: str, settings: dict) -> dict:
    """确定图片形状/构图处理:settings 显式指定优先,否则按素材类型自动。

    shape: 'diamond'(菱形头像蒙版) | 'none' | 缺省(auto 识别)。
    fit_zone: 联机立绘自动半身裁切(0<z<1,源图顶部比例),显式给 1 可禁用。
    """
    if "shape" not in settings and _ICON_RE.match(path):
        settings["shape"] = "diamond"
    if "fit_zone" not in settings and _MP_RE.match(path):
        settings["fit_zone"] = _MP_ZONE
    return settings


def _fill_orig_size(apk: str, path: str, settings: dict):
    """把原素材的真实像素尺寸写入 settings(keep_size / fit 需要)。

    读不到时保持缺省:process_image 会安全地跳过对应处理。
    """
    if not (settings.get("keep_size") or settings.get("fit")):
        return
    key = (apk, path)
    if key not in _orig_sizes:
        try:
            from PIL import Image
            data = read_asset(apk, path)
            if data:
                im = Image.open(io.BytesIO(data))
                _orig_sizes[key] = im.size
            else:
                _orig_sizes[key] = None
        except Exception:
            _orig_sizes[key] = None
    size = _orig_sizes[key]
    if size:
        settings["orig_w"], settings["orig_h"] = size


@router.get("/api/patches")
def list_patches(state: AppState = Depends(get_state)):
    return state.patches.list()


@router.put("/api/patch")
async def put_patch(path: str = Form(...), file: UploadFile = File(...),
                    settings_json: str = Form("{}"),
                    state: AppState = Depends(get_state)):
    """上传替换文件;settings_json 为图片处理参数时先处理后存储。"""
    data = await file.read()
    if not data:
        raise HTTPException(400, "空文件")
    meta = {"source": "upload", "orig_name": file.filename or path}
    img_settings = {}
    try:
        img_settings = json.loads(settings_json or "{}")
    except Exception:
        img_settings = {}
    if img_settings:
        _resolve_shape(path, img_settings)
        orig = find_entry(need_apk(state), path)
        if orig:
            _fill_orig_size(need_apk(state), path, img_settings)
        data = state.patches.process_image(data, os.path.splitext(path)[1].lower(), img_settings)
        meta["note"] = "图片处理: " + json.dumps(img_settings, ensure_ascii=False)
        meta["settings"] = img_settings
    return state.patches.put_bytes(path, data, meta)


@router.post("/api/patch/text")
def put_patch_text(body: dict, state: AppState = Depends(get_state)):
    path = body.get("path", "")
    text = body.get("text", "")
    if not path:
        raise HTTPException(400, "缺少 path")
    return state.patches.put_text(path, text)


@router.delete("/api/patch")
def delete_patch(path: str, state: AppState = Depends(get_state)):
    ok = state.patches.remove(path)
    if not ok:
        raise HTTPException(404, "补丁不存在")
    return {"ok": True}


@router.post("/api/patch/enabled")
def patch_enabled(body: dict, state: AppState = Depends(get_state)):
    """启用/停用补丁(停用的不参与构建)。"""
    path = body.get("path", "")
    ok = state.patches.set_enabled(path, bool(body.get("enabled", True)))
    if not ok:
        raise HTTPException(404, "补丁不存在")
    return {"ok": True}


@router.get("/api/patch/bytes")
def patch_bytes(path: str, state: AppState = Depends(get_state)):
    data = state.patches.get_bytes(path)
    if data is None:
        raise HTTPException(404)
    return Response(data, media_type=guess_mime(path))


@router.post("/api/patch/process")
def process_preview(body: dict, state: AppState = Depends(get_state)):
    """图片处理预览(不落盘):base64 进 -> base64 出。"""
    raw = base64.b64decode(body.get("data", ""))
    settings = body.get("settings", {})
    _resolve_shape(body.get("path", ""), settings)
    orig = find_entry(need_apk(state), body.get("path", ""))
    if orig:
        _fill_orig_size(need_apk(state), body.get("path", ""), settings)
    out = state.patches.process_image(raw, body.get("orig_ext", ".png"), settings)
    return {"data": base64.b64encode(out).decode()}
