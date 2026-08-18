"""路径布局与持久化用户设置,以及 input/ 原包的统一自动识别。

原包放置目录 input/ 同时支持三种形态,放入即自动识别(无需改配置):

  *.apk                   Android 原包
  *.ipa                   iOS 原包(越狱 dump 的解密版)
  *.zip                   外层 zip(暗改包分发格式),自动解出内层 IPA 缓存

识别规则:配置路径优先(按文件类型判定平台);未配置时扫描 input/,
按「当前平台 → 外层 zip(iOS) → 另一平台」依次取最大候选,跨平台时自动跟随
(例如 input/ 只有 IPA 而当前是 Android 模式,自动切换为 iOS 生效平台)。

所有路径均基于项目根目录推导,不依赖当前工作目录;
settings.json 只保存用户配置,损坏或缺失时回退到默认值。
"""

from __future__ import annotations

import json
import os
import threading

from core import iosmode

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
WEBUI_DIR = os.path.join(BASE_DIR, "webui")
INPUT_DIR = os.path.join(BASE_DIR, "input")     # 原包放置目录:放入即自动识别

SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
THUMB_DIR = os.path.join(DATA_DIR, "thumbs")      # 素材缩略图缓存
PATCH_DIR = os.path.join(DATA_DIR, "patches")     # 补丁存储(替换内容 + 元数据)
OUTPUT_DIR = os.path.join(DATA_DIR, "output")     # 构建产物(mod APK / mod IPA)
PACK_DIR = os.path.join(DATA_DIR, "packs")        # 补丁包导出/导入

# 支持的目标平台:android(默认,成熟) | ios(实验性)
PLATFORMS = ("android", "ios")

# 默认 apk_path 留空:启动时自动从 input/ 目录识别,方便开源协作
DEFAULT_SETTINGS = {
    "apk_path": "",
    "output_dir": OUTPUT_DIR,
    "platform": "android",
}

_save_lock = threading.Lock()


def ensure_dirs() -> None:
    """创建全部运行时数据目录(幂等)。"""
    for d in (DATA_DIR, INPUT_DIR, THUMB_DIR, PATCH_DIR, OUTPUT_DIR, PACK_DIR,
              iosmode.IPA_CACHE_DIR):
        os.makedirs(d, exist_ok=True)


# ------------------------------------------------------------------ input/ 识别

def scan_input() -> dict:
    """扫描 input/ 目录,返回按大小降序的候选清单:

    {"apk": [绝对路径...], "ipa": [...], "zip": [...]}

    zip 为疑似外层包(是否含内层 IPA 由 pick_pkg 惰性探测)。
    """
    try:
        names = os.listdir(INPUT_DIR)
    except OSError:
        names = []
    out: dict[str, list[str]] = {"apk": [], "ipa": [], "zip": []}
    for n in names:
        p = os.path.join(INPUT_DIR, n)
        if not os.path.isfile(p):
            continue
        low = n.lower()
        if low.endswith(".apk"):
            out["apk"].append(p)
        elif low.endswith(".ipa"):
            out["ipa"].append(p)
        elif low.endswith(".zip"):
            out["zip"].append(p)
    for k in out:
        out[k].sort(key=lambda p: os.path.getsize(p), reverse=True)
    return out


def _pick_from_scan(scan: dict, platform: str, note: str) -> dict:
    """从 input/ 扫描结果里选原包:当前平台 → 外层 zip(iOS) → 另一平台(自动跟随)。"""
    if platform == "android":
        order = [("apk", "android"), ("zip", "ios"), ("ipa", "ios")]
    else:
        order = [("ipa", "ios"), ("zip", "ios"), ("apk", "android")]
    for kind, plat in order:
        cands = scan.get(kind) or []
        if not cands:
            continue
        if kind != "zip":
            p = cands[0]
            return {
                "path": p, "platform": plat, "source": "input",
                "display": os.path.basename(p), "inner_ipa": None,
                "note": note or (f"input/ 未找到 {('IPA' if plat == 'ios' else 'APK')},"
                                 f"已自动使用 {'iOS' if plat == 'ios' else 'Android'} 模式"
                                 if plat != platform else ""),
            }
        # zip:惰性探测内层 IPA,取第一个含 .ipa 的
        for z in cands:
            inner = iosmode.find_inner_ipa(z)
            if inner:
                path = iosmode.ensure_cached_ipa(z)
                return {
                    "path": path, "platform": "ios", "source": "input",
                    "display": os.path.basename(z), "inner_ipa": inner.filename,
                    "note": f"外层 zip 自动识别(内层 {inner.filename}),已使用 iOS 模式",
                }
    return {"path": "", "platform": platform, "source": "", "display": "",
            "inner_ipa": None, "note": ""}


