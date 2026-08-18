"""配置路由:原包路径 / 输出目录 / 平台模式。

原包解析统一走 pick_pkg:配置路径优先(按文件类型判定平台),否则自动识别
input/ 目录(支持 *.apk / *.ipa / 外层 *.zip,跨平台时自动跟随)。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import config as app_config
from ..deps import get_state
from ..state import AppState

router = APIRouter(tags=["config"])


def _config_payload(state: AppState) -> dict:
    """生效配置:apk_path / platform 为解析后的生效值,附来源说明与 input/ 候选。"""
    out = dict(state.settings)
    try:
        pick = app_config.pick_pkg(
            out.get("apk_path") or "", out.get("platform") or "android")
    except ValueError as ex:
        pick = {"path": "", "platform": out.get("platform") or "android",
                "source": "", "display": "", "inner_ipa": None, "note": str(ex)}
    out["apk_path"] = pick["path"]
    out["platform"] = pick["platform"]
    out["pkg_source"] = pick["source"]
    out["pkg_display"] = pick["display"]
    out["pkg_note"] = pick["note"]
    out["input_candidates"] = app_config.input_candidates()
    return out


@router.get("/api/config")
def get_config(state: AppState = Depends(get_state)):
    return _config_payload(state)


@router.put("/api/config")
def put_config(body: dict, state: AppState = Depends(get_state)):
    # 允许清空:apk_path 置空 = 改回 input/ 目录自动识别
    for k in ("apk_path", "output_dir"):
        if k in body:
            state.settings[k] = str(body[k])
    platform = str(body.get("platform", "") or "").lower()
    if platform:
        if platform not in app_config.PLATFORMS:
            raise HTTPException(400, f"不支持的平台: {platform}")
        if platform != state.settings.get("platform"):
            state.settings["platform"] = platform
            state.clear_catalog()  # 平台切换后旧目录缓存作废
    app_config.save_settings(state.settings)
    return _config_payload(state)
