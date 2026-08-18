"""路由共享依赖:状态访问与原包前置校验。"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request

from core import iosmode
from core.zipio import read_central_directory

from . import config as app_config
from .state import AppState


def get_state(request: Request) -> AppState:
    return request.app.state.amt


def need_pick(state: AppState) -> dict:
    """校验并返回「原包选择结果」:生效路径 + 生效平台 + 来源说明,不满足则抛 400。

    每次实时解析:配置路径优先,否则自动识别 input/ 目录(支持 *.apk / *.ipa /
    外层 *.zip,跨平台时自动跟随)。iOS 模式额外校验包内存在 Payload/<App>.app/
    (官方 App Store 直装包是 FairPlay 加密的,工具无法解包,需用户自备越狱 dump 产物)。
    """
    settings = state.settings
    try:
        pick = app_config.pick_pkg(
            settings.get("apk_path") or "", settings.get("platform") or "android")
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    p = pick["path"]
    if not p or not os.path.exists(p):
        raise HTTPException(
            400, "未找到原包:请将原版 APK 或解密后的 IPA(越狱 dump 产物)放入项目 input/ "
                 "目录(也支持直接放外层 zip),或在「配置」中手动填写路径")
    if pick["platform"] == "ios":
        entries, _cd, _eocd = read_central_directory(p)
        if iosmode.detect_app_root(entries) is None:
            raise HTTPException(
                400, "不是有效的 IPA:包内未找到 Payload/<App>.app/。"
                     "注意:官方 App Store 包是 FairPlay 加密的,需先在越狱设备上 dump 解密")
    return pick


def need_apk(state: AppState) -> str:
    """校验并返回可用的原包路径(need_pick 的路径部分)。"""
    return need_pick(state)["path"]
