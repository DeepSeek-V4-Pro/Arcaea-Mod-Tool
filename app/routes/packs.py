"""补丁包路由:导出 / 导入 mod pack zip。"""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, File, UploadFile

from core.patches import export_pack, import_pack

from .. import config as app_config
from ..deps import get_state
from ..state import AppState

router = APIRouter(tags=["packs"])


@router.post("/api/pack/export")
def pack_export(state: AppState = Depends(get_state)):
    os.makedirs(app_config.PACK_DIR, exist_ok=True)
    out = os.path.join(app_config.PACK_DIR, f"modpack_{uuid.uuid4().hex[:8]}.zip")
    export_pack(state.patches, out)
    return {"file": out, "size": os.path.getsize(out)}


@router.post("/api/pack/import")
async def pack_import(file: UploadFile = File(...), state: AppState = Depends(get_state)):
    os.makedirs(app_config.PACK_DIR, exist_ok=True)
    tmp = os.path.join(app_config.PACK_DIR, "import_" + uuid.uuid4().hex[:8] + ".zip")
    with open(tmp, "wb") as f:
        f.write(await file.read())
    try:
        n = import_pack(state.patches, tmp)
    finally:
        os.remove(tmp)
    return {"ok": True, "imported": n}
