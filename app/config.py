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

SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
THUMB_DIR = os.path.join(DATA_DIR, "thumbs")      # 素材缩略图缓存
PATCH_DIR = os.path.join(DATA_DIR, "patches")     # 补丁存储(替换内容 + 元数据)
OUTPUT_DIR = os.path.join(DATA_DIR, "output")     # 构建产物(mod APK)
PACK_DIR = os.path.join(DATA_DIR, "packs")        # 补丁包导出/导入

DEFAULT_SETTINGS = {
    "apk_path": r"D:\Tools\games\Arcaea\arcaea_6.16.2c.apk",
    "output_dir": OUTPUT_DIR,
}

_save_lock = threading.Lock()


def ensure_dirs() -> None:
    """创建全部运行时数据目录(幂等)。"""
    for d in (DATA_DIR, THUMB_DIR, PATCH_DIR, OUTPUT_DIR, PACK_DIR):
        os.makedirs(d, exist_ok=True)


def load_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            return {**DEFAULT_SETTINGS, **saved}
        except Exception:
            pass  # 配置损坏时使用默认值
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    """原子写入 settings.json(先写临时文件再替换)。"""
    ensure_dirs()
    with _save_lock:
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_PATH)
