"""路由共享依赖:状态访问与 APK 前置校验。"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request

from . import config as app_config
from .state import AppState


def get_state(request: Request) -> AppState:
    return request.app.state.amt


def need_apk(state: AppState) -> str:
    """校验并返回可用的 APK 路径,不满足则抛 400。

    配置路径缺失时每次实时回退 input/ 目录识别——用户把原包丢进
    input/ 后无需重启、无需改配置即可直接使用。
    """
    p = app_config.resolve_apk(state.settings.get("apk_path") or "")
    if not p or not os.path.exists(p):
        raise HTTPException(
            400, "未找到 APK:请将原版 APK 放入项目 input/ 目录,或在「配置」中手动填写路径")
    return p