def pick_pkg(configured: str, platform: str) -> dict:
    """解析生效原包与生效平台。

    返回 {path, platform, source, display, inner_ipa, note}:
      path      生效原包路径(.ipa / .apk;外层 zip 已解出为缓存 IPA)
      platform  生效平台——配置路径按文件类型判定(.ipa/.zip→ios,.apk→android);
                input/ 自动识别时按「当前平台 → 外层 zip → 另一平台」并自动跟随
      source    'configured'(手动配置) | 'input'(自动识别) | ''(未找到)
      display   展示路径(input 场景为 input/ 内文件名)
      inner_ipa 外层 zip 的内层 ipa 文件名(仅 zip 场景)
      note      给前端展示的说明(自动跟随原因 / 配置提示等)

    模式优先:配置路径的类型与当前模式不符时(如 Android 模式却配置了 .zip/.ipa),
    忽略该配置并回退 input/ 自动识别——保证「切回 Android 模式」这类操作永远生效,
    配置路径只在匹配的模式内起作用。
    """
    configured = (configured or "").strip()
    if configured and os.path.exists(configured):
        low = configured.lower()
        if low.endswith(".ipa"):
            if platform != "ios":
                return _mode_conflict_pick(configured, "ios", platform)
            return {"path": configured, "platform": "ios", "source": "configured",
                    "display": configured, "inner_ipa": None, "note": ""}
        if low.endswith(".apk"):
            if platform != "android":
                return _mode_conflict_pick(configured, "android", platform)
            return {"path": configured, "platform": "android", "source": "configured",
                    "display": configured, "inner_ipa": None, "note": ""}
        if low.endswith(".zip"):
            if platform != "ios":
                return _mode_conflict_pick(configured, "ios", platform)
            inner = iosmode.find_inner_ipa(configured)
            if inner is None:
                raise ValueError(f"压缩包内未找到 .ipa 文件: {configured}")
            path = iosmode.ensure_cached_ipa(configured)
            return {"path": path, "platform": "ios", "source": "configured",
                    "display": configured, "inner_ipa": inner.filename,
                    "note": f"外层 zip,内层 {inner.filename}(已解出缓存)"}
        # 其他扩展名:按配置的平台原样返回
        return {"path": configured, "platform": platform, "source": "configured",
                "display": configured, "inner_ipa": None, "note": ""}

    return _pick_from_scan(scan_input(), platform, "")


def _mode_conflict_pick(configured: str, cfg_platform: str, platform: str) -> dict:
    """配置路径类型与当前模式不符:忽略配置,回退 input/ 自动识别并说明原因。

    configured 仍保留在设置里,切回匹配的模式后自动重新生效。
    """
    label = "iOS" if cfg_platform == "ios" else "Android"
    cur = "Android" if platform == "android" else "iOS"
    note = (f"配置的路径是 {label} 包({os.path.basename(configured)}),"
            f"与当前 {cur} 模式不符,已忽略并改用 input/ 自动识别")
    pick = _pick_from_scan(scan_input(), platform, note)
    if pick["path"]:
        return pick
    return {"path": "", "platform": platform, "source": "", "display": "",
            "inner_ipa": None, "note": note}


def input_candidates() -> dict:
    """input/ 候选的展示信息(前端用):{kind: [{name, size, size_human}]}。"""
    def fmt(n: int) -> str:
        if n >= 1 << 30:
            return f"{n / (1 << 30):.2f} GB"
        if n >= 1 << 20:
            return f"{n / (1 << 20):.1f} MB"
        if n >= 1 << 10:
            return f"{n / (1 << 10):.0f} KB"
        return f"{n} B"

    out = {}
    for kind, paths in scan_input().items():
        out[kind] = [{"name": os.path.basename(p), "size": os.path.getsize(p),
                      "size_human": fmt(os.path.getsize(p))} for p in paths]
    return out


# ------------------------------------------------------------------ settings

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
    # platform 只允许已知值
    if out.get("platform") not in PLATFORMS:
        out["platform"] = "android"
    return out


def save_settings(settings: dict) -> None:
    """原子写入 settings.json(先写临时文件再替换)。"""
    ensure_dirs()
    with _save_lock:
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_PATH)
