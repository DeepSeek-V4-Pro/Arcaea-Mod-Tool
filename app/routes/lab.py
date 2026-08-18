"""实验功能控制台:平台模式(Android / iOS)切换与状态查询。

iOS 模式是实验性功能:解包/替换/重打包复用现有引擎(IPA 即 zip,
素材树与 Android 同构);原包(越狱 dump 解密版)与最终签名都由用户自理,
工具只负责 提取素材 → 替换素材 → 产出未签名 IPA。
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException

from core import iosmode
from core.zipio import read_central_directory

from .. import config as app_config
from ..deps import get_state
from ..state import AppState

router = APIRouter(tags=["lab"])


def _fmt(n: int) -> str:
    if n >= 1 << 30:
        return f"{n / (1 << 30):.2f} GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.0f} KB"
    return f"{n} B"


@router.get("/api/lab/status")
def lab_status(state: AppState = Depends(get_state)):
    """实验功能控制台状态:生效平台、原包来源、input/ 候选、应用根目录等。"""
    settings = state.settings
    configured = settings.get("apk_path") or ""
    settings_platform = settings.get("platform") or "android"
    resolve_error = None
    try:
        pick = app_config.pick_pkg(configured, settings_platform)
    except Exception as ex:
        resolve_error = str(ex)
        pick = {"path": "", "platform": settings_platform, "source": "",
                "display": "", "inner_ipa": None, "note": ""}
    pkg = pick["path"]
    info = {
        "platform": pick["platform"],              # 生效平台(可能自动跟随 input/)
        "settings_platform": settings_platform,    # 用户在设置里的平台
        "platforms": list(app_config.PLATFORMS),
        "configured_path": configured,
        "apk_path": pkg or "",
        "pkg_source": pick["source"],              # configured | input | ''
        "pkg_display": pick["display"],
        "pkg_note": pick["note"],
        "inner_ipa": None,
        "pkg_found": bool(pkg and os.path.exists(pkg)),
        "pkg_size": os.path.getsize(pkg) if pkg and os.path.exists(pkg) else 0,
        "pkg_size_human": _fmt(os.path.getsize(pkg)) if pkg and os.path.exists(pkg) else "",
        "app_root": None,
        "input_candidates": app_config.input_candidates(),
        "catalog_ready": state.catalog is not None,
        "resolve_error": resolve_error,
    }
    if info["pkg_found"]:
        # 配置的是外层 zip 时补充内层 IPA 信息
        if pick["inner_ipa"]:
            info["inner_ipa"] = {"name": pick["inner_ipa"], "size_human": ""}
        try:
            entries, _cd, _eocd = read_central_directory(pkg)
            info["app_root"] = iosmode.detect_app_root(entries)
            if pick["inner_ipa"] and pick["source"] == "input":
                # input/ 的 zip 场景:size_human 展示外层大小即可,内层已解出缓存
                info["inner_ipa"] = {"name": pick["inner_ipa"], "size_human": ""}
        except Exception:
            pass
    return info


@router.post("/api/lab/platform")
def lab_set_platform(body: dict, state: AppState = Depends(get_state)):
    """切换平台模式(android / ios);切换后旧目录缓存作废,需重新扫描。"""
    platform = str(body.get("platform", "")).lower()
    if platform not in app_config.PLATFORMS:
        raise HTTPException(400, f"不支持的平台: {platform}")
    if platform != state.settings.get("platform"):
        state.settings["platform"] = platform
        app_config.save_settings(state.settings)
        state.clear_catalog()
    return lab_status(state)
