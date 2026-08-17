"""路由共享依赖:状态访问与 APK 前置校验。"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request

from .state import AppState


def get_state(request: Request) -> AppState:
    return request.app.state.amt


def need_apk(state: AppState) -> str:
    """校验并返回可用的 APK 路径,不满足则抛 400。"""
    p = (state.settings.get("apk_path") or "").strip()
    if not os.path.exists(p):
        raise HTTPException(400, f"APK 文件不存在: {p}（请在配置中设置正确路径）")
    return p
