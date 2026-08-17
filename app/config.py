"""路径布局与持久化用户设置。

所有路径均基于项目根目录推导,不依赖当前工作目录;
settings.json 只保存用户配置,损坏或缺失时回退到默认值。
"""

from __future__ import annotations

import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
WEBUI_DIR = os.path.join(BASE_DIR, "webui")
INPUT_DIR = os.path.join(BASE_DIR, "input")     # 原包放置目录:放入即自动识别

SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
THUMB_DIR = os.path.join(DATA_DIR, "thumbs")      # 素材缩略图缓存
PATCH_DIR = os.path.join(DATA_DIR, "patches")     # 补丁存储(替换内容 + 元数据)
OUTPUT_DIR = os.path.join(DATA_DIR, "output")     # 构建产物(mod APK)
PACK_DIR = os.path.join(DATA_DIR, "packs")        # 补丁包导出/导入

# 默认 apk_path 留空:启动时自动从 input/ 目录识别,方便开源协作
DEFAULT_SETTINGS = {
    "apk_path": "",
    "output_dir": OUTPUT_DIR,
}

_save_lock = threading.Lock()


def ensure_dirs() -> None:
    """创建全部运行时数据目录(幂等)。"""
    for d in (DATA_DIR, INPUT_DIR, THUMB_DIR, PATCH_DIR, OUTPUT_DIR, PACK_DIR):
        os.makedirs(d, exist_ok=True)


def find_apk_in_input() -> str | None:
    """在 input/ 目录自动识别原包:取最大的 *.apk。

    开源场景下用户把原版 APK 丢进 input/ 即可,无需手填路径;
    多个 APK 并存时按体积取最大者(基础包最大,最可能是原版)。
    """
    try:
        cands = [os.path.join(INPUT_DIR, n) for n in os.listdir(INPUT_DIR)
                 if n.lower().endswith(".apk")]
    except OSError:
        return None
    if not cands:
        return None
    return max(cands, key=lambda p: os.path.getsize(p))


def resolve_apk(configured: str) -> str:
    """生效的 APK 路径:配置路径存在则用配置,否则回退 input/ 自动识别。"""
    configured = (configured or "").strip()
    if configured and os.path.exists(configured):
        return configured
    found = find_apk_in_input()
    return found or configured


def load_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            out = {**DEFAULT_SETTINGS, **saved}
        except Exception:
            out = dict(DEFAULT_SETTINGS)  # 配置损坏时使用默认值
    else:
        out = dict(DEFAULT_SETTINGS)
    # 配置路径缺失时自动补上 input/ 目录识别到的原包(首次启动即可用)
    if not (out.get("apk_path") or "").strip() or not os.path.exists(out.get("apk_path") or ""):
        found = find_apk_in_input()
        if found:
            out["apk_path"] = found
    return out


def save_settings(settings: dict) -> None:
    """原子写入 settings.json(先写临时文件再替换)。"""
    ensure_dirs()
    with _save_lock:
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_PATH)
