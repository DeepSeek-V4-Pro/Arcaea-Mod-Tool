"""补丁路由:替换内容的上传 / 文本编辑 / 图片处理预览。"""

from __future__ import annotations

import base64
import io
import json
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from core.catalog import find_entry

from ..deps import get_state, need_apk
from ..mime import guess_mime
from ..state import AppState

router = APIRouter(tags=["patches"])


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
        orig = find_entry(need_apk(state), path)
        if orig and img_settings.get("keep_size"):
            try:
                from PIL import Image
                im = Image.open(io.BytesIO(data))
                img_settings["orig_w"], img_settings["orig_h"] = im.size
            except Exception:
                pass
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
    orig = find_entry(need_apk(state), body.get("path", ""))
    if orig and settings.get("keep_size"):
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(raw))
            settings["orig_w"], settings["orig_h"] = im.size
        except Exception:
            pass
    out = state.patches.process_image(raw, body.get("orig_ext", ".png"), settings)
    return {"data": base64.b64encode(out).decode()}
