"""Asset catalog: 2D image assets only, with fine-grained sub-categories.

Built from the central directory only (no extraction) in well under a second
even for a 1.8GB APK. Sub-category rules follow the actual Arcaea layout:

  assets/char/<id>_mp.png      角色立绘       assets/char/<id>_icon.png   角色头像
  assets/char/<id>u_mp.png     觉醒立绘       assets/char/<id>u_icon.png  觉醒头像
  assets/char/<id>a_mp.png     变体立绘       assets/char/1080/*.png      高清立绘
  assets/img/bg/**             曲目背景       assets/particle/*           音符皮肤
  assets/startup/*.png         启动画面       assets/models/* 贴图        模型贴图
  assets/img/story/**/         剧情 CG        assets/img/story/*          剧情界面
  assets/img/{epilogue,finale} 终章 CG       assets/img/gamescene/*      游玩界面
  assets/img/songselect/*      选曲界面       assets/img/results/*        结算界面
  assets/img/world/*           世界模式       assets/img/multiplayer/*    联机界面
  assets/img/dialog_v2/*       对话框        assets/img/1080/* 等其余     界面贴图
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from .zipio import read_central_directory, read_entry_data

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}

# sub-category id -> display label (order matters for the sidebar)
SUBS = [
    ("char", "角色立绘"),
    ("bg", "曲目背景"),
    ("song_jacket", "曲目曲绘"),
    ("particle", "音符皮肤"),
    ("model", "模型贴图"),
    ("startup", "启动画面"),
    ("story_cg", "剧情 CG"),
    ("story_ui", "剧情界面"),
    ("ui_layout", "界面布局贴图"),
    ("ui_ingame", "游玩界面"),
    ("ui_songselect", "选曲界面"),
    ("ui_results", "结算界面"),
    ("ui_world", "世界模式"),
    ("ui_multiplayer", "联机界面"),
    ("ui_dialog", "对话框"),
    ("ui_other", "其他界面"),
    ("misc", "杂项图片"),
]
SUB_LABELS = dict(SUBS)

# character form labels (for grouped view + jump buttons)
FORM_LABELS = {
    "portrait": "立绘",
    "icon": "头像",
    "awaken_portrait": "觉醒立绘",
    "awaken_icon": "觉醒头像",
    "hd": "高清立绘",
    "special": "变体",
}
# order of forms inside a character group
FORM_ORDER = ["portrait", "icon", "awaken_portrait", "awaken_icon", "hd", "special"]

IMG_UI_DIRS = {
    "gamescene": "ui_ingame",
    "songselect": "ui_songselect",
    "results": "ui_results",
    "world": "ui_world",
    "multiplayer": "ui_multiplayer",
    "dialog_v2": "ui_dialog",
}


def char_info(path: str) -> tuple[str, str] | None:
    """Return (char_id, form) for assets/char entries, else None."""
    low = path.lower()
    if not low.startswith("assets/char/"):
        return None
    rest = low[len("assets/char/"):]
    parts = rest.split("/")
    name = parts[-1]
    base = name[:-4] if name.endswith((".png", ".jpg", ".jpeg")) else name
    if len(parts) >= 2 and parts[0] == "1080":
        m = re.match(r"^(-?\d+)([a-z]?)$", base)
        return (m.group(1), "hd") if m else (None, "hd")
    m = re.match(r"^(-?\d+)([a-z]*)_(mp|icon)$", base)
    if not m:
        return (None, "special")
    cid, suf, kind = m.group(1), m.group(2), m.group(3)
    if suf == "u":
        form = "awaken_icon" if kind == "icon" else "awaken_portrait"
    elif suf:
        form = "special"
    else:
        form = "icon" if kind == "icon" else "portrait"
    return cid, form


def _sub_of_image(path: str) -> str:
    low = path.lower()
    if low.startswith("assets/char/"):
        return "char"
    if low.startswith("assets/img/bg/"):
        return "bg"
    if low.startswith("assets/songs/"):
        return "song_jacket"
    if low.startswith("assets/particle/"):
        return "particle"
    if low.startswith("assets/startup/"):
        return "startup"
    if low.startswith("assets/models/") and low.endswith((".png", ".jpg", ".jpeg")):
        return "model"
    if low.startswith("assets/layouts/"):
        return "ui_layout"
    if low.startswith("assets/app-data/story/"):
        return "story_cg" if "/cg/" in low else "story_ui"
    if low.startswith("assets/img/story/"):
        return "story_cg" if low.count("/") >= 4 else "story_ui"
    if low.startswith(("assets/img/epilogue/", "assets/img/finale/")):
        return "story_cg"
    if low.startswith("assets/img/"):
        parts = low.split("/")
        if len(parts) >= 3 and parts[2] in IMG_UI_DIRS:
            return IMG_UI_DIRS[parts[2]]
        return "ui_other"
    return "misc"


@dataclass
class AssetInfo:
    path: str
    size: int
    csize: int
    method: int
    category: str
    sub: str
    preview: str
    human_size: str
    char_id: str = ""
    form: str = ""


def _fmt(n: int) -> str:
    if n >= 1 << 30:
        return f"{n / (1 << 30):.2f} GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.0f} KB"
    return f"{n} B"


CHAR_NAMES_FILE = "assets/char/characters.json"
_HAN_RANGE = range(0x4E00, 0x9FFF + 1)
# 简体中文特征字:用于从多语言名称串里挑出简体中文(Arcaea 名称场景足够覆盖)
_SIMPLIFIED_MARKERS = "对红调梦丝爱丽忆体图国时后现发门问线纸点华际车东乐习马头凤办从双认让议论记许设访证词语说读课讲诗诚谢识谱"


def _pick_display_name(search: list[str]) -> str:
    """从多语言搜索串里挑显示名(优先简体中文)。

    search_strings 大致为 [日文/简体/繁体/假名/韩文];简体优先策略:
    对每个含汉字串统计简体特征字数量,取分最高者,并列取靠前者。
    """
    han = [(i, s) for i, s in enumerate(search) if any(ord(ch) in _HAN_RANGE for ch in s)]
    if not han:
        return search[0] if search else ""
    best_s, best_score = han[0][1], -1
    for _i, s in han:
        score = sum(1 for ch in s if ch in _SIMPLIFIED_MARKERS)
        if score > best_score:
            best_s, best_score = s, score
    return best_s


def load_char_names(apk_path: str, entries) -> dict:
    """char_id(str) -> {"name": 罗马音, "label": 显示名, "search": 全部搜索串}。

    数据来自 APK 内 assets/char/characters.json;文件缺失或解析失败时返回空表。
    """
    char_names: dict = {}
    for e in entries:
        if e.name != CHAR_NAMES_FILE:
            continue
        try:
            data = json.loads(read_entry_data(apk_path, e).decode("utf-8"))
            for c in data:
                search = c.get("search_strings") or []
                cid = str(c.get("character_id"))
                char_names[cid] = {
                    "name": c.get("name", ""),
                    "label": _pick_display_name(search),
                    "search": search,
                }
        except Exception:
            pass
        break
    return char_names


def build_catalog(apk_path: str) -> dict:
    entries, _cd, _eocd = read_central_directory(apk_path)
    assets = []
    sub_counts = {sid: 0 for sid, _ in SUBS}
    total_images = 0
    for e in entries:
        if e.is_dir or e.usize == 0:
            continue
        ext = os.path.splitext(e.name)[1].lower()
        if ext not in IMAGE_EXTS:
            continue  # 只保留 2D 图片素材
        sub = _sub_of_image(e.name)
        char_id, form = "", ""
        if sub == "char":
            ci = char_info(e.name)
            if ci:
                char_id, form = ci
        assets.append(AssetInfo(
            path=e.name, size=e.usize, csize=e.csize, method=e.method,
            category="image", sub=sub, preview="image",
            human_size=_fmt(e.usize),
            char_id=char_id, form=form,
        ))
        sub_counts[sub] = sub_counts.get(sub, 0) + 1
        total_images += 1
    assets.sort(key=lambda a: a.path)
    return {
        "total": total_images,
        "sub_counts": {k: v for k, v in sub_counts.items() if v},
        "subs": [{"id": sid, "label": label} for sid, label in SUBS
                 if sub_counts.get(sid)],
        "form_labels": FORM_LABELS,
        "form_order": FORM_ORDER,
        "char_names": load_char_names(apk_path, entries),
        "assets": [a.__dict__ for a in assets],
    }


def find_entry(apk_path: str, path: str):
    entries, _cd, _eocd = read_central_directory(apk_path)
    for e in entries:
        if e.name == path:
            return e
    return None


def read_asset(apk_path: str, path: str) -> bytes | None:
    e = find_entry(apk_path, path)
    if e is None:
        return None
    return read_entry_data(apk_path, e)
