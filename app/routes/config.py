"""配置路由:APK 路径 / 输出目录。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import config as app_config
from ..deps import get_state
from ..state import AppState

router = APIRouter(tags=["config"])


@router.get("/api/config")
def get_config(state: AppState = Depends(get_state)):
    return state.settings


@router.put("/api/config")
def put_config(body: dict, state: AppState = Depends(get_state)):
    for k in ("apk_path", "output_dir"):
        if k in body and body[k]:
            state.settings[k] = str(body[k])
    app_config.save_settings(state.settings)
    return state.settings
